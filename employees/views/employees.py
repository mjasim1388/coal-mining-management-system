"""
Employee views: list, detail, add, edit, void.
"""
from datetime import date as date_today

from django.core.paginator import Paginator
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from ..decorators import role_required
from ..forms import EmployeeForm
from ..models import Employee
from ._helpers import void_record
from .notifications import notify_accountants, notify_managers


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

    # --- Pagination ---
    paginator = Paginator(employees, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'employees/list.html', {
        'employees': page_obj,
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
        initial = {}
        last = Employee.objects.order_by('-created_at').first()
        if last:
            initial['shift'] = last.shift
            initial['department'] = last.department
            initial['designation'] = last.designation
            initial['status'] = 'Active'
        initial['date_of_joining'] = date_today.today()
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