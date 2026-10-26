"""
Production views: list, add, edit, void.
"""
from datetime import date as date_today

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from ..decorators import role_required
from ..forms import ProductionForm
from ..models import Mine, ProductionRecord
from ._helpers import void_record


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
    if request.method == 'POST':
        form = ProductionForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.save()
            messages.success(request, f'Production record saved for {record.mine.name} — {record.quantity_tons} tons.')
            return redirect('production_list')
    else:
        initial = {}
        last = ProductionRecord.objects.order_by('-created_at').first()
        if last:
            initial['mine'] = last.mine
            initial['shift'] = last.shift
            initial['coal_type'] = last.coal_type
            initial['supervisor'] = last.supervisor
        initial['date'] = date_today.today()
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