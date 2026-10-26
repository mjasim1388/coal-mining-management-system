"""
Mine views: list, add, edit, void.
"""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from ..decorators import role_required
from ..forms import MineForm
from ..models import Mine
from ._helpers import void_record


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