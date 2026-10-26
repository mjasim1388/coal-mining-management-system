"""
Payroll views: list, generate, add, edit, pay, void, detail, slip, autofill API.

Role rules:
    Manager    → generate, add, edit, pay, void
    Accountant → read-only view, print slips, reports
"""
from datetime import date as date_today
from decimal import Decimal
from calendar import monthrange

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..decorators import role_required
from ..forms import PayrollForm
from ..models import Attendance, Employee, Payroll
from ._helpers import (
    _client_ip, _is_manager_user, _parse_amount, void_record,
)
from .notifications import create_notification


@role_required('Manager', 'Accountant')
def payroll_list(request):
    today = date_today.today()

    month_str = request.GET.get('month', '')
    year_str = request.GET.get('year', '')
    status_filter = request.GET.get('status', '')
    show_voided = request.GET.get('show_voided', '')

    try:
        month_int = int(month_str) if month_str else today.month
    except ValueError:
        month_int = today.month
    try:
        year_int = int(year_str) if year_str else today.year
    except ValueError:
        year_int = today.year

    qs = Payroll.objects.select_related('employee', 'paid_by').filter(
        month=month_int, year=year_int
    )
    if not show_voided:
        qs = qs.filter(voided=False)
    if status_filter:
        qs = qs.filter(status=status_filter)

    payrolls = list(qs.order_by('employee__employee_code'))

    active_emp_count = Employee.objects.filter(status='Active', voided=False).count()
    existing_count = sum(1 for p in payrolls if not p.voided)
    needs_generation = (
        existing_count == 0
        and active_emp_count > 0
        and month_int == today.month
        and year_int == today.year
    )

    total_net = sum(p.net_salary for p in payrolls if not p.voided)
    paid_count = sum(1 for p in payrolls if not p.voided and p.status == 'Paid')
    approved_count = sum(1 for p in payrolls if not p.voided and p.status == 'Approved')

    return render(request, 'payroll/list.html', {
        'payrolls': payrolls,
        'month_filter': month_int,
        'year_filter': year_int,
        'status_filter': status_filter,
        'show_voided': show_voided,
        'total': total_net,
        'paid_count': paid_count,
        'approved_count': approved_count,
        'needs_generation': needs_generation,
        'active_emp_count': active_emp_count,
        'months': Payroll.MONTH_CHOICES,
        'is_manager': _is_manager_user(request.user),
        'now_month': today.month,
        'now_year': today.year,
    })


@role_required('Manager')
def payroll_generate(request):
    if request.method == 'POST':
        month = int(request.POST.get('month'))
        year = int(request.POST.get('year'))
        created = 0
        skipped = 0
        employees = Employee.objects.filter(
            status='Active',
            voided=False,
            approval_status='Approved',
        )

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
            daily_rate = basic / Decimal('30') if basic else Decimal('0')
            absence_deduction = (absent * daily_rate) + (half * daily_rate * Decimal('0.5'))
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
                status='Approved',
                created_by=request.user,
                approved_by=request.user,
                approved_at=timezone.now(),
            )
            created += 1

        messages.success(
            request,
            f'Payroll generated for {created} employee(s). Skipped (already exist): {skipped}.'
        )
        return redirect(f'/payroll/?month={month}&year={year}')

    return render(request, 'payroll/generate.html', {
        'months': Payroll.MONTH_CHOICES,
    })


@role_required('Manager')
def payroll_add(request):
    if request.method == 'POST':
        form = PayrollForm(request.POST)
        if form.is_valid():
            payroll = form.save(commit=False)
            payroll.created_by = request.user
            payroll.status = 'Approved'
            payroll.approved_by = request.user
            payroll.approved_at = timezone.now()
            payroll.save()
            messages.success(request, 'Payroll added. Ready to pay.')
            return redirect('payroll_list')
    else:
        form = PayrollForm()
    return render(request, 'payroll/form.html', {'form': form, 'title': 'Add Payroll'})


@role_required('Manager')
def payroll_edit(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)

    if payroll.voided:
        messages.error(request, 'Voided payrolls cannot be edited.')
        return redirect('payroll_detail', pk=payroll.pk)

    if payroll.status == 'Paid':
        messages.error(request, 'Paid payrolls cannot be edited. Corrections go in the next month.')
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
def payroll_mark_paid(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method != 'POST':
        return redirect('payroll_list')

    if payroll.voided:
        messages.error(request, 'This payroll is voided and cannot be paid.')
        return redirect('payroll_list')

    if payroll.status == 'Paid':
        messages.warning(request, 'Already marked as paid.')
        return redirect('payroll_list')

    amount = _parse_amount(request.POST.get('received_amount'), payroll.net_salary)
    note = request.POST.get('confirmation_notes', '').strip()

    if amount is None or amount <= 0:
        messages.error(request, 'Amount must be greater than 0.')
        return redirect('payroll_list')

    if amount > payroll.net_salary:
        messages.error(
            request,
            f'Amount (PKR {amount}) cannot exceed net salary (PKR {payroll.net_salary}).'
        )
        return redirect('payroll_list')

    name = f'{payroll.employee.first_name} {payroll.employee.last_name}'
    period = f'{payroll.get_month_display()} {payroll.year}'

    payroll.status = 'Paid'
    payroll.received_amount = amount
    payroll.confirmation_notes = note
    payroll.payment_date = timezone.localdate()
    payroll.paid_by = request.user
    payroll.confirmed_at = timezone.now()
    payroll.employee_confirmed = True
    payroll.paid_from_ip = _client_ip(request)
    payroll.payment_method = 'Cash'
    payroll.save()

    messages.success(request, f'Salary paid to {name}. Amount: PKR {amount}')
    return redirect('payroll_list')


@role_required('Manager')
def payroll_void(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)

    if payroll.voided:
        messages.warning(request, 'This payroll is already voided.')
        return redirect('payroll_list')

    if payroll.status == 'Paid':
        messages.error(request, 'Paid payrolls cannot be voided. Corrections go in the next month.')
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
    return render(request, 'payroll/detail.html', {
        'payroll': payroll,
        'is_manager': _is_manager_user(request.user),
    })


@role_required('Manager', 'Accountant')
def payroll_slip(request, pk):
    payroll = get_object_or_404(Payroll, pk=pk)
    return render(request, 'payroll/slip.html', {'payroll': payroll})


@role_required('Manager')
def payroll_autofill_api(request):
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

    records = Attendance.objects.filter(
        employee=employee, date__month=month_int, date__year=year_int,
        voided=False,
    )
    joining_date = employee.date_of_joining
    if joining_date:
        records = records.filter(date__gte=joining_date)

    present = records.filter(status='Present').count()
    absent = records.filter(status='Absent').count()
    leave = records.filter(status='Leave').count()
    half = records.filter(status='Half Day').count()

    overtime_hours = Decimal('0')
    for r in records:
        overtime_hours += (r.overtime_hours or Decimal('0'))

    if joining_date and joining_date.year == year_int and joining_date.month == month_int:
        days_in_month = monthrange(year_int, month_int)[1]
        eligible_days = days_in_month - joining_date.day + 1
        joined_this_month = True
    elif joining_date and joining_date > date_today(year_int, month_int, 1):
        eligible_days = 0
        joined_this_month = True
    else:
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