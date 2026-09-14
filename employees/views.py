from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from .decorators import role_required
from .models import (Employee, Mine, ProductionRecord, Attendance,
                     InventoryItem, StockTransaction, Payroll,
                     Customer, Sale, Notification, ApprovalLog)
from .forms import (EmployeeForm, MineForm, ProductionForm, AttendanceForm,
                    InventoryItemForm, StockTransactionForm, PayrollForm,
                    CustomerForm, SaleForm)
from .exports import make_excel_response
from datetime import date

# ---------- DASHBOARD ----------
@role_required('Manager', 'Accountant', 'Viewer')
def dashboard(request):
    from datetime import date, timedelta

    total = Employee.objects.count()
    active = Employee.objects.filter(status='Active').count()
    on_leave = Employee.objects.filter(status='On Leave').count()
    inactive = Employee.objects.filter(status='Inactive').count()
    recent = Employee.objects.order_by('-created_at')[:5]
    total_production = ProductionRecord.objects.aggregate(t=Sum('quantity_tons'))['t'] or 0
    mine_count = Mine.objects.count()

    # Sales & finance
    total_sales = sum(s.total_amount for s in Sale.objects.all())
    total_received = sum(s.amount_paid for s in Sale.objects.all())
    total_outstanding = total_sales - total_received

    # Payroll
    total_payroll = sum(p.net_salary for p in Payroll.objects.all())

    # Low stock items
    low_stock_items = [i for i in InventoryItem.objects.all() if i.is_low_stock]

    # Unpaid / partial invoices
    unpaid_sales = Sale.objects.exclude(payment_status='Paid')[:5]

    # Production trend - last 7 days
    today = date.today()
    trend_labels = []
    trend_data = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        trend_labels.append(d.strftime('%d %b'))
        qty = ProductionRecord.objects.filter(date=d).aggregate(t=Sum('quantity_tons'))['t'] or 0
        trend_data.append(float(qty))

    # Production by mine (top 5)
    mine_labels = []
    mine_data = []
    for m in Mine.objects.all()[:5]:
        mine_labels.append(m.name)
        q = m.productions.aggregate(t=Sum('quantity_tons'))['t'] or 0
        mine_data.append(float(q))

    context = {
        'total': total,
        'active': active,
        'on_leave': on_leave,
        'inactive': inactive,
        'recent': recent,
        'total_production': total_production,
        'mine_count': mine_count,
        'total_sales': total_sales,
        'total_received': total_received,
        'total_outstanding': total_outstanding,
        'total_payroll': total_payroll,
        'low_stock_items': low_stock_items,
        'unpaid_sales': unpaid_sales,
        'trend_labels': trend_labels,
        'trend_data': trend_data,
        'mine_labels': mine_labels,
        'mine_data': mine_data,
    }
    return render(request, 'dashboard.html', context)

# ---------- EMPLOYEES ----------
@role_required('Manager', 'Accountant')
def employee_list(request):
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    employees = Employee.objects.all()
    if query:
        employees = employees.filter(first_name__icontains=query) | \
                    employees.filter(last_name__icontains=query) | \
                    employees.filter(employee_code__icontains=query) | \
                    employees.filter(cnic__icontains=query)
    if status_filter:
        employees = employees.filter(status=status_filter)
    return render(request, 'employees/list.html', {
        'employees': employees, 'query': query, 'status_filter': status_filter,
    })


@role_required('Manager')
def employee_detail(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    return render(request, 'employees/detail.html', {'employee': employee})


@role_required('Manager', 'Accountant')
def employee_add(request):
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
                messages.success(request, 'Employee added.')
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
                messages.info(request, 'Employee submitted for manager approval.')
            return redirect('employee_list')
    else:
        form = EmployeeForm()
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
def employee_delete(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        employee.delete()
        messages.success(request, 'Employee deleted.')
        return redirect('employee_list')
    return render(request, 'employees/delete.html', {'employee': employee})


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
def mine_delete(request, pk):
    mine = get_object_or_404(Mine, pk=pk)
    if request.method == 'POST':
        mine.delete()
        messages.success(request, 'Mine deleted.')
        return redirect('mine_list')
    return render(request, 'mines/delete.html', {'mine': mine})


# ---------- PRODUCTION ----------
@role_required('Manager', 'Accountant')
def production_list(request):
    mine_filter = request.GET.get('mine', '')
    records = ProductionRecord.objects.select_related('mine').all()
    if mine_filter:
        records = records.filter(mine_id=mine_filter)
    total = records.aggregate(t=Sum('quantity_tons'))['t'] or 0
    return render(request, 'production/list.html', {
        'records': records, 'mines': Mine.objects.all(),
        'mine_filter': mine_filter, 'total': total,
    })


@role_required('Manager', 'Accountant')
def production_add(request):
    if request.method == 'POST':
        form = ProductionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Production record added.')
            return redirect('production_list')
    else:
        form = ProductionForm()
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


@role_required('Manager', 'Accountant')
def production_delete(request, pk):
    record = get_object_or_404(ProductionRecord, pk=pk)
    if request.method == 'POST':
        record.delete()
        messages.success(request, 'Production record deleted.')
        return redirect('production_list')
    return render(request, 'production/delete.html', {'record': record})


# ---------- ATTENDANCE ----------
@role_required('Manager', 'Accountant')
def attendance_list(request):
    date_filter = request.GET.get('date', '')
    status_filter = request.GET.get('status', '')
    records = Attendance.objects.select_related('employee').all()
    if date_filter:
        records = records.filter(date=date_filter)
    if status_filter:
        records = records.filter(status=status_filter)
    return render(request, 'attendance/list.html', {
        'records': records,
        'date_filter': date_filter,
        'status_filter': status_filter,
    })


@role_required('Manager')
def attendance_add(request):
    if request.method == 'POST':
        form = AttendanceForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Attendance record added.')
            return redirect('attendance_list')
    else:
        form = AttendanceForm()
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
def attendance_delete(request, pk):
    record = get_object_or_404(Attendance, pk=pk)
    if request.method == 'POST':
        record.delete()
        messages.success(request, 'Attendance record deleted.')
        return redirect('attendance_list')
    return render(request, 'attendance/delete.html', {'record': record})

# ---------- INVENTORY ----------
@role_required('Manager', 'Accountant')
def inventory_list(request):
    category_filter = request.GET.get('category', '')
    low_filter = request.GET.get('low', '')
    items = list(InventoryItem.objects.all())
    if category_filter:
        items = [i for i in items if i.category == category_filter]
    if low_filter:
        items = [i for i in items if i.is_low_stock]
    low_stock_count = sum(1 for i in InventoryItem.objects.all() if i.is_low_stock)
    return render(request, 'inventory/list.html', {
        'items': items,
        'category_filter': category_filter,
        'low_stock_count': low_stock_count,
        'low_filter': low_filter,
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


@role_required('Manager', 'Accountant')
def inventory_delete(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Item deleted.')
        return redirect('inventory_list')
    return render(request, 'inventory/delete.html', {'item': item})


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
        form = StockTransactionForm()
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
            earned = (present * daily_rate) + (half * daily_rate * Decimal('0.5'))
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
    payrolls = Payroll.objects.select_related('employee').all()
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


@role_required('Manager', 'Accountant')
def payroll_delete(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST':
        payroll.delete()
        messages.success(request, 'Payroll deleted.')
        return redirect('payroll_list')
    return render(request, 'payroll/delete.html', {'payroll': payroll})


@role_required('Manager', 'Accountant')
def payroll_detail(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    return render(request, 'payroll/detail.html', {'payroll': payroll})

# ---------- CUSTOMERS ----------
@role_required('Manager', 'Accountant')
def customer_list(request):
    query = request.GET.get('q', '')
    customers = Customer.objects.all()
    if query:
        customers = customers.filter(name__icontains=query) | \
                    customers.filter(company__icontains=query) | \
                    customers.filter(phone__icontains=query)
    return render(request, 'sales/customer_list.html', {
        'customers': customers, 'query': query,
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


@role_required('Manager', 'Accountant')
def customer_delete(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        customer.delete()
        messages.success(request, 'Customer deleted.')
        return redirect('customer_list')
    return render(request, 'sales/customer_delete.html', {'customer': customer})


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
    if request.method == 'POST':
        form = SaleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Sale record added.')
            return redirect('sale_list')
    else:
        form = SaleForm()
    return render(request, 'sales/sale_form.html', {'form': form, 'title': 'Add Sale'})


@role_required('Manager', 'Accountant')
def sale_edit(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    if request.method == 'POST':
        form = SaleForm(request.POST, instance=sale)
        if form.is_valid():
            form.save()
            messages.success(request, 'Sale updated.')
            return redirect('sale_list')
    else:
        form = SaleForm(instance=sale)
    return render(request, 'sales/sale_form.html', {'form': form, 'title': 'Edit Sale'})


@role_required('Manager', 'Accountant')
def sale_delete(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    if request.method == 'POST':
        sale.delete()
        messages.success(request, 'Sale deleted.')
        return redirect('sale_list')
    return render(request, 'sales/sale_delete.html', {'sale': sale})

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
    emp = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        emp.approval_status = 'Approved'
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
    item = get_object_or_404(InventoryItem, pk=pk)
    if request.method == 'POST':
        item.approval_status = 'Approved'
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
    payroll = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST':
        payroll.status = 'Paid'
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
    payroll = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST':
        is_manager_user = request.user.is_superuser or request.user.groups.filter(name='Manager').exists()
        if is_manager_user:
            payroll.status = 'Paid'
            payroll.payment_date = timezone.now().date()
            payroll.save()
            if payroll.created_by and payroll.created_by != request.user:
                create_notification(
                    payroll.created_by,
                    f'Payroll for {payroll.employee.first_name} {payroll.employee.last_name} '
                    f'({payroll.get_month_display()} {payroll.year}) has been marked as PAID by {request.user.username}.',
                    link=f'/payroll/{payroll.pk}/'
                )
            messages.success(request, 'Payroll marked as PAID.')
        else:
            payroll.status = 'Paid Pending'
            payroll.paid_requested_by = request.user
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
    from django.utils import timezone
    from datetime import date
    from django.http import JsonResponse

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

    if request.method == 'POST':
        try:
            # Ensure backups folder exists
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)

            # Build filename with timestamp
            timestamp = timezone.localtime().strftime('%Y-%m-%d_%H-%M-%S')
            filename = f'coalmining_db_{timestamp}.dump'
            filepath = os.path.join(backup_dir, filename)

            # Find pg_dump path (PostgreSQL 18 on this machine)
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

            # Run pg_dump
            env = os.environ.copy()
            env['PGPASSWORD'] = 'jasim'  # your database password

            result = subprocess.run(
                [pg_dump_path, '-U', 'postgres', '-h', 'localhost', '-Fc', '-f', filepath, 'coalmining_db'],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                messages.error(request, f'Backup failed: {result.stderr}')
                return redirect('dashboard')

            # Get file size
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            messages.success(request, f'✅ Backup saved successfully: {filename} ({size_mb:.2f} MB)')
            return redirect('dashboard')

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
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'modified': timezone.datetime.fromtimestamp(stat.st_mtime),
            'modified_ts': stat.st_mtime,
        })

    # Sort newest first
    backups.sort(key=lambda x: x['modified_ts'], reverse=True)

    total_size = sum(b['size_mb'] for b in backups)

    return render(request, 'backup/list.html', {
        'backups': backups,
        'total_size': round(total_size, 2),
        'count': len(backups),
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


@role_required('Manager')
def backup_delete(request, filename):
    import os
    from django.conf import settings

    if request.method == 'POST':
        if '/' in filename or '\\' in filename or '..' in filename:
            messages.error(request, 'Invalid filename.')
            return redirect('backup_list')

        filepath = os.path.join(settings.BASE_DIR, 'backups', filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            messages.success(request, f'Backup deleted: {filename}')
        else:
            messages.error(request, 'File not found.')

    return redirect('backup_list')