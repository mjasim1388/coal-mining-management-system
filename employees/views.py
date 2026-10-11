from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from datetime import timedelta
from calendar import month_abbr
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from .decorators import role_required
from .exports import make_excel_response
from .forms import (
    AttendanceForm,
    CustomerForm,
    EmployeeForm,
    EquipmentForm,
    InventoryItemForm,
    MaintenanceLogForm,
    MineForm,
    PayrollForm,
    ProductionForm,
    SaleForm,
    StockTransactionForm,
)
from .models import (Employee, Mine, ProductionRecord, Attendance,
                     InventoryItem, StockTransaction, Payroll,
                     Customer, Sale, Notification, ApprovalLog,
                     Equipment, MaintenanceLog, VoidLog, SalePayment)

def distinct_values(queryset, field, limit=30):
    """Return a list of distinct non-empty values from a model field."""
    values = queryset.exclude(**{f'{field}__isnull': True}).exclude(**{field: ''})
    seen = []
    for v in values.values_list(field, flat=True).distinct():
        if v and str(v).strip() and str(v).strip() not in seen:
            seen.append(str(v).strip())
        if len(seen) >= limit:
            break
    return seen

# ---------- VOID HELPER ----------
def void_record(record, user, reason, request, object_label=''):
    """Void a record: sets void fields + creates VoidLog entry.

    Returns True if successful, False if already voided.
    """
    from django.utils import timezone

    # Already voided?
    if getattr(record, 'voided', False):
        return False

    # Get client IP
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')

    # Set void fields on the record
    record.voided = True
    record.voided_by = user
    record.voided_at = timezone.now()
    record.voided_reason = reason
    record.save()

    # Create central audit log entry
    VoidLog.objects.create(
        object_type=record.__class__.__name__,
        object_id=record.pk,
        object_label=object_label or str(record),
        voided_by=user,
        reason=reason,
        ip_address=ip,
    )

    return True

# =====================================================================
# DASHBOARD VIEW  (drop-in replacement for the dashboard() in views.py)
#
# 1) ADD these imports at the top of views.py (merge with existing ones):
#
#       from datetime import timedelta
#       from calendar import month_abbr
#       from django.db.models import (Count, DecimalField, ExpressionWrapper,
#                                     F, Q, Sum, Value)
#       from django.db.models.functions import Coalesce, TruncMonth
#       from django.utils import timezone
#
#    (views.py already has `from datetime import date` and `Sum`; keep them.)
#
# 2) DELETE the old dashboard() function and paste everything below
#    (helpers + dashboard) in its place.
#
# ASSUMPTION: a sale's total is quantity_tons * price_per_ton.
# If your Sale model stores `total_amount` as a real database field and it
# can differ from that (discounts, tax...), change the two lines marked
# "SALE EXPRESSIONS" to:
#       SALE_TOTAL   = F('total_amount')
#       SALE_BALANCE = ExpressionWrapper(F('total_amount') - F('amount_paid'),
#                                        output_field=_DEC)
# =====================================================================

# ---------- DASHBOARD HELPERS ----------
_DEC = DecimalField(max_digits=18, decimal_places=2)

# SALE EXPRESSIONS
SALE_TOTAL = ExpressionWrapper(F('quantity_tons') * F('price_per_ton'), output_field=_DEC)
SALE_BALANCE = ExpressionWrapper(
    F('quantity_tons') * F('price_per_ton') - F('amount_paid'), output_field=_DEC
)


def _zero(expr, **kwargs):
    """Sum(expr) that returns 0 instead of None when there are no rows."""
    return Coalesce(Sum(expr, **kwargs), Value(0), output_field=_DEC)


def _month_back(today, back):
    """(year, month) of the month `back` months before today's month."""
    y, m = today.year, today.month - back
    while m <= 0:
        m += 12
        y -= 1
    return y, m


def _pct_change(current, previous):
    if not previous:
        return None
    try:
        return round(((float(current) - float(previous)) / float(previous)) * 100, 1)
    except (ZeroDivisionError, ValueError, TypeError):
        return None


def _daily_sales_series(sales_qs, today, days=30):
    """Sales per day for the last `days` days, in ONE query."""
    start = today - timedelta(days=days - 1)
    rows = (
        sales_qs.filter(date__gte=start, date__lte=today)
        .order_by()
        .values('date')
        .annotate(t=Sum(SALE_TOTAL))
    )
    by_day = {r['date']: r['t'] for r in rows}
    labels, data = [], []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        labels.append(d.strftime('%d %b'))
        data.append(float(by_day.get(d) or 0))
    return labels, data


def _top_customers(sales_qs, limit=5):
    rows = (
        sales_qs.order_by()
        .values('customer__name')
        .annotate(t=Sum(SALE_TOTAL))
        .order_by('-t')[:limit]
    )
    return [(r['customer__name'], float(r['t'] or 0)) for r in rows]


# ---------- DASHBOARD ----------
@role_required('Manager', 'Accountant', 'Viewer')
def dashboard(request):
    today = timezone.localdate()          # timezone-aware "today"
    this_month_start = today.replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    days_30_ago = today - timedelta(days=30)
    days_60_ago = today - timedelta(days=60)
    days_90_ago = today - timedelta(days=90)

    user_roles = set(request.user.groups.values_list('name', flat=True))
    is_superuser = request.user.is_superuser
    is_viewer_only = (user_roles == {'Viewer'}) and not is_superuser
    is_manager = is_superuser or 'Manager' in user_roles

    all_sales = Sale.objects.filter(voided=False)
    tm_sales_qs = all_sales.filter(date__gte=this_month_start)
    lm_sales_qs = all_sales.filter(date__gte=last_month_start, date__lte=last_month_end)

    # ================================================================
    # VIEWER DASHBOARD
    # ================================================================
    if is_viewer_only:
        totals = all_sales.aggregate(
            total=_zero(SALE_TOTAL),
            received=_zero('amount_paid'),
            tons=_zero('quantity_tons'),
        )
        trend_labels, trend_data = _daily_sales_series(all_sales, today)

        return render(request, 'viewer_dashboard.html', {
            'total_sales': totals['total'],
            'total_received': totals['received'],
            'total_outstanding': totals['total'] - totals['received'],
            'total_tons_sold': totals['tons'],
            'tm_sales': tm_sales_qs.aggregate(t=_zero(SALE_TOTAL))['t'],
            'lm_sales': lm_sales_qs.aggregate(t=_zero(SALE_TOTAL))['t'],
            'recent_sales': all_sales.select_related('customer', 'mine').order_by('-date')[:10],
            'trend_labels': trend_labels,
            'trend_data': trend_data,
            'top_customers': _top_customers(all_sales),
        })

    # ================================================================
    # FULL DASHBOARD
    # ================================================================

    # ----- EMPLOYEES / MINES -----
    emp = Employee.objects.filter(voided=False).aggregate(
        total=Count('pk'),
        active=Count('pk', filter=Q(status='Active')),
    )
    total_employees, active_employees = emp['total'], emp['active']
    mine_count = Mine.objects.filter(voided=False, status='Active').count()

    # ----- SALES -----
    tm = tm_sales_qs.aggregate(
        total=_zero(SALE_TOTAL),
        received=_zero('amount_paid'),
        tons=_zero('quantity_tons'),
        count=Count('pk'),
        paid=Count('pk', filter=Q(payment_status='Paid')),
        partial=Count('pk', filter=Q(payment_status='Partial')),
        unpaid=Count('pk', filter=Q(payment_status='Unpaid')),
    )
    lm = lm_sales_qs.aggregate(total=_zero(SALE_TOTAL), received=_zero('amount_paid'))

    tm_sales, tm_received = tm['total'], tm['received']
    tm_tons_sold, tm_sales_count = tm['tons'], tm['count']
    tm_paid, tm_partial, tm_unpaid = tm['paid'], tm['partial'], tm['unpaid']

    # ----- RECEIVABLES + AGING (one query) -----
    open_sales = all_sales.filter(payment_status__in=['Unpaid', 'Partial'])
    ag = open_sales.aggregate(
        a1=_zero(SALE_BALANCE, filter=Q(date__gte=days_30_ago)),
        a2=_zero(SALE_BALANCE, filter=Q(date__lt=days_30_ago, date__gte=days_60_ago)),
        a3=_zero(SALE_BALANCE, filter=Q(date__lt=days_60_ago, date__gte=days_90_ago)),
        a4=_zero(SALE_BALANCE, filter=Q(date__lt=days_90_ago)),
        c1=Count('pk', filter=Q(date__gte=days_30_ago)),
        c2=Count('pk', filter=Q(date__lt=days_30_ago, date__gte=days_60_ago)),
        c3=Count('pk', filter=Q(date__lt=days_60_ago, date__gte=days_90_ago)),
        c4=Count('pk', filter=Q(date__lt=days_90_ago)),
    )
    total_outstanding = ag['a1'] + ag['a2'] + ag['a3'] + ag['a4']
    overdue_amount = ag['a2'] + ag['a3'] + ag['a4']          # older than 30 days
    overdue_invoices = ag['c2'] + ag['c3'] + ag['c4']

    aging_rows = [
        ('0-30 days',  ag['a1'], ag['c1'], 'success'),
        ('31-60 days', ag['a2'], ag['c2'], 'warning'),
        ('61-90 days', ag['a3'], ag['c3'], 'danger'),
        ('90+ days',   ag['a4'], ag['c4'], 'danger'),
    ]
    aging = [
        {
            'label': label,
            'amount': amount,
            'count': count,
            'tone': tone,
            'pct': int(round(float(amount) / float(total_outstanding) * 100)) if total_outstanding else 0,
        }
        for label, amount, count, tone in aging_rows
    ]

    # ----- PRODUCTION -----
    all_prod = ProductionRecord.objects.filter(voided=False)
    tm_tons = all_prod.filter(date__gte=this_month_start).aggregate(t=_zero('quantity_tons'))['t']
    lm_tons = all_prod.filter(
        date__gte=last_month_start, date__lte=last_month_end
    ).aggregate(t=_zero('quantity_tons'))['t']

    # ----- PAYROLL (net_salary is calculated in Python, so one query + sum) -----
    tm_payroll = list(Payroll.objects.filter(voided=False, year=today.year, month=today.month))
    tm_payroll_total = sum(p.net_salary for p in tm_payroll)
    tm_payroll_count = len(tm_payroll)

    # ----- TODAY'S PULSE -----
    td = all_sales.filter(date=today).aggregate(count=Count('pk'), tons=_zero('quantity_tons'))
    todays_dispatches, todays_tons = td['count'], td['tons']
    todays_cash = SalePayment.objects.filter(
        date=today, sale__voided=False
    ).aggregate(t=_zero('amount'))['t']
    todays_production = all_prod.filter(date=today).aggregate(t=_zero('quantity_tons'))['t']

    att = Attendance.objects.filter(date=today, voided=False).aggregate(
        total=Count('pk'),
        present=Count('pk', filter=Q(status='Present')),
        absent=Count('pk', filter=Q(status='Absent')),
        leave=Count('pk', filter=Q(status='Leave')),
    )

    # ----- EQUIPMENT -----
    eq = Equipment.objects.filter(voided=False).aggregate(
        total=Count('pk'),
        working=Count('pk', filter=Q(status='Working')),
        maint=Count('pk', filter=Q(status='Under Maintenance')),
        out=Count('pk', filter=Q(status='Out of Service')),
    )

    # ----- FUEL (this month) -----
    fuel = StockTransaction.objects.filter(
        transaction_type='OUT', item__category='Fuel', date__gte=this_month_start,
    ).aggregate(
        liters=_zero('quantity'),
        cost=_zero(ExpressionWrapper(F('quantity') * F('item__unit_price'), output_field=_DEC)),
    )
    fuel_liters, fuel_cost = fuel['liters'], fuel['cost']

    # ----- MAINTENANCE (this month) -----
    maint = MaintenanceLog.objects.filter(
        voided=False, date__gte=this_month_start
    ).aggregate(cost=_zero('cost'), count=Count('pk'))
    maint_cost, maint_count = maint['cost'], maint['count']

    # ----- INVENTORY (is_low_stock is a model property, so load once) -----
    all_items = list(InventoryItem.objects.filter(voided=False))
    low_stock_items = [i for i in all_items if i.is_low_stock]
    low_stock_count = len(low_stock_items)
    inventory_value = sum(float(i.quantity) * float(i.unit_price) for i in all_items)

    # ----- PENDING APPROVALS (now includes "Paid Pending" payrolls,
    #       which the approvals page already shows) -----
    pending_approvals = 0
    if is_manager:
        pending_approvals = (
            Employee.objects.filter(approval_status='Pending', voided=False).count()
            + InventoryItem.objects.filter(approval_status='Pending', voided=False).count()
            + Payroll.objects.filter(status__in=['Pending', 'Paid Pending'], voided=False).count()
        )

    # ----- CUSTOMERS -----
    total_customers = Customer.objects.filter(voided=False).count()
    new_customers_month = Customer.objects.filter(
        voided=False, created_at__date__gte=this_month_start
    ).count()

    # ----- TOP CUSTOMERS -----
    top_customers = _top_customers(tm_sales_qs)
    top_customer = top_customers[0] if top_customers else None

    # ----- TRENDS -----
    sales_trend_pct = _pct_change(tm_sales, lm['total'])
    production_trend_pct = _pct_change(tm_tons, lm_tons)
    received_trend_pct = _pct_change(tm_received, lm['received'])

    # ----- 6-MONTH CHART (2 queries instead of 12) -----
    first_y, first_m = _month_back(today, 5)
    window_start = date(first_y, first_m, 1)

    def by_month(qs, expr):
        rows = (
            qs.filter(date__gte=window_start)
            .order_by()
            .annotate(m=TruncMonth('date'))
            .values('m')
            .annotate(t=Sum(expr))
        )
        return {(r['m'].year, r['m'].month): float(r['t'] or 0) for r in rows}

    prod_by_month = by_month(all_prod, 'quantity_tons')
    sales_by_month = by_month(all_sales, SALE_TOTAL)

    monthly_labels, monthly_production, monthly_sales = [], [], []
    for i in range(5, -1, -1):
        y, m = _month_back(today, i)
        monthly_labels.append(f'{month_abbr[m]} {str(y)[-2:]}')
        monthly_production.append(prod_by_month.get((y, m), 0.0))
        monthly_sales.append(sales_by_month.get((y, m), 0.0))

    # ----- 30-DAY TREND (1 query instead of 30) -----
    trend_labels, trend_data = _daily_sales_series(all_sales, today)

    # ----- MINE PERFORMANCE (managers only; 3 queries instead of 2 per mine) -----
    mine_performance = []
    if is_manager:
        tons_by_mine = dict(
            all_prod.filter(date__gte=this_month_start)
            .order_by().values_list('mine').annotate(t=Sum('quantity_tons'))
        )
        revenue_by_mine = dict(
            tm_sales_qs.order_by().values_list('mine').annotate(t=Sum(SALE_TOTAL))
        )
        for mine in Mine.objects.filter(voided=False):
            mine_performance.append({
                'mine': mine,
                'tons': tons_by_mine.get(mine.pk) or 0,
                'revenue': revenue_by_mine.get(mine.pk) or 0,
            })
        mine_performance.sort(key=lambda x: float(x['tons']), reverse=True)

    recent_sales = all_sales.select_related('customer', 'mine').order_by('-created_at')[:5]

    # ----- COST BREAKDOWN -----
    cost_payroll = float(tm_payroll_total or 0)
    cost_fuel = float(fuel_cost or 0)
    cost_maintenance = float(maint_cost or 0)

    # ----- SALES BY COAL TYPE (1 query) -----
    coal_type_data = {}
    rows = tm_sales_qs.order_by().values('coal_type').annotate(t=Sum(SALE_TOTAL))
    for r in rows:
        label = r['coal_type'] or 'Other'
        coal_type_data[label] = coal_type_data.get(label, 0) + float(r['t'] or 0)

    context = {
        'today': today,                      # template uses it for the attendance link

        # Employees / Mines
        'total_employees': total_employees,
        'active_employees': active_employees,
        'mine_count': mine_count,

        # Sales
        'tm_sales': tm_sales,
        'tm_received': tm_received,
        'tm_tons_sold': tm_tons_sold,
        'tm_sales_count': tm_sales_count,
        'total_outstanding': total_outstanding,

        # Production
        'tm_tons': tm_tons,

        # Payroll
        'tm_payroll_total': tm_payroll_total,
        'tm_payroll_count': tm_payroll_count,

        # Today
        'todays_dispatches': todays_dispatches,
        'todays_tons': todays_tons,
        'todays_cash': todays_cash,
        'todays_production': todays_production,
        'today_present': att['present'],
        'today_absent': att['absent'],
        'today_leave': att['leave'],
        'today_attendance_total': att['total'],

        # Equipment
        'eq_working': eq['working'],
        'eq_maint': eq['maint'],
        'eq_out': eq['out'],
        'eq_total': eq['total'],

        # Fuel / Maintenance
        'fuel_liters': fuel_liters,
        'fuel_cost': fuel_cost,
        'maint_cost': maint_cost,
        'maint_count': maint_count,

        # Inventory
        'low_stock_items': low_stock_items,
        'low_stock_count': low_stock_count,
        'inventory_value': inventory_value,

        # Approvals
        'pending_approvals': pending_approvals,

        # Customers
        'total_customers': total_customers,
        'new_customers_month': new_customers_month,

        # Overdue + aging
        'overdue_invoices': overdue_invoices,
        'overdue_amount': overdue_amount,
        'aging': aging,

        # Top customers
        'top_customers': top_customers,
        'top_customer': top_customer,

        # Trends
        'sales_trend_pct': sales_trend_pct,
        'production_trend_pct': production_trend_pct,
        'received_trend_pct': received_trend_pct,

        # Charts
        'monthly_labels': monthly_labels,
        'monthly_production': monthly_production,
        'monthly_sales': monthly_sales,
        'trend_labels': trend_labels,
        'trend_data': trend_data,
        'tm_paid': tm_paid,
        'tm_partial': tm_partial,
        'tm_unpaid': tm_unpaid,
        'cost_payroll': cost_payroll,
        'cost_fuel': cost_fuel,
        'cost_maintenance': cost_maintenance,
        'coal_type_labels': list(coal_type_data.keys()),
        'coal_type_values': list(coal_type_data.values()),

        # Tables
        'mine_performance': mine_performance,
        'recent_sales': recent_sales,
    }
    return render(request, 'dashboard.html', context)

# ---------- EMPLOYEES ----------
@role_required('Manager', 'Accountant')
def employee_list(request):
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    show_voided = request.GET.get('show_voided', '')

    employees = Employee.objects.all()
    if not show_voided:
        employees = employees.filter(voided=False)

    if query:
        employees = employees.filter(first_name__icontains=query) | \
                    employees.filter(last_name__icontains=query) | \
                    employees.filter(employee_code__icontains=query) | \
                    employees.filter(cnic__icontains=query)
    if status_filter:
        employees = employees.filter(status=status_filter)

    return render(request, 'employees/list.html', {
        'employees': employees,
        'query': query,
        'status_filter': status_filter,
        'show_voided': show_voided,
    })

@role_required('Manager')
def employee_detail(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    return render(request, 'employees/detail.html', {'employee': employee})


@role_required('Manager', 'Accountant')
def employee_add(request):
    from datetime import date as date_today

    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES)
        if form.is_valid():
            emp = form.save(commit=False)
            emp.added_by = request.user
            if request.user.is_superuser or request.user.groups.filter(name='Manager').exists():
                emp.approval_status = 'Approved'
                emp.save()
                notify_accountants(
                    f'New employee {emp.first_name} {emp.last_name} added by {request.user.username}.',
                    link=f'/employees/{emp.pk}/'
                )
                messages.success(request, f'Employee {emp.employee_code} added — {emp.first_name} {emp.last_name}.')
            else:
                emp.approval_status = 'Pending'
                emp.save()
                notify_managers(
                    f'Employee {emp.first_name} {emp.last_name} added by {request.user.username} is awaiting your approval.',
                    link='/approvals/',
                    status='Pending',
                    object_type='Employee',
                    object_id=emp.pk,
                )
                messages.info(request, f'Employee submitted for manager approval — {emp.employee_code}.')
            return redirect('employee_list')
    else:
        # Smart defaults: remember last employee's settings
        initial = {}
        last = Employee.objects.order_by('-created_at').first()
        if last:
            initial['shift'] = last.shift
            initial['department'] = last.department
            initial['designation'] = last.designation
            initial['status'] = 'Active'
        initial['date_of_joining'] = date_today.today()  # Auto-set today
        initial['status'] = 'Active'
        initial['shift'] = initial.get('shift', 'Morning')
        form = EmployeeForm(initial=initial)
    return render(request, 'employees/form.html', {'form': form, 'title': 'Add Employee'})

@role_required('Manager')
def employee_edit(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, 'Employee updated successfully.')
            return redirect('employee_list')
    else:
        form = EmployeeForm(instance=employee)
    return render(request, 'employees/form.html', {'form': form, 'title': 'Edit Employee'})


@role_required('Manager')
def employee_void(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if employee.voided:
        messages.warning(request, 'This employee is already voided.')
        return redirect('employee_list')

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('employee_void', pk=employee.pk)

        label = f'{employee.employee_code} — {employee.first_name} {employee.last_name}'
        if void_record(employee, request.user, reason, request, label):
            messages.success(request, f'Employee {label} has been voided.')
        return redirect('employee_list')

    return render(request, 'shared/void_confirm.html', {
        'title': 'Void Employee',
        'object_label': f'{employee.employee_code} — {employee.first_name} {employee.last_name}',
        'object_type': 'Employee',
        'details': [
            ('Designation', employee.designation),
            ('Department', employee.department),
            ('Status', employee.status),
            ('Joining Date', employee.date_of_joining),
        ],
        'cancel_url': 'employee_list',
    })


# ---------- MINES ----------
@role_required('Manager')
def mine_list(request):
    mines = Mine.objects.all()
    return render(request, 'mines/list.html', {'mines': mines})


@role_required('Manager')
def mine_add(request):
    if request.method == 'POST':
        form = MineForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Mine added successfully.')
            return redirect('mine_list')
    else:
        form = MineForm()
    return render(request, 'mines/form.html', {'form': form, 'title': 'Add Mine'})


@role_required('Manager')
def mine_edit(request, pk):
    mine = get_object_or_404(Mine, pk=pk)
    if request.method == 'POST':
        form = MineForm(request.POST, instance=mine)
        if form.is_valid():
            form.save()
            messages.success(request, 'Mine updated successfully.')
            return redirect('mine_list')
    else:
        form = MineForm(instance=mine)
    return render(request, 'mines/form.html', {'form': form, 'title': 'Edit Mine'})


@role_required('Manager')
def mine_void(request, pk):
    mine = get_object_or_404(Mine, pk=pk)
    if mine.voided:
        messages.warning(request, 'This mine is already voided.')
        return redirect('mine_list')

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('mine_void', pk=mine.pk)

        if void_record(mine, request.user, reason, request, mine.name):
            messages.success(request, f'Mine "{mine.name}" has been voided.')
        return redirect('mine_list')

    return render(request, 'shared/void_confirm.html', {
        'title': 'Void Mine',
        'object_label': mine.name,
        'object_type': 'Mine',
        'details': [
            ('Location', mine.location),
            ('Manager', mine.manager_name or '—'),
            ('Status', mine.status),
        ],
        'cancel_url': 'mine_list',
    })


# ---------- PRODUCTION ----------
@role_required('Manager', 'Accountant')
def production_list(request):
    mine_filter = request.GET.get('mine', '')
    show_voided = request.GET.get('show_voided', '')

    records = ProductionRecord.objects.select_related('mine').all()
    if not show_voided:
        records = records.filter(voided=False)
    if mine_filter:
        records = records.filter(mine_id=mine_filter)

    total = records.aggregate(t=Sum('quantity_tons'))['t'] or 0

    return render(request, 'production/list.html', {
        'records': records,
        'mines': Mine.objects.filter(voided=False),
        'mine_filter': mine_filter,
        'show_voided': show_voided,
        'total': total,
    })


@role_required('Manager', 'Accountant')
def production_add(request):
    from datetime import date as date_today

    if request.method == 'POST':
        form = ProductionForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.save()
            messages.success(request, f'Production record saved for {record.mine.name} — {record.quantity_tons} tons.')
            return redirect('production_list')
    else:
        # Pre-fill from the last production record
        initial = {}
        last = ProductionRecord.objects.order_by('-created_at').first()
        if last:
            initial['mine'] = last.mine
            initial['shift'] = last.shift
            initial['coal_type'] = last.coal_type
            initial['supervisor'] = last.supervisor
        initial['date'] = date_today.today()  # Auto-set today
        form = ProductionForm(initial=initial)
    return render(request, 'production/form.html', {'form': form, 'title': 'Add Production Record'})

@role_required('Manager', 'Accountant')
def production_edit(request, pk):
    record = get_object_or_404(ProductionRecord, pk=pk)
    if request.method == 'POST':
        form = ProductionForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, 'Production record updated.')
            return redirect('production_list')
    else:
        form = ProductionForm(instance=record)
    return render(request, 'production/form.html', {'form': form, 'title': 'Edit Production Record'})


@role_required('Manager')
def production_void(request, pk):
    record = get_object_or_404(ProductionRecord, pk=pk)
    if record.voided:
        messages.warning(request, 'This production record is already voided.')
        return redirect('production_list')

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('production_void', pk=record.pk)

        label = f'{record.mine.name} — {record.date} ({record.quantity_tons} tons)'
        if void_record(record, request.user, reason, request, label):
            messages.success(request, f'Production record voided: {label}')
        return redirect('production_list')

    return render(request, 'shared/void_confirm.html', {
        'title': 'Void Production Record',
        'object_label': f'{record.mine.name} — {record.date}',
        'object_type': 'Production Record',
        'details': [
            ('Mine', record.mine.name),
            ('Date', record.date),
            ('Shift', record.shift),
            ('Quantity', f'{record.quantity_tons} tons'),
            ('Coal Type', record.coal_type),
        ],
        'cancel_url': 'production_list',
    })


# ---------- ATTENDANCE ----------
@role_required('Manager', 'Accountant')
def attendance_list(request):
    date_filter = request.GET.get('date', '')
    status_filter = request.GET.get('status', '')
    show_voided = request.GET.get('show_voided', '')

    records = Attendance.objects.select_related('employee').all()
    if not show_voided:
        records = records.filter(voided=False)
    if date_filter:
        records = records.filter(date=date_filter)
    if status_filter:
        records = records.filter(status=status_filter)

    return render(request, 'attendance/list.html', {
        'records': records,
        'date_filter': date_filter,
        'status_filter': status_filter,
        'show_voided': show_voided,
    })


@role_required('Manager')
def attendance_add(request):
    from datetime import date as date_today

    if request.method == 'POST':
        form = AttendanceForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Attendance record added.')
            return redirect('attendance_list')
    else:
        # Pre-fill from the last attendance record
        initial = {}
        last = Attendance.objects.order_by('-created_at').first()
        if last:
            initial['shift'] = last.shift
            initial['status'] = last.status
        initial['date'] = date_today.today()  # Auto-set today
        form = AttendanceForm(initial=initial)
    return render(request, 'attendance/form.html', {'form': form, 'title': 'Add Attendance'})
@role_required('Manager')
def attendance_edit(request, pk):
    record = get_object_or_404(Attendance, pk=pk)
    if request.method == 'POST':
        form = AttendanceForm(request.POST, request.FILES, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, 'Attendance updated.')
            return redirect('attendance_list')
    else:
        form = AttendanceForm(instance=record)
    return render(request, 'attendance/form.html', {'form': form, 'title': 'Edit Attendance'})


@role_required('Manager')
def attendance_void(request, pk):
    record = get_object_or_404(Attendance, pk=pk)
    if record.voided:
        messages.warning(request, 'This attendance record is already voided.')
        return redirect('attendance_list')

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('attendance_void', pk=record.pk)

        label = f'{record.employee.employee_code} — {record.date}'
        if void_record(record, request.user, reason, request, label):
            messages.success(request, f'Attendance voided: {label}')
        return redirect('attendance_list')

    return render(request, 'attendance/void.html', {'record': record})

# ---------- INVENTORY ----------
@role_required('Manager', 'Accountant')
def inventory_list(request):
    category_filter = request.GET.get('category', '')
    low_filter = request.GET.get('low', '')
    search_query = request.GET.get('q', '')
    show_voided = request.GET.get('show_voided', '')

    items = list(InventoryItem.objects.all())
    if not show_voided:
        items = [i for i in items if not i.voided]

    if search_query:
        q = search_query.lower()
        items = [i for i in items if q in i.name.lower() or q in i.category.lower()]
    if category_filter:
        items = [i for i in items if i.category == category_filter]
    if low_filter:
        items = [i for i in items if i.is_low_stock]

    all_items = list(InventoryItem.objects.filter(voided=False))
    total_items = len(all_items)
    total_value = sum(float(i.quantity) * float(i.unit_price) for i in all_items)
    low_stock_count = sum(1 for i in all_items if i.is_low_stock)

    recent_movements = StockTransaction.objects.select_related(
        'item', 'issued_to_equipment', 'issued_to_employee', 'issued_to_mine'
    ).all()[:30]

    return render(request, 'inventory/list.html', {
        'items': items,
        'category_filter': category_filter,
        'low_filter': low_filter,
        'search_query': search_query,
        'show_voided': show_voided,
        'low_stock_count': low_stock_count,
        'total_items': total_items,
        'total_value': total_value,
        'recent_movements': recent_movements,
        'equipment_list': Equipment.objects.filter(voided=False),
        'employee_list': Employee.objects.filter(status='Active', voided=False),
        'mine_list': Mine.objects.filter(voided=False),
    })

@role_required('Manager', 'Accountant')
def inventory_add(request):
    if request.method == 'POST':
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.added_by = request.user
            if request.user.is_superuser or request.user.groups.filter(name='Manager').exists():
                item.approval_status = 'Approved'
                item.save()
                notify_accountants(
                    f'New inventory item "{item.name}" added by {request.user.username}.',
                    link=f'/inventory/{item.pk}/edit/'
                )
                messages.success(request, 'Inventory item added.')
            else:
                item.approval_status = 'Pending'
                item.save()
                notify_managers(
                    f'Inventory item "{item.name}" added by {request.user.username} is awaiting your approval.',
                    link='/approvals/',
                    status='Pending',
                    object_type='InventoryItem',
                    object_id=item.pk,
                )
                messages.info(request, 'Item submitted for manager approval.')
            return redirect('inventory_list')
    else:
        form = InventoryItemForm()
    return render(request, 'inventory/form.html', {'form': form, 'title': 'Add Inventory Item'})


@role_required('Manager', 'Accountant')
def inventory_edit(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)
    if request.method == 'POST':
        form = InventoryItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Item updated.')
            return redirect('inventory_list')
    else:
        form = InventoryItemForm(instance=item)
    return render(request, 'inventory/form.html', {'form': form, 'title': 'Edit Inventory Item'})


@role_required('Manager')
def inventory_void(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)
    if item.voided:
        messages.warning(request, 'This item is already voided.')
        return redirect('inventory_list')

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('inventory_void', pk=item.pk)

        if void_record(item, request.user, reason, request, item.name):
            messages.success(request, f'Inventory item "{item.name}" has been voided.')
        return redirect('inventory_list')

    return render(request, 'shared/void_confirm.html', {
        'title': 'Void Inventory Item',
        'object_label': item.name,
        'object_type': 'Inventory Item',
        'details': [
            ('Category', item.category),
            ('Quantity', f'{item.quantity} {item.unit}'),
            ('Unit Price', f'PKR {item.unit_price}'),
            ('Location', item.location or '—'),
        ],
        'cancel_url': 'inventory_list',
    })


@role_required('Manager', 'Accountant')
def stock_transaction_list(request):
    item_filter = request.GET.get('item', '')
    type_filter = request.GET.get('type', '')
    transactions = StockTransaction.objects.select_related('item').all()
    if item_filter:
        transactions = transactions.filter(item_id=item_filter)
    if type_filter:
        transactions = transactions.filter(transaction_type=type_filter)
    return render(request, 'inventory/transactions.html', {
        'transactions': transactions,
        'items': InventoryItem.objects.all(),
        'item_filter': item_filter,
        'type_filter': type_filter,
    })


@role_required('Manager', 'Accountant')
def stock_transaction_add(request):
    from datetime import date as date_today

    if request.method == 'POST':
        form = StockTransactionForm(request.POST)
        if form.is_valid():
            trans = form.save(commit=False)
            item = trans.item
            if trans.transaction_type == 'IN':
                item.quantity += trans.quantity
            else:
                if trans.quantity > item.quantity:
                    messages.error(request, f'Not enough stock. Available: {item.quantity} {item.unit}')
                    return render(request, 'inventory/transaction_form.html', {
                        'form': form, 'title': 'Add Stock Transaction',
                    })
                item.quantity -= trans.quantity
            item.save()
            trans.save()
            messages.success(request, f'Stock {trans.transaction_type} recorded. New quantity: {item.quantity} {item.unit}')
            return redirect('stock_transaction_list')
    else:
        # Pre-fill from the last transaction
        initial = {}
        last = StockTransaction.objects.order_by('-created_at').first()
        if last:
            initial['item'] = last.item
            initial['transaction_type'] = last.transaction_type
            initial['handled_by'] = last.handled_by
        initial['date'] = date_today.today()  # Auto-set today
        form = StockTransactionForm(initial=initial)
    return render(request, 'inventory/transaction_form.html', {
        'form': form, 'title': 'Add Stock Transaction',
    })

@role_required('Manager')
def stock_transaction_delete(request, pk):
    from django.db import transaction as db_transaction

    trans = get_object_or_404(StockTransaction, pk=pk)
    if request.method == 'POST':
        item = trans.item

        # Deleting a stock-IN would remove stock that may already be used
        if trans.transaction_type == 'IN' and trans.quantity > item.quantity:
            messages.error(
                request,
                f'Cannot delete this stock-in: only {item.quantity} {item.unit} left, '
                f'but this transaction added {trans.quantity} {item.unit}.'
            )
            return redirect('stock_transaction_list')

        # Both changes succeed together or not at all
        with db_transaction.atomic():
            if trans.transaction_type == 'IN':
                item.quantity -= trans.quantity
            else:
                item.quantity += trans.quantity
            item.save()
            trans.delete()

        messages.success(request, 'Transaction deleted and stock adjusted.')
        return redirect('stock_transaction_list')
    return render(request, 'inventory/transaction_delete.html', {'trans': trans})

# ---------- PAYROLL ----------
@role_required('Manager', 'Accountant')
def payroll_generate(request):
    from decimal import Decimal

    if request.method == 'POST':
        month = int(request.POST.get('month'))
        year = int(request.POST.get('year'))
        created = 0
        skipped = 0
        employees = Employee.objects.filter(status='Active', voided=False)
        is_manager_user = request.user.is_superuser or request.user.groups.filter(name='Manager').exists()

        for emp in employees:
            if Payroll.objects.filter(employee=emp, month=month, year=year).exists():
                skipped += 1
                continue

            records = Attendance.objects.filter(
                employee=emp, date__month=month, date__year=year, voided=False
            )
            present = records.filter(status='Present').count()
            absent = records.filter(status='Absent').count()
            leave = records.filter(status='Leave').count()
            half = records.filter(status='Half Day').count()
            overtime_hours = sum((r.overtime_hours or Decimal('0')) for r in records)

            basic = emp.salary or Decimal('0')
            # Absence deduction: absent days + half days (0.5 each) at daily rate (basic/30)
            daily_rate = basic / Decimal('30') if basic else Decimal('0')
            absence_deduction = (absent * daily_rate) + (half * daily_rate * Decimal('0.5'))

            # Overtime: double rate, hourly = basic / 26 / 8
            hourly_rate = basic / Decimal('26') / Decimal('8') if basic else Decimal('0')
            overtime_amount = overtime_hours * hourly_rate * Decimal('2')

            Payroll.objects.create(
                employee=emp,
                month=month,
                year=year,
                basic_salary=basic,
                present_days=present,
                absent_days=absent,
                leave_days=leave,
                half_days=half,
                overtime_hours=overtime_hours,
                overtime_amount=overtime_amount,
                allowances=Decimal('0'),
                deductions=Decimal('0'),
                status='Approved' if is_manager_user else 'Pending',
                created_by=request.user,
            )
            created += 1

        if not is_manager_user and created > 0:
            notify_managers(
                f'{created} payroll record(s) for {month}/{year} were generated by {request.user.username} and are awaiting your approval.',
                link='/approvals/'
            )

        messages.success(request, f'Payroll generated for {created} employee(s). Skipped: {skipped}.')
        return redirect('payroll_list')

    return render(request, 'payroll/generate.html', {
        'months': Payroll.MONTH_CHOICES,
    })
@role_required('Manager', 'Accountant')
def payroll_list(request):
    month_filter = request.GET.get('month', '')
    year_filter = request.GET.get('year', '')
    status_filter = request.GET.get('status', '')
    show_voided = request.GET.get('show_voided', '')

    payrolls = Payroll.objects.select_related('employee').all()
    if not show_voided:
        payrolls = payrolls.filter(voided=False)
    if month_filter:
        payrolls = payrolls.filter(month=month_filter)
    if year_filter:
        payrolls = payrolls.filter(year=year_filter)
    if status_filter:
        payrolls = payrolls.filter(status=status_filter)

    total = sum(p.net_salary for p in payrolls)

    return render(request, 'payroll/list.html', {
        'payrolls': payrolls,
        'month_filter': month_filter,
        'year_filter': year_filter,
        'status_filter': status_filter,
        'show_voided': show_voided,
        'total': total,
        'months': Payroll.MONTH_CHOICES,
    })


@role_required('Manager', 'Accountant')
def payroll_add(request):
    if request.method == 'POST':
        form = PayrollForm(request.POST)
        if form.is_valid():
            payroll = form.save(commit=False)
            payroll.created_by = request.user
            if request.user.is_superuser or request.user.groups.filter(name='Manager').exists():
                payroll.status = 'Approved'
                payroll.save()
                notify_accountants(
                    f'Payroll for {payroll.employee.first_name} {payroll.employee.last_name} '
                    f'({payroll.get_month_display()} {payroll.year}) created by {request.user.username}.',
                    link=f'/payroll/{payroll.pk}/'
                )
                messages.success(request, 'Payroll added.')
            else:
                payroll.status = 'Pending'
                payroll.save()
                notify_managers(
                    f'Payroll for {payroll.employee.first_name} {payroll.employee.last_name} '
                    f'({payroll.get_month_display()} {payroll.year}) created by {request.user.username} is awaiting your approval.',
                    link='/approvals/',
                    status='Pending',
                    object_type='Payroll',
                    object_id=payroll.pk,
                )
                messages.info(request, 'Payroll submitted for manager approval.')
            return redirect('payroll_list')
    else:
        form = PayrollForm()
    return render(request, 'payroll/form.html', {'form': form, 'title': 'Add Payroll'})


# ---------------------------------------------------------------------
# BLOCK 1 - helpers (paste anywhere in the PAYROLL section)
# ---------------------------------------------------------------------
def _is_manager_user(user):
    return user.is_superuser or user.groups.filter(name='Manager').exists()


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _parse_amount(raw, default):
    """Turn form text into a Decimal; use `default` if empty or invalid."""
    from decimal import Decimal, InvalidOperation

    text = str(raw or '').strip()
    if not text:
        return default
    try:
        return Decimal(text)
    except InvalidOperation:
        return default


def _record_payroll_payment(request, payroll, amount, note, photo=None):
    """One place for the payment rules.

    Manager    -> payroll becomes 'Paid' immediately.
    Accountant -> payroll becomes 'Paid Pending' and managers are notified.

    Returns (level, message). level is 'success', 'info', 'warning' or 'error'
    and matches a function in django.contrib.messages.
    """
    from django.utils import timezone

    if payroll.voided:
        return 'error', 'This payroll has been voided and cannot be paid.'
    if payroll.status == 'Paid':
        return 'warning', 'This payroll is already marked as Paid.'
    if payroll.status == 'Paid Pending':
        return 'warning', 'This payment is already waiting for manager approval.'
    if payroll.status != 'Approved':
        return 'error', 'This payroll must be approved by a manager before it can be paid.'
    if not amount.is_finite() or amount <= 0:
        return 'error', 'Amount must be greater than 0.'

    name = f'{payroll.employee.first_name} {payroll.employee.last_name}'
    period = f'{payroll.get_month_display()} {payroll.year}'

    payroll.received_amount = amount
    payroll.confirmation_notes = note
    payroll.paid_from_ip = _client_ip(request)
    payroll.payment_method = 'Cash'
    if photo:
        payroll.signed_slip_photo = photo

    # ----- Manager: final immediately -----
    if _is_manager_user(request.user):
        payroll.status = 'Paid'
        payroll.payment_date = timezone.localdate()
        payroll.paid_by = request.user
        payroll.confirmed_at = timezone.now()
        payroll.employee_confirmed = True
        payroll.save()

        if payroll.created_by and payroll.created_by != request.user:
            create_notification(
                payroll.created_by,
                f'Salary for {name} ({period}) has been PAID by {request.user.username}.',
                link=f'/payroll/{payroll.pk}/',
            )
        return 'success', f'Salary paid to {name}. Amount: PKR {amount}'

    # ----- Accountant: needs manager approval -----
    payroll.status = 'Paid Pending'
    payroll.paid_requested_by = request.user
    payroll.save()

    notify_managers(
        f'Payroll for {name} ({period}) marked as PAID by {request.user.username} '
        f'- awaiting your approval.',
        link='/approvals/',
    )
    return 'info', 'Payment submitted for manager approval.'


# ---------------------------------------------------------------------
# BLOCK 2 - replaces payroll_mark_paid
# (used by the "Paid" button + pop-up on the payroll list and detail pages)
# ---------------------------------------------------------------------
@role_required('Manager', 'Accountant')
def payroll_mark_paid(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method != 'POST':
        return redirect('payroll_list')

    amount = _parse_amount(request.POST.get('received_amount'), payroll.net_salary)
    note = request.POST.get('confirmation_notes', '').strip()

    level, text = _record_payroll_payment(request, payroll, amount, note)
    getattr(messages, level)(request, text)
    return redirect('payroll_list')


# ---------------------------------------------------------------------
# BLOCK 3 - replaces payroll_pay_save
# (the page that uploads the signed slip photo; same rules as above)
# ---------------------------------------------------------------------
@role_required('Manager', 'Accountant')
def payroll_pay_save(request, pk):
    """Handle the confirm-payment POST (with signed slip photo)."""
    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method != 'POST':
        return redirect('payroll_list')

    amount = _parse_amount(request.POST.get('received_amount'), payroll.net_salary)
    note = request.POST.get('confirmation_notes', '').strip()
    photo = request.FILES.get('signed_slip_photo')

    level, text = _record_payroll_payment(request, payroll, amount, note, photo)
    getattr(messages, level)(request, text)
    return redirect('payroll_detail', pk=payroll.pk)


# ---------------------------------------------------------------------
# BLOCK 4 - replaces approve_payroll
# (manager approves a new payroll: Pending -> Approved)
# ---------------------------------------------------------------------
@role_required('Manager')
def approve_payroll(request, pk):
    from django.utils import timezone

    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method == 'POST':
        # Only a payroll that is waiting for approval can be approved.
        # (Stops a re-approval from changing a Paid payroll back to Approved.)
        if payroll.voided or payroll.status != 'Pending':
            messages.warning(request, 'This payroll is not waiting for approval.')
            return redirect('approval_list')

        name = f'{payroll.employee.first_name} {payroll.employee.last_name}'
        period = f'{payroll.get_month_display()} {payroll.year}'

        payroll.status = 'Approved'
        payroll.approved_by = request.user
        payroll.approved_at = timezone.now()
        payroll.save()

        if payroll.created_by:
            create_notification(
                payroll.created_by,
                f'Payroll for {name} ({period}) has been approved by {request.user.username}.',
                link=f'/payroll/{payroll.pk}/',
            )

        # Clear the manager's own "pending" notification for this payroll
        Notification.objects.filter(
            user=request.user,
            object_type='Payroll',
            object_id=payroll.pk,
            status='Pending',
        ).update(
            status='Approved',
            message=f'You approved payroll for {name} ({period}).',
            is_read=True,
        )

        messages.success(request, f'Payroll for {name} approved.')
    return redirect('approval_list')


# ---------------------------------------------------------------------
# BLOCK 5 - replaces approve_payroll_paid
# (manager approves an accountant's payment: Paid Pending -> Paid)
# ---------------------------------------------------------------------
@role_required('Manager')
def approve_payroll_paid(request, pk):
    from django.utils import timezone

    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method == 'POST':
        if payroll.voided or payroll.status != 'Paid Pending':
            messages.warning(request, 'This payment is not waiting for approval.')
            return redirect('approval_list')

        payroll.status = 'Paid'
        payroll.payment_date = timezone.localdate()
        payroll.paid_by = request.user
        payroll.confirmed_at = timezone.now()
        payroll.employee_confirmed = True
        payroll.save()

        if payroll.paid_requested_by:
            create_notification(
                payroll.paid_requested_by,
                f'Payment for {payroll.employee.first_name} {payroll.employee.last_name} '
                f'({payroll.get_month_display()} {payroll.year}) has been approved '
                f'and marked as PAID by {request.user.username}.',
                link=f'/payroll/{payroll.pk}/',
            )
        messages.success(request, 'Payment approved and marked as PAID.')
    return redirect('approval_list')


# ---------------------------------------------------------------------
# BLOCK 6 - replaces payroll_edit
# (Manager only. Paid / waiting-for-approval / voided payrolls are locked.)
# ---------------------------------------------------------------------
@role_required('Manager', 'Accountant')
def payroll_edit(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)

    if payroll.status == 'Paid':
        messages.error(request, 'Paid payrolls cannot be edited. Corrections go in the next month as arrears or adjustment.')
        return redirect('payroll_detail', pk=payroll.pk)

    if payroll.voided:
        messages.error(request, 'Voided payrolls cannot be edited.')
        return redirect('payroll_detail', pk=payroll.pk)

    if request.method == 'POST':
        form = PayrollForm(request.POST, instance=payroll)
        if form.is_valid():
            form.save()
            messages.success(request, 'Payroll updated.')
            return redirect('payroll_list')
    else:
        form = PayrollForm(instance=payroll)
    return render(request, 'payroll/form.html', {'form': form, 'title': 'Edit Payroll'})
@role_required('Manager')
def payroll_void(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)

    if payroll.voided:
        messages.warning(request, 'This payroll is already voided.')
        return redirect('payroll_list')

    if payroll.status == 'Paid':
        messages.error(request, 'Paid payrolls cannot be voided. Corrections go in the next month as arrears or adjustment.')
        return redirect('payroll_list')

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('payroll_void', pk=payroll.pk)

        label = f'{payroll.employee.first_name} {payroll.employee.last_name} — {payroll.get_month_display()} {payroll.year}'
        if void_record(payroll, request.user, reason, request, label):
            messages.success(request, f'Payroll voided: {label}')
        return redirect('payroll_list')

    return render(request, 'shared/void_confirm.html', {
        'title': 'Void Payroll',
        'object_label': f'{payroll.employee.first_name} {payroll.employee.last_name} — {payroll.get_month_display()} {payroll.year}',
        'object_type': 'Payroll',
        'details': [
            ('Employee', f'{payroll.employee.employee_code} — {payroll.employee.first_name} {payroll.employee.last_name}'),
            ('Period', f'{payroll.get_month_display()} {payroll.year}'),
            ('Net Salary', f'PKR {payroll.net_salary}'),
            ('Status', payroll.status),
        ],
        'cancel_url': 'payroll_list',
    })

@role_required('Manager', 'Accountant')
def payroll_detail(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    return render(request, 'payroll/detail.html', {'payroll': payroll})

# ---------- CUSTOMERS ----------
@role_required('Manager', 'Accountant', 'Viewer')
def customer_list(request):
    query = request.GET.get('q', '')
    show_voided = request.GET.get('show_voided', '')

    customers = Customer.objects.all()
    if not show_voided:
        customers = customers.filter(voided=False)

    if query:
        customers = customers.filter(name__icontains=query) | \
                    customers.filter(company__icontains=query) | \
                    customers.filter(phone__icontains=query)

    return render(request, 'sales/customer_list.html', {
        'customers': customers,
        'query': query,
        'show_voided': show_voided,
    })


@role_required('Manager', 'Accountant')
def customer_add(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer added.')
            return redirect('customer_list')
    else:
        form = CustomerForm()
    return render(request, 'sales/customer_form.html', {'form': form, 'title': 'Add Customer'})


@role_required('Manager', 'Accountant')
def customer_edit(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer updated.')
            return redirect('customer_list')
    else:
        form = CustomerForm(instance=customer)
    return render(request, 'sales/customer_form.html', {'form': form, 'title': 'Edit Customer'})


@role_required('Manager')
def customer_void(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if customer.voided:
        messages.warning(request, 'This customer is already voided.')
        return redirect('customer_list')

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('customer_void', pk=customer.pk)

        if void_record(customer, request.user, reason, request, customer.name):
            messages.success(request, f'Customer "{customer.name}" has been voided.')
        return redirect('customer_list')

    return render(request, 'sales/customer_void.html', {'customer': customer})


# ---------- SALES ----------
@role_required('Manager', 'Accountant')
def sale_list(request):
    customer_filter = request.GET.get('customer', '')
    status_filter = request.GET.get('status', '')
    sales = Sale.objects.select_related('customer', 'mine').all()
    if customer_filter:
        sales = sales.filter(customer_id=customer_filter)
    if status_filter:
        sales = sales.filter(payment_status=status_filter)
    total_amount = sum(s.total_amount for s in sales)
    total_paid = sum(s.amount_paid for s in sales)
    total_balance = total_amount - total_paid
    return render(request, 'sales/sale_list.html', {
        'sales': sales,
        'customers': Customer.objects.all(),
        'customer_filter': customer_filter,
        'status_filter': status_filter,
        'total_amount': total_amount,
        'total_paid': total_paid,
        'total_balance': total_balance,
    })


@role_required('Manager', 'Accountant')
def sale_detail(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    return render(request, 'sales/sale_detail.html', {'sale': sale})


@role_required('Manager', 'Accountant')
def sale_add(request):
    from datetime import date as date_today
    from decimal import Decimal

    if request.method == 'POST':
        form = SaleForm(request.POST)
        if form.is_valid():
            sale = form.save(commit=False)
            sale.created_by = request.user
            sale.date = date_today.today()
            sale.dispatch_date = date_today.today()

            # Auto-compute amount_paid based on payment status
            total = (sale.quantity_tons or Decimal('0')) * (sale.price_per_ton or Decimal('0'))
            if sale.payment_status == 'Unpaid':
                sale.amount_paid = Decimal('0')
            elif sale.payment_status == 'Paid':
                sale.amount_paid = total
            else:
                # Partial — use the value from the form
                if sale.amount_paid is None:
                    sale.amount_paid = Decimal('0')

            sale.save()
            messages.success(request, f'Dispatch {sale.dispatch_no} created. Print the slip for the driver.')
            return redirect('sale_slip', pk=sale.pk)
    else:
        initial = {}
        last = Sale.objects.order_by('-created_at').first()
        if last:
            initial['coal_type'] = last.coal_type
            initial['mine'] = last.mine
            initial['price_per_ton'] = last.price_per_ton
            initial['customer'] = last.customer
            initial['truck_no'] = last.truck_no
            initial['driver_name'] = last.driver_name
            initial['driver_phone'] = last.driver_phone
            initial['payment_status'] = last.payment_status
        form = SaleForm(initial=initial)

        # Autocomplete suggestions
    suggestions = {
        'truck_numbers': distinct_values(Sale.objects.filter(voided=False), 'truck_no'),
        'driver_names': distinct_values(Sale.objects.filter(voided=False), 'driver_name'),
        'driver_phones': distinct_values(Sale.objects.filter(voided=False), 'driver_phone'),
    }

    return render(request, 'sales/sale_form.html', {
        'form': form,
        'title': 'New Dispatch',
        'suggestions': suggestions,
    })    
    return render(request, 'sales/sale_form.html', {'form': form, 'title': 'New Dispatch'})
@role_required('Manager', 'Accountant')
def sale_edit(request, pk):
    sale = get_object_or_404(Sale, pk=pk)

    # Locked dispatches can only be edited by managers
    is_manager_user = request.user.is_superuser or request.user.groups.filter(name='Manager').exists()
    if sale.is_locked and not is_manager_user:
        messages.error(request, 'This dispatch is locked and cannot be edited. Contact the manager.')
        return redirect('sale_detail', pk=sale.pk)

    if sale.voided:
        messages.error(request, 'This dispatch has been voided and cannot be edited.')
        return redirect('sale_detail', pk=sale.pk)

    if request.method == 'POST':
        form = SaleForm(request.POST, instance=sale)
        if form.is_valid():
            form.save()
            messages.success(request, 'Dispatch updated.')
            return redirect('sale_list')
    else:
        form = SaleForm(instance=sale)
    return render(request, 'sales/sale_form.html', {'form': form, 'title': 'Edit Dispatch'})


@role_required('Manager')
def sale_delete(request, pk):
    sale = get_object_or_404(Sale, pk=pk)

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('sale_delete', pk=sale.pk)

        sale.voided = True
        sale.voided_by = request.user
        sale.voided_reason = reason
        from django.utils import timezone
        sale.voided_at = timezone.now()
        sale.save()
        messages.success(request, f'Dispatch {sale.dispatch_no} has been voided.')
        return redirect('sale_list')

    return render(request, 'sales/sale_void.html', {'sale': sale})

# ---------- EXCEL EXPORTS ----------
@role_required('Manager', 'Accountant')
def export_employees(request):
    headers = ['Code', 'First Name', 'Last Name', 'Father Name', 'CNIC',
               'Phone', 'Designation', 'Department', 'Shift',
               'Joining Date', 'Salary', 'Status']
    rows = []
    for e in Employee.objects.all():
        rows.append([e.employee_code, e.first_name, e.last_name, e.father_name,
                     e.cnic, e.phone, e.designation, e.department, e.shift,
                     str(e.date_of_joining), float(e.salary), e.status])
    return make_excel_response(f'employees_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_mines(request):
    headers = ['Name', 'Location', 'License No', 'Manager', 'Reserves (tons)', 'Status']
    rows = []
    for m in Mine.objects.all():
        rows.append([m.name, m.location, m.license_no, m.manager_name,
                     float(m.reserves_tons), m.status])
    return make_excel_response(f'mines_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_production(request):
    headers = ['Date', 'Shift', 'Mine', 'Coal Type', 'Quantity (tons)',
               'Overburden', 'Supervisor', 'Workers']
    rows = []
    for r in ProductionRecord.objects.select_related('mine').all():
        rows.append([str(r.date), r.shift, r.mine.name, r.coal_type,
                     float(r.quantity_tons), float(r.overburden_removed),
                     r.supervisor, r.workers_count])
    return make_excel_response(f'production_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_attendance(request):
    headers = ['Date', 'Employee Code', 'Employee Name', 'Shift', 'Status',
               'Check In', 'Check Out', 'Overtime (h)']
    rows = []
    for r in Attendance.objects.select_related('employee').all():
        rows.append([str(r.date), r.employee.employee_code,
                     f'{r.employee.first_name} {r.employee.last_name}',
                     r.shift, r.status,
                     str(r.check_in) if r.check_in else '',
                     str(r.check_out) if r.check_out else '',
                     float(r.overtime_hours)])
    return make_excel_response(f'attendance_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_inventory(request):
    headers = ['Name', 'Category', 'Quantity', 'Unit', 'Reorder Level',
               'Unit Price', 'Location']
    rows = []
    for i in InventoryItem.objects.all():
        rows.append([i.name, i.category, float(i.quantity), i.unit,
                     float(i.reorder_level), float(i.unit_price), i.location])
    return make_excel_response(f'inventory_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_payroll(request):
    headers = ['Employee Code', 'Employee Name', 'Month', 'Year',
               'Basic Salary', 'Present', 'Absent', 'Leave', 'Half Day',
               'Overtime Amount', 'Allowances', 'Deductions', 'Net Salary', 'Status']
    rows = []
    for p in Payroll.objects.select_related('employee').all():
        rows.append([p.employee.employee_code,
                     f'{p.employee.first_name} {p.employee.last_name}',
                     p.get_month_display(), p.year,
                     float(p.basic_salary), p.present_days, p.absent_days,
                     p.leave_days, p.half_days,
                     float(p.overtime_amount), float(p.allowances),
                     float(p.deductions), float(p.net_salary), p.status])
    return make_excel_response(f'payroll_{date.today()}.xlsx', headers, rows)


@role_required('Manager', 'Accountant')
def export_sales(request):
    headers = ['Invoice No', 'Date', 'Customer', 'Mine', 'Coal Type',
               'Quantity (tons)', 'Price/Ton', 'Total', 'Paid', 'Balance', 'Status']
    rows = []
    for s in Sale.objects.select_related('customer', 'mine').all():
        rows.append([s.invoice_no, str(s.date), s.customer.name,
                     s.mine.name if s.mine else '',
                     s.coal_type, float(s.quantity_tons),
                     float(s.price_per_ton), float(s.total_amount),
                     float(s.amount_paid), float(s.balance), s.payment_status])
    return make_excel_response(f'sales_{date.today()}.xlsx', headers, rows)


# ---------- NOTIFICATIONS ----------
def create_notification(user, message, link=''):
    if user and user.is_authenticated:
        Notification.objects.create(user=user, message=message, link=link)


def notify_role(role_name, message, link='', status='Info', object_type='', object_id=None):
    from django.contrib.auth.models import User
    users = User.objects.filter(groups__name=role_name)
    for user in users:
        Notification.objects.create(
            user=user,
            message=message,
            link=link,
            status=status,
            object_type=object_type,
            object_id=object_id,
        )


def notify_accountants(message, link='', status='Info', object_type='', object_id=None):
    notify_role('Accountant', message, link, status, object_type, object_id)


def notify_managers(message, link='', status='Info', object_type='', object_id=None):
    notify_role('Manager', message, link, status, object_type, object_id)

@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user)
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return render(request, 'notifications/list.html', {'notifications': notifications})


# ---------- APPROVALS ----------
@role_required('Manager')
def approval_list(request):
    pending_employees = Employee.objects.filter(approval_status='Pending')
    pending_inventory = InventoryItem.objects.filter(approval_status='Pending')
    pending_payrolls = Payroll.objects.filter(status='Pending')
    pending_paid = Payroll.objects.filter(status='Paid Pending')
    return render(request, 'approvals/list.html', {
        'pending_employees': pending_employees,
        'pending_inventory': pending_inventory,
        'pending_payrolls': pending_payrolls,
        'pending_paid': pending_paid,
    })


@role_required('Manager')
def approve_employee(request, pk):
    from django.utils import timezone
    emp = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        emp.approval_status = 'Approved'
        emp.approved_by = request.user              # ← auto-record who
        emp.approved_at = timezone.now()            # ← auto-record when
        emp.save()
        if emp.added_by:
            create_notification(
                emp.added_by,
                f'Your employee record for {emp.first_name} {emp.last_name} has been approved by {request.user.username}.',
                link=f'/employees/{emp.pk}/'
            )
        ApprovalLog.objects.create(
            object_type='Employee', object_id=emp.pk,
            object_label=f'{emp.first_name} {emp.last_name}',
            requested_by=emp.added_by or request.user,
            status='Approved', reviewed_by=request.user,
        )
        Notification.objects.filter(
            user=request.user,
            object_type='Employee',
            object_id=emp.pk,
            status='Pending',
        ).update(
            status='Approved',
            message=f'You approved employee {emp.first_name} {emp.last_name}.',
            is_read=True,
        )
        messages.success(request, f'Employee {emp.first_name} {emp.last_name} approved.')
    return redirect('approval_list')

@role_required('Manager')
def reject_employee(request, pk):
    emp = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        emp.approval_status = 'Rejected'
        emp.save()
        if emp.added_by:
            create_notification(
                emp.added_by,
                f'Your employee record for {emp.first_name} {emp.last_name} was rejected.',
            )
            Notification.objects.filter(
            user=request.user,
            object_type='Employee',
            object_id=emp.pk,
            status='Pending',
        ).update(
            status='Rejected',
            message=f'You rejected employee {emp.first_name} {emp.last_name}.',
            is_read=True,
        )
        messages.warning(request, f'Employee {emp.first_name} {emp.last_name} rejected.')
    return redirect('approval_list')


@role_required('Manager')
def approve_inventory(request, pk):
    from django.utils import timezone
    item = get_object_or_404(InventoryItem, pk=pk)
    if request.method == 'POST':
        item.approval_status = 'Approved'
        item.approved_by = request.user             # ← auto-record who
        item.approved_at = timezone.now()           # ← auto-record when
        item.save()
        if item.added_by:
            create_notification(
                item.added_by,
                f'Inventory item "{item.name}" has been approved by {request.user.username}.',
                link=f'/inventory/{item.pk}/edit/'
            )
        Notification.objects.filter(
            user=request.user,
            object_type='InventoryItem',
            object_id=item.pk,
            status='Pending',
        ).update(
            status='Approved',
            message=f'You approved inventory item "{item.name}".',
            is_read=True,
        )
        messages.success(request, f'Inventory item "{item.name}" approved.')
    return redirect('approval_list')

@role_required('Manager')
def reject_inventory(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)
    if request.method == 'POST':
        item.approval_status = 'Rejected'
        item.save()
        if item.added_by:
            create_notification(
                item.added_by,
                f'Inventory item "{item.name}" was rejected.',
            )
            Notification.objects.filter(
            user=request.user,
            object_type='InventoryItem',
            object_id=item.pk,
            status='Pending',
        ).update(
            status='Rejected',
            message=f'You rejected inventory item "{item.name}".',
            is_read=True,
        )
        messages.warning(request, f'Inventory item "{item.name}" rejected.')
    return redirect('approval_list')






# ---------- PUNCH IN / OUT ----------
@role_required('Manager', 'Accountant')
def attendance_punch(request):
    employees = Employee.objects.filter(status='Active').order_by('first_name')
    return render(request, 'attendance/punch.html', {'employees': employees})


@role_required('Manager', 'Accountant')
def attendance_punch_save(request, pk):
    from datetime import date

    from django.http import JsonResponse
    from django.utils import timezone

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)

    employee = get_object_or_404(Employee, pk=pk)
    today = date.today()
    now_time = timezone.localtime().time().replace(second=0, microsecond=0)
    photo = request.FILES.get('photo')

    existing = Attendance.objects.filter(employee=employee, date=today).first()

    if not existing:
        Attendance.objects.create(
            employee=employee,
            date=today,
            shift=employee.shift or 'Morning',
            status='Present',
            check_in=now_time,
            photo=photo,
            auto_check_in=False,
        )
        return JsonResponse({
            'status': 'in',
            'time': now_time.strftime('%H:%M'),
            'name': f'{employee.first_name} {employee.last_name}',
            'message': f'{employee.first_name} {employee.last_name} checked IN at {now_time.strftime("%H:%M")}',
        })

    if not existing.check_out:
        existing.check_out = now_time
        if photo:
            existing.photo_out = photo
        existing.save()
        return JsonResponse({
            'status': 'out',
            'time': now_time.strftime('%H:%M'),
            'name': f'{employee.first_name} {employee.last_name}',
            'message': f'{employee.first_name} {employee.last_name} checked OUT at {now_time.strftime("%H:%M")}',
        })

    return JsonResponse({
        'status': 'done',
        'message': f'{employee.first_name} {employee.last_name} has already completed both check-in and check-out today.',
    })

# ---------- BACKUP ----------
@role_required('Manager', 'Accountant')
def backup_now(request):
    import subprocess
    import os
    import shutil
    from django.conf import settings
    from django.utils import timezone
    from datetime import timedelta

    if request.method == 'POST':
        try:
            # Ensure backups folder exists
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)

            # Today's date for the dated file
            today_str = timezone.localtime().strftime('%Y-%m-%d')

            # Backup file paths
            dated_filename = f'coalmining_{today_str}.dump'
            dated_filepath = os.path.join(backup_dir, dated_filename)

            master_filename = 'coalmining_backup.dump'
            master_filepath = os.path.join(backup_dir, master_filename)

            # Find pg_dump path
            pg_dump_path = shutil.which('pg_dump')
            if not pg_dump_path:
                for ver in ['18', '17', '16', '15', '14']:
                    test_path = rf'C:\Program Files\PostgreSQL\{ver}\bin\pg_dump.exe'
                    if os.path.exists(test_path):
                        pg_dump_path = test_path
                        break
            if not pg_dump_path:
                messages.error(request, 'pg_dump.exe not found. Please check PostgreSQL installation path.')
                return redirect('dashboard')

            # Run pg_dump → write to dated file (credentials come from settings.py)
            db = settings.DATABASES['default']
            env = os.environ.copy()
            env['PGPASSWORD'] = str(db.get('PASSWORD', ''))

            result = subprocess.run(
                [
                    pg_dump_path,
                    '-U', db.get('USER') or 'postgres',
                    '-h', db.get('HOST') or 'localhost',
                    '-p', str(db.get('PORT') or '5432'),
                    '-Fc', '-f', dated_filepath,
                    db['NAME'],
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                messages.error(request, f'Backup failed: {result.stderr}')
                return redirect('dashboard')

            # Copy dated file to master (overwrite)
            shutil.copy2(dated_filepath, master_filepath)

            # Auto-cleanup: delete dated files older than 7 days
            cutoff_date = timezone.localdate() - timedelta(days=7)
            removed_count = 0
            for fname in os.listdir(backup_dir):
                if not (fname.startswith('coalmining_') and fname.endswith('.dump')):
                    continue
                if fname == master_filename:
                    continue
                # Extract date from filename like coalmining_2026-10-03.dump
                try:
                    date_str = fname.replace('coalmining_', '').replace('.dump', '')
                    from datetime import datetime
                    file_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if file_date < cutoff_date:
                        os.remove(os.path.join(backup_dir, fname))
                        removed_count += 1
                except (ValueError, OSError):
                    pass

            # Get file size
            size_mb = os.path.getsize(dated_filepath) / (1024 * 1024)

            msg = f'✅ Backup saved: {dated_filename} ({size_mb:.2f} MB)'
            if removed_count > 0:
                msg += f' — cleaned up {removed_count} old backup(s)'

            messages.success(request, msg)
            return redirect('backup_list')

        except subprocess.TimeoutExpired:
            messages.error(request, 'Backup timed out after 2 minutes.')
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f'Backup error: {str(e)}')
            return redirect('dashboard')

    # GET request — show confirmation page
    return render(request, 'backup/confirm.html')

# ---------- BACKUP HISTORY ----------
@role_required('Manager', 'Accountant')
def backup_list(request):
    import os
    from django.conf import settings
    from django.utils import timezone

    backup_dir = os.path.join(settings.BASE_DIR, 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    backups = []
    for fname in os.listdir(backup_dir):
        if not fname.endswith('.dump'):
            continue
        fpath = os.path.join(backup_dir, fname)
        stat = os.stat(fpath)
        backups.append({
            'filename': fname,
            'is_master': fname == 'coalmining_backup.dump',
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'modified': timezone.datetime.fromtimestamp(stat.st_mtime),
            'modified_ts': stat.st_mtime,
        })

    # Sort: master file first, then by date descending
    backups.sort(key=lambda x: (not x['is_master'], -x['modified_ts']))

    total_size = sum(b['size_mb'] for b in backups)
    dated_count = sum(1 for b in backups if not b['is_master'])

    return render(request, 'backup/list.html', {
        'backups': backups,
        'total_size': round(total_size, 2),
        'count': len(backups),
        'dated_count': dated_count,
    })

@role_required('Manager', 'Accountant')
def backup_download(request, filename):
    import os

    from django.conf import settings
    from django.http import FileResponse, Http404

    # Security: prevent path traversal
    if '/' in filename or '\\' in filename or '..' in filename:
        raise Http404("Invalid filename")

    filepath = os.path.join(settings.BASE_DIR, 'backups', filename)
    if not os.path.exists(filepath):
        raise Http404("File not found")

    return FileResponse(
        open(filepath, 'rb'),
        as_attachment=True,
        filename=filename,
    )


# ---------- SALARY PAYMENT CONFIRMATION ----------
@role_required('Manager', 'Accountant')
def payroll_pay_confirm(request, pk):
    """Show the pay & confirm page where manager/accountant uploads signed slip photo."""
    payroll = get_object_or_404(Payroll, pk=pk)
    return render(request, 'payroll/pay_confirm.html', {'payroll': payroll})



@role_required('Manager', 'Accountant')
def payroll_slip(request, pk):
    """Printable salary slip for employee signature/thumbprint."""
    payroll = get_object_or_404(Payroll, pk=pk)
    return render(request, 'payroll/slip.html', {'payroll': payroll})

# ---------- EQUIPMENT ----------
@role_required('Manager', 'Accountant', 'Viewer')
def equipment_list(request):
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    show_voided = request.GET.get('show_voided', '')

    equipment = Equipment.objects.select_related('mine').all()
    if not show_voided:
        equipment = equipment.filter(voided=False)
    if status_filter:
        equipment = equipment.filter(status=status_filter)
    if type_filter:
        equipment = equipment.filter(equipment_type=type_filter)

    return render(request, 'equipment/list.html', {
        'equipment': equipment,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'show_voided': show_voided,
        'type_choices': Equipment.TYPE_CHOICES,
    })

@role_required('Manager', 'Accountant', 'Viewer')
def equipment_detail(request, pk):
    from datetime import date, timedelta
    from django.db.models import Sum

    equipment = get_object_or_404(Equipment, pk=pk)
    logs = equipment.maintenance_logs.all()
    total_cost = sum(log.cost for log in logs)

    # ---------- FUEL USAGE ----------
    fuel_issues = equipment.stock_issues.filter(
        transaction_type='OUT',
        item__category='Fuel',
    ).select_related('item', 'created_by').order_by('-date', '-created_at')

    today = date.today()
    month_start = today.replace(day=1)

    # This month
    this_month_qs = fuel_issues.filter(date__gte=month_start)
    this_month_liters = this_month_qs.aggregate(t=Sum('quantity'))['t'] or 0
    this_month_cost = sum(float(f.quantity) * float(f.item.unit_price) for f in this_month_qs)

    # Last month
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    last_month_qs = fuel_issues.filter(date__gte=last_month_start, date__lte=last_month_end)
    last_month_liters = last_month_qs.aggregate(t=Sum('quantity'))['t'] or 0
    last_month_cost = sum(float(f.quantity) * float(f.item.unit_price) for f in last_month_qs)

    # All time
    total_liters = fuel_issues.aggregate(t=Sum('quantity'))['t'] or 0
    total_fuel_cost = sum(float(f.quantity) * float(f.item.unit_price) for f in fuel_issues)

    return render(request, 'equipment/detail.html', {
        'equipment': equipment,
        'logs': logs,
        'total_cost': total_cost,
        # Fuel stats
        'fuel_issues': fuel_issues[:20],  # last 20 records
        'this_month_liters': this_month_liters,
        'this_month_cost': this_month_cost,
        'last_month_liters': last_month_liters,
        'last_month_cost': last_month_cost,
        'total_liters': total_liters,
        'total_fuel_cost': total_fuel_cost,
    })


@role_required('Manager', 'Accountant')
def equipment_add(request):
    if request.method == 'POST':
        form = EquipmentForm(request.POST, request.FILES)
        if form.is_valid():
            eq = form.save()
            messages.success(request, f'Equipment "{eq.name}" added with code {eq.equipment_code}.')
            return redirect('equipment_list')
    else:
        form = EquipmentForm()
    return render(request, 'equipment/form.html', {'form': form, 'title': 'Add Equipment'})


@role_required('Manager', 'Accountant')
def equipment_edit(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    if request.method == 'POST':
        form = EquipmentForm(request.POST, request.FILES, instance=equipment)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipment updated.')
            return redirect('equipment_detail', pk=equipment.pk)
    else:
        form = EquipmentForm(instance=equipment)
    return render(request, 'equipment/form.html', {'form': form, 'title': 'Edit Equipment'})


@role_required('Manager')
def equipment_void(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    if equipment.voided:
        messages.warning(request, 'This equipment is already voided.')
        return redirect('equipment_list')

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('equipment_void', pk=equipment.pk)

        label = f'{equipment.equipment_code} — {equipment.name}'
        if void_record(equipment, request.user, reason, request, label):
            messages.success(request, f'Equipment voided: {label}')
        return redirect('equipment_list')

    return render(request, 'shared/void_confirm.html', {
        'title': 'Void Equipment',
        'object_label': f'{equipment.equipment_code} — {equipment.name}',
        'object_type': 'Equipment',
        'details': [
            ('Type', equipment.equipment_type),
            ('Model', equipment.model_number or '—'),
            ('Status', equipment.status),
            ('Mine', equipment.mine.name if equipment.mine else '—'),
        ],
        'cancel_url': 'equipment_list',
    })


# ---------- MAINTENANCE ----------
@role_required('Manager', 'Accountant', 'Viewer')
def maintenance_list(request):
    type_filter = request.GET.get('type', '')
    show_voided = request.GET.get('show_voided', '')

    logs = MaintenanceLog.objects.select_related('equipment').all()
    if not show_voided:
        logs = logs.filter(voided=False)
    if type_filter:
        logs = logs.filter(maintenance_type=type_filter)

    total_cost = sum(log.cost for log in logs)

    return render(request, 'equipment/maintenance_list.html', {
        'logs': logs,
        'type_filter': type_filter,
        'show_voided': show_voided,
        'total_cost': total_cost,
        'type_choices': MaintenanceLog.TYPE_CHOICES,
    })


@role_required('Manager', 'Accountant')
def maintenance_add(request):
    equipment_id = request.GET.get('equipment')
    if request.method == 'POST':
        form = MaintenanceLogForm(request.POST)
        if form.is_valid():
            log = form.save()
            # Update equipment status based on maintenance status
            eq = log.equipment
            if log.status == 'In Progress':
                eq.status = 'Under Maintenance'
            elif log.status == 'Completed' and eq.status == 'Under Maintenance':
                eq.status = 'Working'
            eq.save()
            messages.success(request, f'Maintenance log added for {eq.name}.')
            return redirect('equipment_detail', pk=eq.pk)
    else:
        initial = {}
        if equipment_id:
            initial['equipment'] = equipment_id
        form = MaintenanceLogForm(initial=initial)

    return render(request, 'equipment/maintenance_form.html', {
        'form': form, 'title': 'Add Maintenance Log',
    })


@role_required('Manager')
def maintenance_edit(request, pk):
    log = get_object_or_404(MaintenanceLog, pk=pk)
    if request.method == 'POST':
        form = MaintenanceLogForm(request.POST, instance=log)
        if form.is_valid():
            form.save()
            messages.success(request, 'Maintenance log updated.')
            return redirect('equipment_detail', pk=log.equipment.pk)
    else:
        form = MaintenanceLogForm(instance=log)
    return render(request, 'equipment/maintenance_form.html', {
        'form': form, 'title': 'Edit Maintenance Log',
    })


@role_required('Manager')
def maintenance_void(request, pk):
    log = get_object_or_404(MaintenanceLog, pk=pk)
    equipment_pk = log.equipment.pk

    if log.voided:
        messages.warning(request, 'This maintenance log is already voided.')
        return redirect('equipment_detail', pk=equipment_pk)

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('maintenance_void', pk=log.pk)

        label = f'{log.equipment.name} — {log.maintenance_type} on {log.date}'
        if void_record(log, request.user, reason, request, label):
            messages.success(request, f'Maintenance log voided.')
        return redirect('equipment_detail', pk=equipment_pk)

    return render(request, 'equipment/maintenance_void.html', {'log': log})

# ---------- LIVE DISPATCH API ----------
@role_required('Manager', 'Accountant', 'Viewer')
def sales_live_api(request):
    """Returns recent dispatches as JSON for live polling."""
    from datetime import date, timedelta

    from django.http import JsonResponse

    # Show dispatches from the last 24 hours + today
    today = date.today()
    yesterday = today - timedelta(days=1)

    recent = Sale.objects.select_related('customer', 'mine').filter(
        date__gte=yesterday
    ).order_by('-created_at')[:15]

    data = []
    for s in recent:
        data.append({
            'id': s.pk,
            'invoice_no': s.invoice_no,
            'customer': s.customer.name,
            'mine': s.mine.name if s.mine else '',
            'quantity_tons': float(s.quantity_tons),
            'total_amount': float(s.total_amount),
            'truck_no': s.truck_no or '',
            'driver_name': s.driver_name or '',
            'dispatch_date': str(s.dispatch_date) if s.dispatch_date else '',
            'date': str(s.date),
            'payment_status': s.payment_status,
            'created_at': s.created_at.isoformat(),
            'created_at_display': s.created_at.strftime('%H:%M:%S'),
        })

    return JsonResponse({
        'dispatches': data,
        'server_time': today.isoformat(),
        'count': len(data),
    })

# ---------- DISPATCH SLIP ----------
@role_required('Manager', 'Accountant', 'Viewer')
def sale_slip(request, pk):
    """Printable dispatch slip for the driver."""
    sale = get_object_or_404(Sale, pk=pk)
    return render(request, 'sales/slip.html', {'sale': sale})

# ---------- QUICK STOCK IN/OUT ----------
@role_required('Manager', 'Accountant')
def stock_quick_in(request, item_pk):
    """Quick stock-in from the inventory page modal."""
    from datetime import date as date_today
    from decimal import Decimal

    item = get_object_or_404(InventoryItem, pk=item_pk)

    if request.method == 'POST':
        try:
            qty = Decimal(request.POST.get('quantity', '0'))
        except Exception:
            messages.error(request, 'Invalid quantity.')
            return redirect('inventory_list')

        if qty <= 0:
            messages.error(request, 'Quantity must be greater than 0.')
            return redirect('inventory_list')

        item.quantity += qty
        item.save()

        StockTransaction.objects.create(
            item=item,
            date=date_today.today(),
            transaction_type='IN',
            quantity=qty,
            reason=request.POST.get('reason', 'Stock received'),
            handled_by=request.POST.get('handled_by', request.user.username),
            created_by=request.user,
        )
        messages.success(request, f'Added {qty} {item.unit} to {item.name}. New stock: {item.quantity} {item.unit}')

    return redirect('inventory_list')


@role_required('Manager', 'Accountant')
def stock_quick_out(request, item_pk):
    """Quick stock-out from the inventory page modal, with 'issued to'."""
    from datetime import date as date_today
    from decimal import Decimal

    item = get_object_or_404(InventoryItem, pk=item_pk)

    if request.method == 'POST':
        try:
            qty = Decimal(request.POST.get('quantity', '0'))
        except Exception:
            messages.error(request, 'Invalid quantity.')
            return redirect('inventory_list')

        if qty <= 0:
            messages.error(request, 'Quantity must be greater than 0.')
            return redirect('inventory_list')

        if qty > item.quantity:
            messages.error(request, f'Not enough stock. Available: {item.quantity} {item.unit}')
            return redirect('inventory_list')

        issued_to_type = request.POST.get('issued_to_type', 'General')
        eq_id = request.POST.get('issued_to_equipment') or None
        emp_id = request.POST.get('issued_to_employee') or None
        mine_id = request.POST.get('issued_to_mine') or None

        trans = StockTransaction(
            item=item,
            date=date_today.today(),
            transaction_type='OUT',
            quantity=qty,
            reason=request.POST.get('reason', ''),
            issued_to_type=issued_to_type,
            handled_by=request.POST.get('handled_by', request.user.username),
            created_by=request.user,
        )
        if issued_to_type == 'Equipment' and eq_id:
            trans.issued_to_equipment_id = eq_id
        elif issued_to_type == 'Employee' and emp_id:
            trans.issued_to_employee_id = emp_id
        elif issued_to_type == 'Mine' and mine_id:
            trans.issued_to_mine_id = mine_id
        trans.save()

        item.quantity -= qty
        item.save()

        messages.success(request, f'Issued {qty} {item.unit} of {item.name}. New stock: {item.quantity} {item.unit}')

    return redirect('inventory_list')

# ---------- FUEL REPORT ----------
@role_required('Manager', 'Accountant', 'Viewer')
def fuel_report(request):
    from datetime import date, timedelta
    from django.db.models import Sum

    # Filter: default = current month
    month = request.GET.get('month', '')
    year = request.GET.get('year', '')

    today = date.today()
    if month:
        try:
            month_int = int(month)
        except ValueError:
            month_int = today.month
    else:
        month_int = today.month

    if year:
        try:
            year_int = int(year)
        except ValueError:
            year_int = today.year
    else:
        year_int = today.year

    # All fuel transactions for the period
    fuel_txns = StockTransaction.objects.filter(
        transaction_type='OUT',
        item__category='Fuel',
        date__month=month_int,
        date__year=year_int,
    ).select_related('item', 'issued_to_equipment')

    # Group by equipment
    equipment_data = {}
    unassigned_liters = 0
    unassigned_cost = 0

    for txn in fuel_txns:
        liters = float(txn.quantity or 0)
        cost = liters * float(txn.item.unit_price or 0)

        if txn.issued_to_equipment:
            eq = txn.issued_to_equipment
            if eq.pk not in equipment_data:
                equipment_data[eq.pk] = {
                    'equipment': eq,
                    'liters': 0,
                    'cost': 0,
                    'transactions': 0,
                }
            equipment_data[eq.pk]['liters'] += liters
            equipment_data[eq.pk]['cost'] += cost
            equipment_data[eq.pk]['transactions'] += 1
        else:
            unassigned_liters += liters
            unassigned_cost += cost

    # Sort by liters descending
    ranked = sorted(equipment_data.values(), key=lambda x: x['liters'], reverse=True)

    total_liters = sum(e['liters'] for e in ranked) + unassigned_liters
    total_cost = sum(e['cost'] for e in ranked) + unassigned_cost

    # Month options for dropdown
    months = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
    ]

    return render(request, 'equipment/fuel_report.html', {
        'ranked': ranked,
        'month': month_int,
        'year': year_int,
        'months': months,
        'total_liters': total_liters,
        'total_cost': total_cost,
        'unassigned_liters': unassigned_liters,
        'unassigned_cost': unassigned_cost,
        'equipment_count': len(ranked),
    })

# ---------- PAYROLL AUTO-CALC API ----------
@role_required('Manager', 'Accountant')
def payroll_autofill_api(request):
    """Returns an employee's salary + attendance counts for a given month/year,
    only counting dates on/after the employee's joining date."""
    from django.http import JsonResponse
    from decimal import Decimal
    from datetime import date

    employee_id = request.GET.get('employee')
    month = request.GET.get('month')
    year = request.GET.get('year')

    if not all([employee_id, month, year]):
        return JsonResponse({'error': 'Missing params'}, status=400)

    try:
        employee = Employee.objects.get(pk=employee_id)
        month_int = int(month)
        year_int = int(year)
    except (Employee.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Invalid params'}, status=400)

    # Base queryset: this employee, this month/year
    records = Attendance.objects.filter(
        employee=employee,
        date__month=month_int,
        date__year=year_int,
    )

    # Only include dates on/after the employee's joining date
    joining_date = employee.date_of_joining
    if joining_date:
        records = records.filter(date__gte=joining_date)

    present = records.filter(status='Present').count()
    absent = records.filter(status='Absent').count()
    leave = records.filter(status='Leave').count()
    half = records.filter(status='Half Day').count()

    # Sum overtime hours
    overtime_hours = Decimal('0')
    for r in records:
        overtime_hours += (r.overtime_hours or Decimal('0'))

    # Calculate worked days so far (for context)
    from calendar import monthrange
    if joining_date and joining_date.year == year_int and joining_date.month == month_int:
        # Employee joined this month
        days_in_month = monthrange(year_int, month_int)[1]
        eligible_days = days_in_month - joining_date.day + 1
        joined_this_month = True
    elif joining_date and joining_date > date(year_int, month_int, 1):
        # Joined after this month started (in a different month — shouldn't happen)
        eligible_days = 0
        joined_this_month = True
    else:
        # Full month
        eligible_days = monthrange(year_int, month_int)[1]
        joined_this_month = False

    return JsonResponse({
        'basic_salary': float(employee.salary or 0),
        'present_days': present,
        'absent_days': absent,
        'leave_days': leave,
        'half_days': half,
        'overtime_hours': float(overtime_hours),
        'employee_name': f'{employee.first_name} {employee.last_name}',
        'employee_code': employee.employee_code,
        'joining_date': str(joining_date) if joining_date else '',
        'joined_this_month': joined_this_month,
        'eligible_days': eligible_days,
        'total_attendance_records': records.count(),
    })

# ---------- REPORTS HUB ----------
@role_required('Manager', 'Accountant')
def reports_hub(request):
    return render(request, 'reports/hub.html')

# ---------- REPORT STUBS (to be implemented) ----------
@role_required('Manager', 'Accountant')
def report_sales(request):
    from datetime import date, timedelta
    from calendar import month_abbr
    from django.db.models import Sum

    # ---- Filters ----
    today = date.today()
    month_str = request.GET.get('month', '')
    year_str = request.GET.get('year', '')
    customer_filter = request.GET.get('customer', '')

    try:
        month = int(month_str) if month_str else today.month
    except ValueError:
        month = today.month
    try:
        year = int(year_str) if year_str else today.year
    except ValueError:
        year = today.year

    # ---- Sales for the period ----
    sales_qs = Sale.objects.filter(
        voided=False,
        date__year=year,
        date__month=month,
    ).select_related('customer', 'mine')

    if customer_filter:
        sales_qs = sales_qs.filter(customer_id=customer_filter)

    total_sales = sum(s.total_amount for s in sales_qs) or 0
    total_received = sum(s.amount_paid for s in sales_qs) or 0
    total_outstanding = total_sales - total_received
    total_tons = sum(s.quantity_tons for s in sales_qs) or 0
    dispatch_count = sales_qs.count()

    # ---- Previous month for trend ----
    prev_month = month - 1
    prev_year = year
    if prev_month <= 0:
        prev_month = 12
        prev_year -= 1

    prev_qs = Sale.objects.filter(voided=False, date__year=prev_year, date__month=prev_month)
    prev_total = sum(s.total_amount for s in prev_qs) or 0

    if prev_total > 0:
        trend_pct = round(((float(total_sales) - float(prev_total)) / float(prev_total)) * 100, 1)
    else:
        trend_pct = None

    # ---- By Customer ----
    customer_totals = {}
    for s in sales_qs:
        name = s.customer.name
        if name not in customer_totals:
            customer_totals[name] = {'sales': 0, 'received': 0, 'tons': 0, 'count': 0}
        customer_totals[name]['sales'] += float(s.total_amount)
        customer_totals[name]['received'] += float(s.amount_paid)
        customer_totals[name]['tons'] += float(s.quantity_tons)
        customer_totals[name]['count'] += 1

    customer_list = sorted(customer_totals.items(), key=lambda x: x[1]['sales'], reverse=True)

    # ---- By Mine ----
    mine_totals = {}
    for s in sales_qs:
        name = s.mine.name if s.mine else 'Unassigned'
        if name not in mine_totals:
            mine_totals[name] = {'sales': 0, 'tons': 0, 'count': 0}
        mine_totals[name]['sales'] += float(s.total_amount)
        mine_totals[name]['tons'] += float(s.quantity_tons)
        mine_totals[name]['count'] += 1

    mine_list = sorted(mine_totals.items(), key=lambda x: x[1]['sales'], reverse=True)

    # ---- By Payment Status ----
    paid_count = sales_qs.filter(payment_status='Paid').count()
    partial_count = sales_qs.filter(payment_status='Partial').count()
    unpaid_count = sales_qs.filter(payment_status='Unpaid').count()

    paid_amount = sum(s.total_amount for s in sales_qs if s.payment_status == 'Paid') or 0
    partial_amount = sum(s.total_amount for s in sales_qs if s.payment_status == 'Partial') or 0
    unpaid_amount = sum(s.total_amount for s in sales_qs if s.payment_status == 'Unpaid') or 0

    # ---- By Day (for chart) ----
    from calendar import monthrange
    days_in_month = monthrange(year, month)[1]
    daily_labels = []
    daily_data = []
    for d in range(1, days_in_month + 1):
        daily_labels.append(str(d))
        day_total = sum(s.total_amount for s in sales_qs.filter(date__day=d))
        daily_data.append(float(day_total))

    # ---- All dispatches ----
    all_dispatches = list(sales_qs.order_by('-date'))

    context = {
        'month': month,
        'year': year,
        'month_name': month_abbr[month],
        'now': today,
        'months': Payroll.MONTH_CHOICES,  # reuse
        'customer_filter': customer_filter,
        'all_customers': Customer.objects.filter(voided=False),

        'total_sales': total_sales,
        'total_received': total_received,
        'total_outstanding': total_outstanding,
        'total_tons': total_tons,
        'dispatch_count': dispatch_count,
        'trend_pct': trend_pct,

        'customer_list': customer_list,
        'mine_list': mine_list,

        'paid_count': paid_count,
        'partial_count': partial_count,
        'unpaid_count': unpaid_count,
        'paid_amount': paid_amount,
        'partial_amount': partial_amount,
        'unpaid_amount': unpaid_amount,

        'daily_labels': daily_labels,
        'daily_data': daily_data,

        'all_dispatches': all_dispatches,
    }
    return render(request, 'reports/sales.html', context)

@role_required('Manager', 'Accountant')
def report_production(request):
    from datetime import date
    from calendar import month_abbr, monthrange
    from decimal import Decimal

    today = date.today()
    month_str = request.GET.get('month', '')
    year_str = request.GET.get('year', '')
    mine_filter = request.GET.get('mine', '')

    try:
        month = int(month_str) if month_str else today.month
    except ValueError:
        month = today.month
    try:
        year = int(year_str) if year_str else today.year
    except ValueError:
        year = today.year

    # Production records for the period
    records = ProductionRecord.objects.filter(
        voided=False,
        date__year=year,
        date__month=month,
    ).select_related('mine')

    if mine_filter:
        records = records.filter(mine_id=mine_filter)

    total_tons = sum(r.quantity_tons for r in records) or Decimal('0')
    total_overburden = sum(r.overburden_removed for r in records) or Decimal('0')
    total_workers = sum(r.workers_count or 0 for r in records)
    record_count = records.count()

    # Previous month for trend
    prev_month = month - 1
    prev_year = year
    if prev_month <= 0:
        prev_month = 12
        prev_year -= 1
    prev_total = sum(
        r.quantity_tons for r in ProductionRecord.objects.filter(
            voided=False, date__year=prev_year, date__month=prev_month
        )
    ) or Decimal('0')

    trend_pct = None
    if prev_total > 0:
        trend_pct = round(((float(total_tons) - float(prev_total)) / float(prev_total)) * 100, 1)

    # By Mine
    mine_totals = {}
    for r in records:
        name = r.mine.name
        if name not in mine_totals:
            mine_totals[name] = {'tons': 0, 'overburden': 0, 'records': 0, 'workers': 0}
        mine_totals[name]['tons'] += float(r.quantity_tons)
        mine_totals[name]['overburden'] += float(r.overburden_removed)
        mine_totals[name]['records'] += 1
        mine_totals[name]['workers'] += r.workers_count or 0
    mine_list = sorted(mine_totals.items(), key=lambda x: x[1]['tons'], reverse=True)

    # By Shift
    shift_totals = {}
    for r in records:
        s = r.shift
        if s not in shift_totals:
            shift_totals[s] = {'tons': 0, 'count': 0}
        shift_totals[s]['tons'] += float(r.quantity_tons)
        shift_totals[s]['count'] += 1
    shift_list = sorted(shift_totals.items(), key=lambda x: x[1]['tons'], reverse=True)

    # By Coal Type
    coal_totals = {}
    for r in records:
        c = r.coal_type
        if c not in coal_totals:
            coal_totals[c] = {'tons': 0, 'count': 0}
        coal_totals[c]['tons'] += float(r.quantity_tons)
        coal_totals[c]['count'] += 1
    coal_list = sorted(coal_totals.items(), key=lambda x: x[1]['tons'], reverse=True)

    # Daily production for chart
    days_in_month = monthrange(year, month)[1]
    daily_labels = []
    daily_tons = []
    daily_overburden = []
    for d in range(1, days_in_month + 1):
        daily_labels.append(str(d))
        day_records = records.filter(date__day=d)
        tons = sum(r.quantity_tons for r in day_records) or 0
        ob = sum(r.overburden_removed for r in day_records) or 0
        daily_tons.append(float(tons))
        daily_overburden.append(float(ob))

    # Striping ratio = overburden / coal
    if total_tons > 0:
        stripping_ratio = round(float(total_overburden) / float(total_tons), 2)
    else:
        stripping_ratio = 0

    context = {
        'month': month,
        'year': year,
        'month_name': month_abbr[month],
        'months': Payroll.MONTH_CHOICES,
        'mine_filter': mine_filter,
        'all_mines': Mine.objects.filter(voided=False),
        'now': today,
        'total_tons': total_tons,
        'total_overburden': total_overburden,
        'total_workers': total_workers,
        'record_count': record_count,
        'trend_pct': trend_pct,
        'stripping_ratio': stripping_ratio,

        'mine_list': mine_list,
        'shift_list': shift_list,
        'coal_list': coal_list,

        'daily_labels': daily_labels,
        'daily_tons': daily_tons,
        'daily_overburden': daily_overburden,
    }
    return render(request, 'reports/production.html', context)

@role_required('Manager', 'Accountant')
def report_payroll(request):
    from datetime import date
    from calendar import month_abbr
    from decimal import Decimal

    today = date.today()
    month_str = request.GET.get('month', '')
    year_str = request.GET.get('year', '')
    status_filter = request.GET.get('status', '')

    try:
        month = int(month_str) if month_str else today.month
    except ValueError:
        month = today.month
    try:
        year = int(year_str) if year_str else today.year
    except ValueError:
        year = today.year

    payrolls = Payroll.objects.filter(
        voided=False,
        year=year,
        month=month,
    ).select_related('employee')

    if status_filter:
        payrolls = payrolls.filter(status=status_filter)

    total_basic = sum(p.basic_salary for p in payrolls) or Decimal('0')
    total_overtime = sum(p.overtime_amount for p in payrolls) or Decimal('0')
    total_allowances = sum(p.allowances for p in payrolls) or Decimal('0')
    total_deductions = sum(p.deductions for p in payrolls) or Decimal('0')
    total_net = sum(p.net_salary for p in payrolls) or Decimal('0')
    total_overtime_hours = sum(p.overtime_hours for p in payrolls) or Decimal('0')
    employee_count = payrolls.count()

    # By status
    paid_count = payrolls.filter(status='Paid').count()
    pending_count = payrolls.filter(status='Pending').count()
    approved_count = payrolls.filter(status='Approved').count()
    paid_amount = sum(p.net_salary for p in payrolls if p.status == 'Paid') or Decimal('0')
    approved_amount = sum(p.net_salary for p in payrolls if p.status == 'Approved') or Decimal('0')
    pending_amount = sum(p.net_salary for p in payrolls if p.status == 'Pending') or Decimal('0')

    # Previous month for trend
    prev_month = month - 1
    prev_year = year
    if prev_month <= 0:
        prev_month = 12
        prev_year -= 1

    prev_total = sum(
        p.net_salary for p in Payroll.objects.filter(voided=False, year=prev_year, month=prev_month)
    ) or Decimal('0')

    trend_pct = None
    if prev_total > 0:
        trend_pct = round(((float(total_net) - float(prev_total)) / float(prev_total)) * 100, 1)

    # By department
    dept_totals = {}
    for p in payrolls:
        d = p.employee.department or 'Unassigned'
        if d not in dept_totals:
            dept_totals[d] = {'net': 0, 'count': 0, 'overtime': 0}
        dept_totals[d]['net'] += float(p.net_salary)
        dept_totals[d]['count'] += 1
        dept_totals[d]['overtime'] += float(p.overtime_amount)
    dept_list = sorted(dept_totals.items(), key=lambda x: x[1]['net'], reverse=True)

    context = {
        'month': month,
        'year': year,
        'month_name': month_abbr[month],
                'now': today,
        'months': Payroll.MONTH_CHOICES,
        'status_filter': status_filter,

        'total_basic': total_basic,
        'total_overtime': total_overtime,
        'total_allowances': total_allowances,
        'total_deductions': total_deductions,
        'total_net': total_net,
        'total_overtime_hours': total_overtime_hours,
        'employee_count': employee_count,
        'trend_pct': trend_pct,

        'paid_count': paid_count,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'paid_amount': paid_amount,
        'approved_amount': approved_amount,
        'pending_amount': pending_amount,

        'dept_list': dept_list,
        'payrolls': payrolls.order_by('employee__employee_code'),
    }
    return render(request, 'reports/payroll.html', context)

@role_required('Manager', 'Accountant')
def report_inventory(request):
    from datetime import date
    from calendar import month_abbr
    from decimal import Decimal

    today = date.today()
    month_str = request.GET.get('month', '')
    year_str = request.GET.get('year', '')

    try:
        month = int(month_str) if month_str else today.month
    except ValueError:
        month = today.month
    try:
        year = int(year_str) if year_str else today.year
    except ValueError:
        year = today.year

    # Current stock status (all non-voided items)
    all_items = list(InventoryItem.objects.filter(voided=False))
    total_items = len(all_items)
    total_value = sum(float(i.quantity) * float(i.unit_price) for i in all_items)
    low_stock_items = [i for i in all_items if i.is_low_stock]
    low_stock_count = len(low_stock_items)

    # Transactions for the period
    transactions = StockTransaction.objects.filter(
        date__year=year,
        date__month=month,
    ).select_related('item', 'issued_to_equipment', 'issued_to_employee', 'issued_to_mine')

    total_in = Decimal('0')
    total_out = Decimal('0')
    in_value = Decimal('0')
    out_value = Decimal('0')

    for t in transactions:
        if t.transaction_type == 'IN':
            total_in += t.quantity
            in_value += (t.quantity * (t.item.unit_price or 0))
        else:
            total_out += t.quantity
            out_value += (t.quantity * (t.item.unit_price or 0))

    transaction_count = transactions.count()

    # By Category (current stock)
    category_data = {}
    for item in all_items:
        cat = item.category
        if cat not in category_data:
            category_data[cat] = {'items': 0, 'value': 0, 'qty': 0}
        category_data[cat]['items'] += 1
        category_data[cat]['value'] += float(item.quantity) * float(item.unit_price)
        category_data[cat]['qty'] += float(item.quantity)
    category_list = sorted(category_data.items(), key=lambda x: x[1]['value'], reverse=True)

    # By Category (movements in period)
    movement_by_category = {}
    for t in transactions:
        cat = t.item.category
        if cat not in movement_by_category:
            movement_by_category[cat] = {'in': 0, 'out': 0, 'in_val': 0, 'out_val': 0}
        if t.transaction_type == 'IN':
            movement_by_category[cat]['in'] += float(t.quantity)
            movement_by_category[cat]['in_val'] += float(t.quantity) * float(t.item.unit_price or 0)
        else:
            movement_by_category[cat]['out'] += float(t.quantity)
            movement_by_category[cat]['out_val'] += float(t.quantity) * float(t.item.unit_price or 0)
    movement_cat_list = sorted(movement_by_category.items(), key=lambda x: x[1]['in_val'] + x[1]['out_val'], reverse=True)

    # Fuel consumed by equipment (only OUT transactions of Fuel category)
    fuel_usage = {}
    fuel_txns = transactions.filter(transaction_type='OUT', item__category='Fuel')
    for t in fuel_txns:
        if t.issued_to_equipment:
            eq_name = f"{t.issued_to_equipment.equipment_code} — {t.issued_to_equipment.name}"
            if eq_name not in fuel_usage:
                fuel_usage[eq_name] = {'liters': 0, 'cost': 0}
            fuel_usage[eq_name]['liters'] += float(t.quantity)
            fuel_usage[eq_name]['cost'] += float(t.quantity) * float(t.item.unit_price or 0)
    fuel_list = sorted(fuel_usage.items(), key=lambda x: x[1]['liters'], reverse=True)

    # Previous month for trend
    prev_month = month - 1
    prev_year = year
    if prev_month <= 0:
        prev_month = 12
        prev_year -= 1

    prev_out = sum(
        t.quantity for t in StockTransaction.objects.filter(
            transaction_type='OUT', date__year=prev_year, date__month=prev_month
        )
    ) or Decimal('0')

    trend_pct = None
    if prev_out > 0:
        trend_pct = round(((float(total_out) - float(prev_out)) / float(prev_out)) * 100, 1)

    context = {
        'month': month,
        'year': year,
        'month_name': month_abbr[month],
        'months': Payroll.MONTH_CHOICES,
        'now': today,

        'total_items': total_items,
        'total_value': total_value,
        'low_stock_count': low_stock_count,
        'low_stock_items': low_stock_items,

        'total_in': total_in,
        'total_out': total_out,
        'in_value': in_value,
        'out_value': out_value,
        'transaction_count': transaction_count,
        'trend_pct': trend_pct,

        'category_list': category_list,
        'movement_cat_list': movement_cat_list,
        'fuel_list': fuel_list,

        'transactions': transactions.order_by('-date', '-created_at'),
    }
    return render(request, 'reports/inventory.html', context)

@role_required('Manager', 'Accountant')
def report_attendance(request):
    from datetime import date
    from calendar import month_abbr
    from django.db.models import Count

    today = date.today()
    month_str = request.GET.get('month', '')
    year_str = request.GET.get('year', '')

    try:
        month = int(month_str) if month_str else today.month
    except ValueError:
        month = today.month
    try:
        year = int(year_str) if year_str else today.year
    except ValueError:
        year = today.year

    records = Attendance.objects.filter(
        voided=False,
        date__year=year,
        date__month=month,
    ).select_related('employee')

    total = records.count()
    present = records.filter(status='Present').count()
    absent = records.filter(status='Absent').count()
    leave = records.filter(status='Leave').count()
    half = records.filter(status='Half Day').count()

    total_overtime = sum(r.overtime_hours or 0 for r in records)

    # Percentages
    def pct(n, total):
        return round((n / total) * 100, 1) if total else 0

    present_pct = pct(present, total)
    absent_pct = pct(absent, total)
    leave_pct = pct(leave, total)
    half_pct = pct(half, total)

    # By Department
    dept_data = {}
    for r in records:
        d = r.employee.department or 'Unassigned'
        if d not in dept_data:
            dept_data[d] = {'present': 0, 'absent': 0, 'leave': 0, 'half': 0, 'total': 0, 'overtime': 0}
        dept_data[d]['total'] += 1
        dept_data[d]['overtime'] += float(r.overtime_hours or 0)
        if r.status == 'Present':
            dept_data[d]['present'] += 1
        elif r.status == 'Absent':
            dept_data[d]['absent'] += 1
        elif r.status == 'Leave':
            dept_data[d]['leave'] += 1
        elif r.status == 'Half Day':
            dept_data[d]['half'] += 1
    for d in dept_data:
        dept_data[d]['present_pct'] = pct(dept_data[d]['present'], dept_data[d]['total'])
    dept_list = sorted(dept_data.items(), key=lambda x: x[1]['total'], reverse=True)

    # By Employee (summary)
    emp_data = {}
    for r in records:
        key = r.employee.pk
        if key not in emp_data:
            emp_data[key] = {
                'code': r.employee.employee_code,
                'name': f'{r.employee.first_name} {r.employee.last_name}',
                'department': r.employee.department,
                'present': 0, 'absent': 0, 'leave': 0, 'half': 0,
                'total': 0, 'overtime': 0,
            }
        emp_data[key]['total'] += 1
        emp_data[key]['overtime'] += float(r.overtime_hours or 0)
        if r.status == 'Present':
            emp_data[key]['present'] += 1
        elif r.status == 'Absent':
            emp_data[key]['absent'] += 1
        elif r.status == 'Leave':
            emp_data[key]['leave'] += 1
        elif r.status == 'Half Day':
            emp_data[key]['half'] += 1

    emp_list = []
    for data in emp_data.values():
        data['present_pct'] = pct(data['present'], data['total'])
        emp_list.append(data)
    emp_list.sort(key=lambda x: x['present_pct'], reverse=True)

    # Previous month trend
    prev_month = month - 1
    prev_year = year
    if prev_month <= 0:
        prev_month = 12
        prev_year -= 1
    prev_present = Attendance.objects.filter(
        voided=False, date__year=prev_year, date__month=prev_month, status='Present'
    ).count()

    trend_pct = None
    if prev_present > 0:
        trend_pct = round(((present - prev_present) / prev_present) * 100, 1)

    context = {
        'month': month,
        'year': year,
        'month_name': month_abbr[month],
        'months': Payroll.MONTH_CHOICES,
        'now': today,

        'total': total,
        'present': present,
        'absent': absent,
        'leave': leave,
        'half': half,
        'present_pct': present_pct,
        'absent_pct': absent_pct,
        'leave_pct': leave_pct,
        'half_pct': half_pct,
        'total_overtime': total_overtime,
        'trend_pct': trend_pct,

        'dept_list': dept_list,
        'emp_list': emp_list,
    }
    return render(request, 'reports/attendance.html', context)

@role_required('Manager', 'Accountant')
def report_equipment(request):
    from datetime import date
    from calendar import month_abbr

    today = date.today()
    month_str = request.GET.get('month', '')
    year_str = request.GET.get('year', '')

    try:
        month = int(month_str) if month_str else today.month
    except ValueError:
        month = today.month
    try:
        year = int(year_str) if year_str else today.year
    except ValueError:
        year = today.year

    # Equipment counts
    all_equipment = Equipment.objects.filter(voided=False)
    total_equipment = all_equipment.count()
    working = all_equipment.filter(status='Working').count()
    under_maint = all_equipment.filter(status='Under Maintenance').count()
    out_of_service = all_equipment.filter(status='Out of Service').count()

    # Maintenance logs for the period
    logs = MaintenanceLog.objects.filter(
        voided=False,
        date__year=year,
        date__month=month,
    ).select_related('equipment')

    total_logs = logs.count()
    total_maint_cost = sum(log.cost for log in logs)

    # By type
    maint_by_type = {}
    for log in logs:
        t = log.maintenance_type
        if t not in maint_by_type:
            maint_by_type[t] = {'count': 0, 'cost': 0}
        maint_by_type[t]['count'] += 1
        maint_by_type[t]['cost'] += float(log.cost)
    type_list = sorted(maint_by_type.items(), key=lambda x: x[1]['cost'], reverse=True)

    # Per equipment
    eq_data = {}
    for eq in all_equipment:
        eq_logs = logs.filter(equipment=eq)
        total_cost = sum(log.cost for log in eq_logs)
        eq_data[eq.pk] = {
            'code': eq.equipment_code,
            'name': eq.name,
            'type': eq.equipment_type,
            'status': eq.status,
            'mine': eq.mine.name if eq.mine else '—',
            'logs': eq_logs.count(),
            'cost': float(total_cost),
        }
    eq_list = sorted(eq_data.values(), key=lambda x: x['cost'], reverse=True)

    # Equipment by status
    status_list = [
        ('Working', working),
        ('Under Maintenance', under_maint),
        ('Out of Service', out_of_service),
    ]

    context = {
        'month': month,
        'year': year,
        'month_name': month_abbr[month],
        'months': Payroll.MONTH_CHOICES,
        'now': today,

        'total_equipment': total_equipment,
        'working': working,
        'under_maint': under_maint,
        'out_of_service': out_of_service,

        'total_logs': total_logs,
        'total_maint_cost': total_maint_cost,

        'type_list': type_list,
        'eq_list': eq_list,
        'status_list': status_list,
    }
    return render(request, 'reports/equipment.html', context)

# ---------- CUSTOMER AUTOFILL API ----------
@role_required('Manager', 'Accountant')
def customer_autofill_api(request, pk):
    from django.http import JsonResponse

    try:
        customer = Customer.objects.get(pk=pk)
    except Customer.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    return JsonResponse({
        'coal_type': customer.default_coal_type or '',
        'rate': float(customer.default_rate) if customer.default_rate else '',
        'truck_no': customer.default_truck_no or '',
        'driver_name': customer.default_driver_name or '',
        'driver_phone': customer.default_driver_phone or '',
        'mine_id': customer.default_mine.pk if customer.default_mine else '',
    })

# ---------- GLOBAL SEARCH ----------
@role_required('Manager', 'Accountant', 'Viewer')
def global_search(request):
    from django.http import JsonResponse
    from django.db.models import Q

    q = request.GET.get('q', '').strip()

    if len(q) < 2:
        return JsonResponse({'results': [], 'query': q})

    results = []
    user_roles = set(request.user.groups.values_list('name', flat=True))
    is_viewer_only = (user_roles == {'Viewer'}) and not request.user.is_superuser

    # ---------- EMPLOYEES (not for Viewer) ----------
    if not is_viewer_only:
        for e in Employee.objects.filter(voided=False).filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(employee_code__icontains=q) |
            Q(cnic__icontains=q) |
            Q(phone__icontains=q)
        )[:5]:
            results.append({
                'type': 'Employee',
                'icon': 'bi-person-badge',
                'label': f'{e.employee_code} — {e.first_name} {e.last_name}',
                'sublabel': e.designation,
                'url': f'/employees/{e.pk}/',
            })

    # ---------- CUSTOMERS ----------
    for c in Customer.objects.filter(voided=False).filter(
        Q(name__icontains=q) |
        Q(company__icontains=q) |
        Q(phone__icontains=q)
    )[:5]:
        results.append({
            'type': 'Customer',
            'icon': 'bi-person-vcard',
            'label': c.name,
            'sublabel': c.company or c.phone or 'Customer',
            'url': f'/customers/{c.pk}/edit/' if not is_viewer_only else '/customers/',
        })

    # ---------- DISPATCHES / SALES ----------
    for s in Sale.objects.filter(voided=False).filter(
        Q(dispatch_no__icontains=q) |
        Q(invoice_no__icontains=q) |
        Q(truck_no__icontains=q) |
        Q(driver_name__icontains=q) |
        Q(customer__name__icontains=q)
    ).select_related('customer')[:5]:
        results.append({
            'type': 'Dispatch',
            'icon': 'bi-receipt',
            'label': s.dispatch_no or s.invoice_no,
            'sublabel': f'{s.customer.name} — {s.quantity_tons} tons',
            'url': f'/sales/{s.pk}/',
        })

    # ---------- MINES (not for Viewer) ----------
    if not is_viewer_only:
        for m in Mine.objects.filter(voided=False).filter(
            Q(name__icontains=q) |
            Q(location__icontains=q)
        )[:4]:
            results.append({
                'type': 'Mine',
                'icon': 'bi-geo-alt-fill',
                'label': m.name,
                'sublabel': m.location,
                'url': f'/mines/{m.pk}/edit/',
            })

    # ---------- EQUIPMENT ----------
    for eq in Equipment.objects.filter(voided=False).filter(
        Q(equipment_code__icontains=q) |
        Q(name__icontains=q) |
        Q(serial_number__icontains=q) |
        Q(model_number__icontains=q)
    )[:4]:
        results.append({
            'type': 'Equipment',
            'icon': 'bi-tools',
            'label': f'{eq.equipment_code} — {eq.name}',
            'sublabel': eq.equipment_type,
            'url': f'/equipment/{eq.pk}/',
        })

    # ---------- INVENTORY ITEMS ----------
    for i in InventoryItem.objects.filter(voided=False).filter(
        Q(name__icontains=q) |
        Q(location__icontains=q)
    )[:4]:
        results.append({
            'type': 'Item',
            'icon': 'bi-box-seam',
            'label': i.name,
            'sublabel': f'{i.quantity} {i.unit} — {i.category}',
            'url': f'/inventory/{i.pk}/edit/' if not is_viewer_only else '/inventory/',
        })

    return JsonResponse({'results': results, 'query': q})

# ---------- SALE PAYMENT ----------
@role_required('Manager', 'Accountant')
def sale_add_payment(request, pk):
    from datetime import date as date_today
    from decimal import Decimal

    sale = get_object_or_404(Sale, pk=pk)

    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0'))
        except Exception:
            messages.error(request, 'Invalid amount.')
            return redirect('sale_detail', pk=sale.pk)

        if amount <= 0:
            messages.error(request, 'Amount must be greater than 0.')
            return redirect('sale_detail', pk=sale.pk)

        balance = (sale.total_amount or 0) - (sale.amount_paid or 0)
        if amount > balance:
            messages.error(request, f'Amount exceeds outstanding balance (PKR {balance}).')
            return redirect('sale_detail', pk=sale.pk)

        # Create payment record
        SalePayment.objects.create(
            sale=sale,
            date=date_today.today(),
            amount=amount,
            method=request.POST.get('method', 'Cash'),
            reference_no=request.POST.get('reference_no', ''),
            notes=request.POST.get('notes', ''),
            received_by=request.user,
        )

        # Update sale totals
        sale.amount_paid = (sale.amount_paid or 0) + amount
        new_balance = (sale.total_amount or 0) - sale.amount_paid

        if new_balance <= 0:
            sale.payment_status = 'Paid'
        elif sale.amount_paid > 0:
            sale.payment_status = 'Partial'

        sale.save()

        messages.success(request, f'Payment of PKR {amount} recorded. Balance: PKR {new_balance}')

    return redirect('sale_detail', pk=sale.pk)


@role_required('Manager', 'Accountant')
def sale_payment_delete(request, pk):
    """Delete a payment (reverses the balance). Manager only."""
    if not (request.user.is_superuser or request.user.groups.filter(name='Manager').exists()):
        messages.error(request, 'Only managers can delete payments.')
        return redirect('sale_list')

    payment = get_object_or_404(SalePayment, pk=pk)
    sale = payment.sale

    if request.method == 'POST':
        sale.amount_paid = (sale.amount_paid or 0) - payment.amount
        if sale.amount_paid <= 0:
            sale.amount_paid = 0
            sale.payment_status = 'Unpaid'
        elif sale.amount_paid < sale.total_amount:
            sale.payment_status = 'Partial'
        else:
            sale.payment_status = 'Paid'
        sale.save()

        payment.delete()
        messages.success(request, f'Payment of PKR {payment.amount} removed.')

    return redirect('sale_detail', pk=sale.pk)