"""
Attendance views: list, add, edit, void, punch in/out.
"""
from datetime import date as date_today

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..decorators import role_required
from ..forms import AttendanceForm
from ..models import Attendance, Employee
from ._helpers import void_record


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
    if request.method == 'POST':
        form = AttendanceForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Attendance record added.')
            return redirect('attendance_list')
    else:
        initial = {}
        last = Attendance.objects.order_by('-created_at').first()
        if last:
            initial['shift'] = last.shift
            initial['status'] = last.status
        initial['date'] = date_today.today()
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

    return render(request, 'shared/void_confirm.html', {
        'title': 'Void Attendance',
        'object_label': f'{record.employee.employee_code} — {record.date}',
        'object_type': 'Attendance Record',
        'details': [
            ('Employee', f'{record.employee.employee_code} — {record.employee.first_name} {record.employee.last_name}'),
            ('Date', record.date),
            ('Shift', record.shift),
            ('Status', record.status),
            ('Check In', record.check_in or '—'),
            ('Check Out', record.check_out or '—'),
        ],
        'cancel_url': 'attendance_list',
    })


@role_required('Manager', 'Accountant')
def attendance_punch(request):
    employees = Employee.objects.filter(status='Active').order_by('first_name')
    return render(request, 'attendance/punch.html', {'employees': employees})


@role_required('Manager', 'Accountant')
def attendance_punch_save(request, pk):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=400)

    employee = get_object_or_404(Employee, pk=pk)
    today = date_today.today()
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