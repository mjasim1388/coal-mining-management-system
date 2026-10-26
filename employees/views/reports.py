"""
Report views — Manager & Accountant.
"""
from datetime import date
from calendar import month_abbr, monthrange
from decimal import Decimal

from django.shortcuts import render

from ..decorators import role_required
from ..models import (
    Attendance, Customer, Equipment, InventoryItem, MaintenanceLog,
    Mine, Payroll, ProductionRecord, Sale, StockTransaction,
)


@role_required('Manager', 'Accountant')
def reports_hub(request):
    return render(request, 'reports/hub.html')


@role_required('Manager', 'Accountant')
def report_sales(request):
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

    sales_qs = Sale.objects.filter(
        voided=False, date__year=year, date__month=month,
    ).select_related('customer', 'mine')

    if customer_filter:
        sales_qs = sales_qs.filter(customer_id=customer_filter)

    total_sales = sum(s.total_amount for s in sales_qs) or 0
    total_received = sum(s.amount_paid for s in sales_qs) or 0
    total_outstanding = total_sales - total_received
    total_tons = sum(s.quantity_tons for s in sales_qs) or 0
    dispatch_count = sales_qs.count()

    prev_month = month - 1
    prev_year = year
    if prev_month <= 0:
        prev_month = 12
        prev_year -= 1

    prev_qs = Sale.objects.filter(voided=False, date__year=prev_year, date__month=prev_month)
    prev_total = sum(s.total_amount for s in prev_qs) or 0

    trend_pct = None
    if prev_total > 0:
        trend_pct = round(((float(total_sales) - float(prev_total)) / float(prev_total)) * 100, 1)

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

    mine_totals = {}
    for s in sales_qs:
        name = s.mine.name if s.mine else 'Unassigned'
        if name not in mine_totals:
            mine_totals[name] = {'sales': 0, 'tons': 0, 'count': 0}
        mine_totals[name]['sales'] += float(s.total_amount)
        mine_totals[name]['tons'] += float(s.quantity_tons)
        mine_totals[name]['count'] += 1
    mine_list = sorted(mine_totals.items(), key=lambda x: x[1]['sales'], reverse=True)

    paid_count = sales_qs.filter(payment_status='Paid').count()
    partial_count = sales_qs.filter(payment_status='Partial').count()
    unpaid_count = sales_qs.filter(payment_status='Unpaid').count()
    paid_amount = sum(s.total_amount for s in sales_qs if s.payment_status == 'Paid') or 0
    partial_amount = sum(s.total_amount for s in sales_qs if s.payment_status == 'Partial') or 0
    unpaid_amount = sum(s.total_amount for s in sales_qs if s.payment_status == 'Unpaid') or 0

    days_in_month = monthrange(year, month)[1]
    daily_labels = []
    daily_data = []
    for d in range(1, days_in_month + 1):
        daily_labels.append(str(d))
        day_total = sum(s.total_amount for s in sales_qs.filter(date__day=d))
        daily_data.append(float(day_total))

    all_dispatches = list(sales_qs.order_by('-date'))

    return render(request, 'reports/sales.html', {
        'month': month, 'year': year, 'month_name': month_abbr[month],
        'now': today, 'months': Payroll.MONTH_CHOICES,
        'customer_filter': customer_filter,
        'all_customers': Customer.objects.filter(voided=False),
        'total_sales': total_sales, 'total_received': total_received,
        'total_outstanding': total_outstanding, 'total_tons': total_tons,
        'dispatch_count': dispatch_count, 'trend_pct': trend_pct,
        'customer_list': customer_list, 'mine_list': mine_list,
        'paid_count': paid_count, 'partial_count': partial_count, 'unpaid_count': unpaid_count,
        'paid_amount': paid_amount, 'partial_amount': partial_amount, 'unpaid_amount': unpaid_amount,
        'daily_labels': daily_labels, 'daily_data': daily_data,
        'all_dispatches': all_dispatches,
    })


@role_required('Manager', 'Accountant')
def report_production(request):
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

    records = ProductionRecord.objects.filter(
        voided=False, date__year=year, date__month=month,
    ).select_related('mine')

    if mine_filter:
        records = records.filter(mine_id=mine_filter)

    total_tons = sum(r.quantity_tons for r in records) or Decimal('0')
    total_overburden = sum(r.overburden_removed for r in records) or Decimal('0')
    total_workers = sum(r.workers_count or 0 for r in records)
    record_count = records.count()

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

    shift_totals = {}
    for r in records:
        s = r.shift
        if s not in shift_totals:
            shift_totals[s] = {'tons': 0, 'count': 0}
        shift_totals[s]['tons'] += float(r.quantity_tons)
        shift_totals[s]['count'] += 1
    shift_list = sorted(shift_totals.items(), key=lambda x: x[1]['tons'], reverse=True)

    coal_totals = {}
    for r in records:
        c = r.coal_type
        if c not in coal_totals:
            coal_totals[c] = {'tons': 0, 'count': 0}
        coal_totals[c]['tons'] += float(r.quantity_tons)
        coal_totals[c]['count'] += 1
    coal_list = sorted(coal_totals.items(), key=lambda x: x[1]['tons'], reverse=True)

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

    if total_tons > 0:
        stripping_ratio = round(float(total_overburden) / float(total_tons), 2)
    else:
        stripping_ratio = 0

    return render(request, 'reports/production.html', {
        'month': month, 'year': year, 'month_name': month_abbr[month],
        'months': Payroll.MONTH_CHOICES, 'mine_filter': mine_filter,
        'all_mines': Mine.objects.filter(voided=False), 'now': today,
        'total_tons': total_tons, 'total_overburden': total_overburden,
        'total_workers': total_workers, 'record_count': record_count,
        'trend_pct': trend_pct, 'stripping_ratio': stripping_ratio,
        'mine_list': mine_list, 'shift_list': shift_list, 'coal_list': coal_list,
        'daily_labels': daily_labels, 'daily_tons': daily_tons,
        'daily_overburden': daily_overburden,
    })


@role_required('Manager', 'Accountant')
def report_payroll(request):
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
        voided=False, year=year, month=month,
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

    paid_count = payrolls.filter(status='Paid').count()
    approved_count = payrolls.filter(status='Approved').count()
    paid_amount = sum(p.net_salary for p in payrolls if p.status == 'Paid') or Decimal('0')
    approved_amount = sum(p.net_salary for p in payrolls if p.status == 'Approved') or Decimal('0')

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

    dept_totals = {}
    for p in payrolls:
        d = p.employee.department or 'Unassigned'
        if d not in dept_totals:
            dept_totals[d] = {'net': 0, 'count': 0, 'overtime': 0}
        dept_totals[d]['net'] += float(p.net_salary)
        dept_totals[d]['count'] += 1
        dept_totals[d]['overtime'] += float(p.overtime_amount)
    dept_list = sorted(dept_totals.items(), key=lambda x: x[1]['net'], reverse=True)

    return render(request, 'reports/payroll.html', {
        'month': month, 'year': year, 'month_name': month_abbr[month],
        'now': today, 'months': Payroll.MONTH_CHOICES, 'status_filter': status_filter,
        'total_basic': total_basic, 'total_overtime': total_overtime,
        'total_allowances': total_allowances, 'total_deductions': total_deductions,
        'total_net': total_net, 'total_overtime_hours': total_overtime_hours,
        'employee_count': employee_count, 'trend_pct': trend_pct,
        'paid_count': paid_count, 'approved_count': approved_count,
        'paid_amount': paid_amount, 'approved_amount': approved_amount,
        'dept_list': dept_list,
        'payrolls': payrolls.order_by('employee__employee_code'),
    })


@role_required('Manager', 'Accountant')
def report_inventory(request):
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

    all_items = list(InventoryItem.objects.filter(voided=False))
    total_items = len(all_items)
    total_value = sum(float(i.quantity) * float(i.unit_price) for i in all_items)
    low_stock_items = [i for i in all_items if i.is_low_stock]
    low_stock_count = len(low_stock_items)

    transactions = StockTransaction.objects.filter(
        date__year=year, date__month=month,
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

    category_data = {}
    for item in all_items:
        cat = item.category
        if cat not in category_data:
            category_data[cat] = {'items': 0, 'value': 0, 'qty': 0}
        category_data[cat]['items'] += 1
        category_data[cat]['value'] += float(item.quantity) * float(item.unit_price)
        category_data[cat]['qty'] += float(item.quantity)
    category_list = sorted(category_data.items(), key=lambda x: x[1]['value'], reverse=True)

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

    return render(request, 'reports/inventory.html', {
        'month': month, 'year': year, 'month_name': month_abbr[month],
        'months': Payroll.MONTH_CHOICES, 'now': today,
        'total_items': total_items, 'total_value': total_value,
        'low_stock_count': low_stock_count, 'low_stock_items': low_stock_items,
        'total_in': total_in, 'total_out': total_out,
        'in_value': in_value, 'out_value': out_value,
        'transaction_count': transaction_count, 'trend_pct': trend_pct,
        'category_list': category_list, 'movement_cat_list': movement_cat_list,
        'fuel_list': fuel_list,
        'transactions': transactions.order_by('-date', '-created_at'),
    })


@role_required('Manager', 'Accountant')
def report_attendance(request):
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
        voided=False, date__year=year, date__month=month,
    ).select_related('employee')

    total = records.count()
    present = records.filter(status='Present').count()
    absent = records.filter(status='Absent').count()
    leave = records.filter(status='Leave').count()
    half = records.filter(status='Half Day').count()

    total_overtime = sum(r.overtime_hours or 0 for r in records)

    def pct(n, total):
        return round((n / total) * 100, 1) if total else 0

    present_pct = pct(present, total)
    absent_pct = pct(absent, total)
    leave_pct = pct(leave, total)
    half_pct = pct(half, total)

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

    return render(request, 'reports/attendance.html', {
        'month': month, 'year': year, 'month_name': month_abbr[month],
        'months': Payroll.MONTH_CHOICES, 'now': today,
        'total': total, 'present': present, 'absent': absent, 'leave': leave, 'half': half,
        'present_pct': present_pct, 'absent_pct': absent_pct,
        'leave_pct': leave_pct, 'half_pct': half_pct,
        'total_overtime': total_overtime, 'trend_pct': trend_pct,
        'dept_list': dept_list, 'emp_list': emp_list,
    })


@role_required('Manager', 'Accountant')
def report_equipment(request):
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

    all_equipment = Equipment.objects.filter(voided=False)
    total_equipment = all_equipment.count()
    working = all_equipment.filter(status='Working').count()
    under_maint = all_equipment.filter(status='Under Maintenance').count()
    out_of_service = all_equipment.filter(status='Out of Service').count()

    logs = MaintenanceLog.objects.filter(
        voided=False, date__year=year, date__month=month,
    ).select_related('equipment')

    total_logs = logs.count()
    total_maint_cost = sum(log.cost for log in logs)

    maint_by_type = {}
    for log in logs:
        t = log.maintenance_type
        if t not in maint_by_type:
            maint_by_type[t] = {'count': 0, 'cost': 0}
        maint_by_type[t]['count'] += 1
        maint_by_type[t]['cost'] += float(log.cost)
    type_list = sorted(maint_by_type.items(), key=lambda x: x[1]['cost'], reverse=True)

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

    status_list = [
        ('Working', working),
        ('Under Maintenance', under_maint),
        ('Out of Service', out_of_service),
    ]

    return render(request, 'reports/equipment.html', {
        'month': month, 'year': year, 'month_name': month_abbr[month],
        'months': Payroll.MONTH_CHOICES, 'now': today,
        'total_equipment': total_equipment, 'working': working,
        'under_maint': under_maint, 'out_of_service': out_of_service,
        'total_logs': total_logs, 'total_maint_cost': total_maint_cost,
        'type_list': type_list, 'eq_list': eq_list, 'status_list': status_list,
    })