"""
Dashboard view — the operations landing page.
"""
from datetime import date, timedelta
from calendar import month_abbr

from django.db.models import (
    Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value,
)
from django.db.models.functions import Coalesce, TruncMonth
from django.shortcuts import render
from django.utils import timezone

from ..decorators import role_required
from ..models import (
    Attendance, Customer, Employee, Equipment, Hazard, InventoryItem,
    MaintenanceLog, Mine, Payroll, PPEIssuance, ProductionRecord,
    SafetyIncident, SafetyTraining, Sale, SalePayment, StockTransaction,
)


# ---------- HELPERS ----------
_DEC = DecimalField(max_digits=18, decimal_places=2)

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
    today = timezone.localdate()
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

    # ---- VIEWER DASHBOARD ----
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

    # ---- FULL DASHBOARD ----
    emp = Employee.objects.filter(voided=False).aggregate(
        total=Count('pk'),
        active=Count('pk', filter=Q(status='Active')),
    )
    total_employees, active_employees = emp['total'], emp['active']
    mine_count = Mine.objects.filter(voided=False, status='Active').count()

    tm = tm_sales_qs.aggregate(
        total=_zero(SALE_TOTAL),
        tons=_zero('quantity_tons'),
        count=Count('pk'),
        paid=Count('pk', filter=Q(payment_status='Paid')),
        partial=Count('pk', filter=Q(payment_status='Partial')),
        unpaid=Count('pk', filter=Q(payment_status='Unpaid')),
    )
    
    # FIX: Calculate actual cash received from SalePayment records this month
    tm_cash_received = SalePayment.objects.filter(
        date__gte=this_month_start, sale__voided=False
    ).aggregate(t=_zero('amount'))['t']

    lm_cash_received = SalePayment.objects.filter(
        date__gte=last_month_start, date__lte=last_month_end, sale__voided=False
    ).aggregate(t=_zero('amount'))['t']
    
    lm_sales_total = lm_sales_qs.aggregate(t=_zero(SALE_TOTAL))['t']

    tm_sales = tm['total']
    tm_tons_sold, tm_sales_count = tm['tons'], tm['count']
    tm_paid, tm_partial, tm_unpaid = tm['paid'], tm['partial'], tm['unpaid']

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
    overdue_amount = ag['a2'] + ag['a3'] + ag['a4']
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

    all_prod = ProductionRecord.objects.filter(voided=False)
    tm_tons = all_prod.filter(date__gte=this_month_start).aggregate(t=_zero('quantity_tons'))['t']
    lm_tons = all_prod.filter(
        date__gte=last_month_start, date__lte=last_month_end
    ).aggregate(t=_zero('quantity_tons'))['t']

    tm_payroll = list(Payroll.objects.filter(voided=False, year=today.year, month=today.month))
    tm_payroll_total = sum(p.net_salary for p in tm_payroll)
    tm_payroll_count = len(tm_payroll)

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

    eq = Equipment.objects.filter(voided=False).aggregate(
        total=Count('pk'),
        working=Count('pk', filter=Q(status='Working')),
        maint=Count('pk', filter=Q(status='Under Maintenance')),
        out=Count('pk', filter=Q(status='Out of Service')),
    )

    fuel = StockTransaction.objects.filter(
        transaction_type='OUT', item__category='Fuel', date__gte=this_month_start,
    ).aggregate(
        liters=_zero('quantity'),
        cost=_zero(ExpressionWrapper(F('quantity') * F('item__unit_price'), output_field=_DEC)),
    )
    fuel_liters, fuel_cost = fuel['liters'], fuel['cost']

    maint = MaintenanceLog.objects.filter(
        voided=False, date__gte=this_month_start
    ).aggregate(cost=_zero('cost'), count=Count('pk'))
    maint_cost, maint_count = maint['cost'], maint['count']

    all_items = list(InventoryItem.objects.filter(voided=False))
    low_stock_items = [i for i in all_items if i.is_low_stock]
    low_stock_count = len(low_stock_items)
    inventory_value = sum(float(i.quantity) * float(i.unit_price) for i in all_items)

    pending_approvals = 0
    if is_manager:
        pending_approvals = (
            Employee.objects.filter(approval_status='Pending', voided=False).count()
            + InventoryItem.objects.filter(approval_status='Pending', voided=False).count()
        )

    # ----- SAFETY -----
    today_for_safety = timezone.localdate()
    last_incident = SafetyIncident.objects.order_by('-date').first()
    days_since_incident = (
        (today_for_safety - last_incident.date).days if last_incident else None
    )

    open_hazards_count = Hazard.objects.filter(
        status__in=['Open', 'In Progress']
    ).count()

    critical_hazards_count = Hazard.objects.filter(
        status__in=['Open', 'In Progress'],
        risk_level__in=['Critical', 'High'],
    ).count()

    incidents_this_month = SafetyIncident.objects.filter(
        date__gte=this_month_start
    ).count()

    # FIX: Include Expired AND Expiring PPE/Training
    ppe_due_soon = PPEIssuance.objects.filter(
        replacement_due__lte=today_for_safety + timedelta(days=30),
        replacement_due__isnull=False,
        returned=False,
    ).count()

    training_due_soon = SafetyTraining.objects.filter(
        expiry_date__lte=today_for_safety + timedelta(days=30),
        expiry_date__isnull=False,
    ).count()

    total_customers = Customer.objects.filter(voided=False).count()
    new_customers_month = Customer.objects.filter(
        voided=False, created_at__date__gte=this_month_start
    ).count()

    top_customers = _top_customers(tm_sales_qs)
    top_customer = top_customers[0] if top_customers else None

    # Trends using accurate cash data
    sales_trend_pct = _pct_change(tm_sales, lm_sales_total)
    production_trend_pct = _pct_change(tm_tons, lm_tons)
    received_trend_pct = _pct_change(tm_cash_received, lm_cash_received)

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

    trend_labels, trend_data = _daily_sales_series(all_sales, today)

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

    cost_payroll = float(tm_payroll_total or 0)
    cost_fuel = float(fuel_cost or 0)
    cost_maintenance = float(maint_cost or 0)

    # --- NEW FINANCIAL METRICS (Calculated in Python) ---
    total_costs = cost_payroll + cost_fuel + cost_maintenance
    net_position = float(tm_sales) - total_costs
    cost_per_ton = (total_costs / float(tm_tons)) if float(tm_tons) > 0 else 0
    collection_rate = (float(tm_cash_received) / float(tm_sales) * 100) if float(tm_sales) > 0 else 0

    coal_type_data = {}
    rows = tm_sales_qs.order_by().values('coal_type').annotate(t=Sum(SALE_TOTAL))
    for r in rows:
        label = r['coal_type'] or 'Other'
        coal_type_data[label] = coal_type_data.get(label, 0) + float(r['t'] or 0)

    return render(request, 'dashboard.html', {
        'today': today,
        'total_employees': total_employees,
        'active_employees': active_employees,
        'mine_count': mine_count,
        'tm_sales': tm_sales,
        'tm_received': tm_cash_received, # FIXED: Now uses accurate payment data
        'tm_tons_sold': tm_tons_sold,
        'tm_sales_count': tm_sales_count,
        'total_outstanding': total_outstanding,
        'tm_tons': tm_tons,
        'tm_payroll_total': tm_payroll_total,
        'tm_payroll_count': tm_payroll_count,
        'todays_dispatches': todays_dispatches,
        'todays_tons': todays_tons,
        'todays_cash': todays_cash,
        'todays_production': todays_production,
        'today_present': att['present'],
        'today_absent': att['absent'],
        'today_leave': att['leave'],
        'today_attendance_total': att['total'],
        'eq_working': eq['working'],
        'eq_maint': eq['maint'],
        'eq_out': eq['out'],
        'eq_total': eq['total'],
        'fuel_liters': fuel_liters,
        'fuel_cost': fuel_cost,
        'maint_cost': maint_cost,
        'maint_count': maint_count,
        'low_stock_items': low_stock_items,
        'low_stock_count': low_stock_count,
        'inventory_value': inventory_value,
        'pending_approvals': pending_approvals,
        
        # Safety
        'days_since_incident': days_since_incident,
        'open_hazards_count': open_hazards_count,
        'critical_hazards_count': critical_hazards_count,
        'incidents_this_month': incidents_this_month,
        'ppe_due_soon': ppe_due_soon,
        'training_due_soon': training_due_soon,
        
        'total_customers': total_customers,
        'new_customers_month': new_customers_month,
        'overdue_invoices': overdue_invoices,
        'overdue_amount': overdue_amount,
        'aging': aging,
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
        'mine_performance': mine_performance,
        'recent_sales': recent_sales,
        
        # NEW Financial Metrics
        'net_position': net_position,
        'cost_per_ton': cost_per_ton,
        'collection_rate': collection_rate,
    })