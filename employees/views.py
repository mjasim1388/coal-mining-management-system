from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

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
                     Equipment, MaintenanceLog, VoidLog)
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

# ---------- DASHBOARD ----------
@role_required('Manager', 'Accountant', 'Viewer')
def dashboard(request):
    from datetime import date, timedelta
    from decimal import Decimal

    # Check role
    user_roles = set(request.user.groups.values_list('name', flat=True))
    is_viewer_only = (user_roles == {'Viewer'}) and not request.user.is_superuser

    today = date.today()
    this_month_start = today.replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    # ---------- VIEWER DASHBOARD (SALES ONLY) ----------
    if is_viewer_only:
        sales = Sale.objects.filter(voided=False)
        this_month_sales = sales.filter(date__gte=this_month_start)
        last_month_sales = sales.filter(date__gte=last_month_start, date__lte=last_month_end)

        total_sales = sum(s.total_amount for s in sales)
        total_received = sum(s.amount_paid for s in sales)
        total_outstanding = total_sales - total_received
        total_tons_sold = sum(s.quantity_tons for s in sales)

        tm_sales = sum(s.total_amount for s in this_month_sales)
        lm_sales = sum(s.total_amount for s in last_month_sales)
        tm_tons = sum(s.quantity_tons for s in this_month_sales)

        recent_sales = sales.order_by('-date')[:10]

        trend_labels, trend_data = [], []
        for i in range(29, -1, -1):
            d = today - timedelta(days=i)
            amount = sum(s.total_amount for s in Sale.objects.filter(date=d, voided=False))
            trend_labels.append(d.strftime('%d %b'))
            trend_data.append(float(amount))

        customer_totals = {}
        for s in sales:
            customer_totals[s.customer.name] = customer_totals.get(s.customer.name, 0) + float(s.total_amount)
        top_customers = sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)[:5]

        return render(request, 'viewer_dashboard.html', {
            'total_sales': total_sales,
            'total_received': total_received,
            'total_outstanding': total_outstanding,
            'total_tons_sold': total_tons_sold,
            'tm_sales': tm_sales,
            'lm_sales': lm_sales,
            'tm_tons': tm_tons,
            'recent_sales': recent_sales,
            'trend_labels': trend_labels,
            'trend_data': trend_data,
            'top_customers': top_customers,
        })

    # ---------- FULL DASHBOARD (MANAGER / ACCOUNTANT) ----------

    # Current counts
    total_employees = Employee.objects.filter(voided=False).count()
    active_employees = Employee.objects.filter(status='Active', voided=False).count()
    mine_count = Mine.objects.filter(voided=False, status='Active').count()

    # Sales (this month vs last month)
    all_sales = Sale.objects.filter(voided=False)
    tm_sales_qs = all_sales.filter(date__gte=this_month_start)
    lm_sales_qs = all_sales.filter(date__gte=last_month_start, date__lte=last_month_end)

    tm_sales = sum(s.total_amount for s in tm_sales_qs)
    lm_sales = sum(s.total_amount for s in lm_sales_qs)

    tm_received = sum(s.amount_paid for s in tm_sales_qs)
    lm_received = sum(s.amount_paid for s in lm_sales_qs)

    tm_tons_sold = sum(s.quantity_tons for s in tm_sales_qs)
    lm_tons_sold = sum(s.quantity_tons for s in lm_sales_qs)

    total_outstanding = sum(s.balance for s in all_sales.filter(payment_status__in=['Unpaid', 'Partial']))

    # Production (this month vs last month)
    all_prod = ProductionRecord.objects.filter(voided=False)
    tm_prod = all_prod.filter(date__gte=this_month_start)
    lm_prod = all_prod.filter(date__gte=last_month_start, date__lte=last_month_end)

    tm_tons = sum(p.quantity_tons for p in tm_prod)
    lm_tons = sum(p.quantity_tons for p in lm_prod)

    # Payroll (this month vs last month) — use net_salary for the selected period
    tm_payroll = Payroll.objects.filter(voided=False, year=today.year, month=today.month)
    lm_payroll = Payroll.objects.filter(voided=False, year=last_month_start.year, month=last_month_start.month)

    tm_payroll_total = sum(p.net_salary for p in tm_payroll)
    lm_payroll_total = sum(p.net_salary for p in lm_payroll)

    # Alerts
    low_stock_items = [i for i in InventoryItem.objects.filter(voided=False) if i.is_low_stock]
    pending_approvals = (
        Employee.objects.filter(approval_status='Pending', voided=False).count() +
        InventoryItem.objects.filter(approval_status='Pending', voided=False).count() +
        Payroll.objects.filter(status='Pending', voided=False).count()
    )

    # Monthly comparison (last 6 months) — Production + Sales + Payroll
    monthly_labels = []
    monthly_production = []
    monthly_sales = []
    monthly_payroll = []
    from calendar import month_abbr
    for i in range(5, -1, -1):
        # Compute month start/end for i months ago
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        monthly_labels.append(f'{month_abbr[m]} {str(y)[-2:]}')

        prod = sum(p.quantity_tons for p in ProductionRecord.objects.filter(
            voided=False, date__year=y, date__month=m
        ))
        monthly_production.append(float(prod))

        sales = sum(s.total_amount for s in Sale.objects.filter(
            voided=False, date__year=y, date__month=m
        ))
        monthly_sales.append(float(sales))

        payroll = sum(p.net_salary for p in Payroll.objects.filter(
            voided=False, year=y, month=m
        ))
        monthly_payroll.append(float(payroll))

    # Sales trend — last 30 days
    trend_labels = []
    trend_data = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        amount = sum(s.total_amount for s in Sale.objects.filter(date=d, voided=False))
        trend_labels.append(d.strftime('%d %b'))
        trend_data.append(float(amount))

    # Top customers (this month)
    customer_totals = {}
    for s in tm_sales_qs:
        name = s.customer.name
        customer_totals[name] = customer_totals.get(name, 0) + float(s.total_amount)
    top_customers = sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    # Mine performance (this month)
    mine_performance = []
    for m in Mine.objects.filter(voided=False):
        tons = sum(p.quantity_tons for p in ProductionRecord.objects.filter(
            mine=m, voided=False, date__gte=this_month_start
        ))
        revenue = sum(s.total_amount for s in Sale.objects.filter(
            mine=m, voided=False, date__gte=this_month_start
        ))
        mine_performance.append({
            'mine': m,
            'tons': tons,
            'revenue': revenue,
        })
    mine_performance.sort(key=lambda x: float(x['tons']), reverse=True)

    # Recent sales (last 5)
    recent_sales = all_sales.order_by('-created_at')[:5]

    # Compute trend % helpers
    def pct(current, previous):
        if not previous:
            return None
        return round(((float(current) - float(previous)) / float(previous)) * 100, 1)

    sales_trend_pct = pct(tm_sales, lm_sales)
    production_trend_pct = pct(tm_tons, lm_tons)
    received_trend_pct = pct(tm_received, lm_received)

    context = {
        # Counts
        'total_employees': total_employees,
        'active_employees': active_employees,
        'mine_count': mine_count,

        # Sales
        'tm_sales': tm_sales,
        'tm_received': tm_received,
        'tm_tons_sold': tm_tons_sold,
        'total_outstanding': total_outstanding,

        # Production
        'tm_tons': tm_tons,

        # Payroll
        'tm_payroll_total': tm_payroll_total,

        # Alerts
        'low_stock_items': low_stock_items,
        'pending_approvals': pending_approvals,
        'low_stock_count': len(low_stock_items),

        # Trends
        'sales_trend_pct': sales_trend_pct,
        'production_trend_pct': production_trend_pct,
        'received_trend_pct': received_trend_pct,

        # Monthly chart data
        'monthly_labels': monthly_labels,
        'monthly_production': monthly_production,
        'monthly_sales': monthly_sales,
        'monthly_payroll': monthly_payroll,

        # 30-day chart
        'trend_labels': trend_labels,
        'trend_data': trend_data,

        # Tables
        'top_customers': top_customers,
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

@login_required
def stock_transaction_delete(request, pk):
    trans = get_object_or_404(StockTransaction, pk=pk)
    if request.method == 'POST':
        item = trans.item
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
    """Auto-generate payroll for all active employees for a given month/year."""
    from decimal import Decimal

    if request.method == 'POST':
        month = int(request.POST.get('month'))
        year = int(request.POST.get('year'))
        created = 0
        skipped = 0
        employees = Employee.objects.filter(status='Active')

        for emp in employees:
            if Payroll.objects.filter(employee=emp, month=month, year=year).exists():
                skipped += 1
                continue

            records = Attendance.objects.filter(
                employee=emp, date__month=month, date__year=year
            )
            present = records.filter(status='Present').count()
            absent = records.filter(status='Absent').count()
            leave = records.filter(status='Leave').count()
            half = records.filter(status='Half Day').count()

            overtime_hours = sum((r.overtime_hours or Decimal('0')) for r in records)

            emp_salary = emp.salary or Decimal('0')
            daily_rate = emp_salary / Decimal('30') if emp_salary else Decimal('0')
            overtime_amount = (overtime_hours * (daily_rate / Decimal('8')) * Decimal('1.5')) if daily_rate else Decimal('0')

            is_manager_user = request.user.is_superuser or request.user.groups.filter(name='Manager').exists()
            Payroll.objects.create(
                employee=emp,
                month=month,
                year=year,
                basic_salary=emp_salary,
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

        is_manager_user = request.user.is_superuser or request.user.groups.filter(name='Manager').exists()
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


@role_required('Manager', 'Accountant')
def payroll_edit(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
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
        messages.warning(request, 'This payroll record is already voided.')
        return redirect('payroll_list')

    if payroll.status == 'Paid':
        messages.error(request, 'Paid payroll records cannot be voided. Contact the superuser if correction is needed.')
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

    if request.method == 'POST':
        form = SaleForm(request.POST)
        if form.is_valid():
            sale = form.save(commit=False)
            sale.created_by = request.user
            sale.date = date_today.today()
            sale.dispatch_date = date_today.today()
            sale.save()
            messages.success(request, f'Dispatch {sale.dispatch_no} created. Print the slip for the driver.')
            return redirect('sale_slip', pk=sale.pk)
    else:
        # Pre-fill with the last dispatch's settings for quick entry
        initial = {}
        last_sale = Sale.objects.order_by('-created_at').first()
        if last_sale:
            initial['coal_type'] = last_sale.coal_type           # ← auto-select coal type
            initial['mine'] = last_sale.mine                     # ← same mine
            initial['price_per_ton'] = last_sale.price_per_ton   # ← same rate
            initial['customer'] = last_sale.customer             # ← same customer
            initial['truck_no'] = last_sale.truck_no             # ← same truck
            initial['driver_name'] = last_sale.driver_name       # ← same driver
            initial['driver_phone'] = last_sale.driver_phone     # ← same phone
            initial['payment_status'] = last_sale.payment_status
        form = SaleForm(initial=initial)
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


@role_required('Manager')
def approve_payroll(request, pk):
    from django.utils import timezone
    payroll = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST':
        payroll.status = 'Approved'
        payroll.approved_by = request.user
        payroll.approved_at = timezone.now()
        payroll.save()
        if payroll.created_by:
            create_notification(
                payroll.created_by,
                f'Payroll for {payroll.employee.first_name} {payroll.employee.last_name} '
                f'({payroll.get_month_display()} {payroll.year}) has been approved by {request.user.username}.',
                link=f'/payroll/{payroll.pk}/'
            )
            Notification.objects.filter(
            user=request.user,
            object_type='Payroll',
            object_id=payroll.pk,
            status='Pending',
        ).update(
            status='Approved',
            message=f'You approved payroll for {payroll.employee.first_name} {payroll.employee.last_name} ({payroll.get_month_display()} {payroll.year}).',
            is_read=True,
        )
        messages.success(request, f'Payroll for {payroll.employee.first_name} {payroll.employee.last_name} approved.')
    return redirect('approval_list')


@role_required('Manager')
def approve_payroll_paid(request, pk):
    from django.utils import timezone
    payroll = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST':
        payroll.status = 'Paid'
        payroll.payment_date = timezone.now().date()   # ← Auto-fill today
        payroll.paid_by = request.user                 # ← Auto-record
        payroll.confirmed_at = timezone.now()          # ← Auto-record time
        payroll.save()
        if payroll.paid_requested_by:
            create_notification(
                payroll.paid_requested_by,
                f'Payment for {payroll.employee.first_name} {payroll.employee.last_name} '
                f'({payroll.get_month_display()} {payroll.year}) has been marked as PAID by {request.user.username}.',
                link=f'/payroll/{payroll.pk}/'
            )
        messages.success(request, 'Payment marked as PAID.')
    return redirect('approval_list')
@role_required('Manager', 'Accountant')
def payroll_mark_paid(request, pk):
    from django.utils import timezone
    from decimal import Decimal

    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method != 'POST':
        return redirect('payroll_list')

    # Get client IP
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')

    is_manager_user = request.user.is_superuser or request.user.groups.filter(name='Manager').exists()

    # Check if already paid
    if payroll.status == 'Paid':
        messages.warning(request, 'This payroll is already marked as Paid.')
        return redirect('payroll_list')

    # Get amount from form (default = net salary)
    try:
        amount = Decimal(request.POST.get('received_amount') or payroll.net_salary)
    except Exception:
        amount = payroll.net_salary

    note = request.POST.get('confirmation_notes', '').strip()

    if is_manager_user:
        # Manager pays directly
        payroll.status = 'Paid'
        payroll.received_amount = amount
        payroll.payment_date = timezone.now().date()
        payroll.paid_by = request.user
        payroll.paid_from_ip = ip
        payroll.payment_method = 'Cash'
        payroll.confirmed_at = timezone.now()
        payroll.employee_confirmed = True
        payroll.confirmation_notes = note
        payroll.save()

        if payroll.created_by and payroll.created_by != request.user:
            create_notification(
                payroll.created_by,
                f'Salary for {payroll.employee.first_name} {payroll.employee.last_name} '
                f'({payroll.get_month_display()} {payroll.year}) has been PAID by {request.user.username}.',
                link=f'/payroll/{payroll.pk}/'
            )

        messages.success(
            request,
            f'✅ Salary paid to {payroll.employee.first_name} {payroll.employee.last_name}. '
            f'Amount: PKR {amount}'
        )
    else:
        # Accountant requests approval
        payroll.status = 'Paid Pending'
        payroll.received_amount = amount
        payroll.paid_requested_by = request.user
        payroll.confirmation_notes = note
        payroll.save()
        notify_managers(
            f'Payroll for {payroll.employee.first_name} {payroll.employee.last_name} '
            f'({payroll.get_month_display()} {payroll.year}) marked as PAID by {request.user.username} — awaiting your approval.',
            link='/approvals/'
        )
        messages.info(request, 'Payment submitted for manager approval.')

    return redirect('payroll_list')


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

            # Run pg_dump → write to dated file
            env = os.environ.copy()
            env['PGPASSWORD'] = 'jasim'

            result = subprocess.run(
                [pg_dump_path, '-U', 'postgres', '-h', 'localhost', '-Fc', '-f', dated_filepath, 'coalmining_db'],
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
def payroll_pay_save(request, pk):
    """Handle the confirm payment POST (with signed slip photo)."""
    from django.utils import timezone
    from decimal import Decimal

    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method != 'POST':
        return redirect('payroll_list')

    received = request.POST.get('received_amount', '').strip()
    notes = request.POST.get('confirmation_notes', '').strip()
    photo = request.FILES.get('signed_slip_photo')

    try:
        payroll.received_amount = Decimal(received) if received else payroll.net_salary
    except Exception:
        payroll.received_amount = payroll.net_salary

    payroll.confirmation_notes = notes
    payroll.paid_by = request.user
    payroll.confirmed_at = timezone.now()
    payroll.payment_date = timezone.now().date()
    payroll.employee_confirmed = True
    payroll.status = 'Paid'

    if photo:
        payroll.signed_slip_photo = photo

    payroll.save()

    if payroll.created_by and payroll.created_by != request.user:
        create_notification(
            payroll.created_by,
            f'Salary for {payroll.employee.first_name} {payroll.employee.last_name} '
            f'({payroll.get_month_display()} {payroll.year}) has been PAID by {request.user.username}.',
            link=f'/payroll/{payroll.pk}/'
        )

    messages.success(
        request,
        f'✅ Salary paid to {payroll.employee.first_name} {payroll.employee.last_name}. '
        f'Amount: PKR {payroll.received_amount}'
    )
    return redirect('payroll_detail', pk=payroll.pk)

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
    return render(request, 'reports/coming_soon.html', {'report_name': 'Payroll Report', 'report_icon': 'bi-cash-coin'})


@role_required('Manager', 'Accountant')
def report_inventory(request):
    return render(request, 'reports/coming_soon.html', {'report_name': 'Inventory Report', 'report_icon': 'bi-box-seam'})


@role_required('Manager', 'Accountant')
def report_attendance(request):
    return render(request, 'reports/coming_soon.html', {'report_name': 'Attendance Report', 'report_icon': 'bi-calendar-check'})


@role_required('Manager', 'Accountant')
def report_equipment(request):
    return render(request, 'reports/coming_soon.html', {'report_name': 'Equipment Report', 'report_icon': 'bi-tools'})