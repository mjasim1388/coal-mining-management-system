"""
Equipment views: list, detail, add, edit, void + maintenance + fuel report.
"""
from datetime import date as date_today, timedelta

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from ..decorators import role_required
from ..forms import EquipmentForm, MaintenanceLogForm
from ..models import Equipment, MaintenanceLog, StockTransaction
from ._helpers import void_record


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
    equipment = get_object_or_404(Equipment, pk=pk)
    logs = equipment.maintenance_logs.all()
    total_cost = sum(log.cost for log in logs)

    fuel_issues = equipment.stock_issues.filter(
        transaction_type='OUT',
        item__category='Fuel',
    ).select_related('item', 'created_by').order_by('-date', '-created_at')

    today = date_today.today()
    month_start = today.replace(day=1)

    this_month_qs = fuel_issues.filter(date__gte=month_start)
    this_month_liters = this_month_qs.aggregate(t=Sum('quantity'))['t'] or 0
    this_month_cost = sum(float(f.quantity) * float(f.item.unit_price) for f in this_month_qs)

    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    last_month_qs = fuel_issues.filter(date__gte=last_month_start, date__lte=last_month_end)
    last_month_liters = last_month_qs.aggregate(t=Sum('quantity'))['t'] or 0
    last_month_cost = sum(float(f.quantity) * float(f.item.unit_price) for f in last_month_qs)

    total_liters = fuel_issues.aggregate(t=Sum('quantity'))['t'] or 0
    total_fuel_cost = sum(float(f.quantity) * float(f.item.unit_price) for f in fuel_issues)

    return render(request, 'equipment/detail.html', {
        'equipment': equipment,
        'logs': logs,
        'total_cost': total_cost,
        'fuel_issues': fuel_issues[:20],
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
            messages.success(request, 'Maintenance log voided.')
        return redirect('equipment_detail', pk=equipment_pk)

    return render(request, 'shared/void_confirm.html', {
        'title': 'Void Maintenance Log',
        'object_label': f'{log.equipment.name} — {log.maintenance_type} on {log.date}',
        'object_type': 'Maintenance Log',
        'details': [
            ('Equipment', f'{log.equipment.equipment_code} — {log.equipment.name}'),
            ('Date', log.date),
            ('Type', log.maintenance_type),
            ('Cost', f'PKR {log.cost}'),
            ('Status', log.status),
        ],
        'cancel_url': 'maintenance_list',
    })


@role_required('Manager', 'Accountant', 'Viewer')
def fuel_report(request):
    month = request.GET.get('month', '')
    year = request.GET.get('year', '')

    today = date_today.today()
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

    fuel_txns = StockTransaction.objects.filter(
        transaction_type='OUT',
        item__category='Fuel',
        date__month=month_int,
        date__year=year_int,
    ).select_related('item', 'issued_to_equipment')

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

    ranked = sorted(equipment_data.values(), key=lambda x: x['liters'], reverse=True)

    total_liters = sum(e['liters'] for e in ranked) + unassigned_liters
    total_cost = sum(e['cost'] for e in ranked) + unassigned_cost

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