"""
Inventory views: items, stock transactions, quick in/out.
"""
from datetime import date as date_today
from decimal import Decimal

from django.contrib import messages
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404, redirect, render

from ..decorators import role_required
from ..forms import InventoryItemForm, StockTransactionForm
from ..models import (
    Employee, Equipment, InventoryItem, Mine, StockTransaction,
)
from ._helpers import void_record
from .notifications import notify_accountants, notify_managers


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
    if request.method == 'POST':
        form = StockTransactionForm(request.POST)
        if form.is_valid():
            try:
                with db_transaction.atomic():
                    trans = form.save(commit=False)
                    item = InventoryItem.objects.select_for_update().get(pk=trans.item_id)
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
            except Exception as e:
                messages.error(request, f'Stock update failed: {e}')
    else:
        initial = {}
        last = StockTransaction.objects.order_by('-created_at').first()
        if last:
            initial['item'] = last.item
            initial['transaction_type'] = last.transaction_type
            initial['handled_by'] = last.handled_by
        initial['date'] = date_today.today()
        form = StockTransactionForm(initial=initial)
    return render(request, 'inventory/transaction_form.html', {
        'form': form, 'title': 'Add Stock Transaction',
    })


@role_required('Manager')
def stock_transaction_delete(request, pk):
    trans = get_object_or_404(StockTransaction, pk=pk)
    if request.method == 'POST':
        item = trans.item

        if trans.transaction_type == 'IN' and trans.quantity > item.quantity:
            messages.error(
                request,
                f'Cannot delete this stock-in: only {item.quantity} {item.unit} left, '
                f'but this transaction added {trans.quantity} {item.unit}.'
            )
            return redirect('stock_transaction_list')

        with db_transaction.atomic():
            if trans.transaction_type == 'IN':
                item.quantity -= trans.quantity
            else:
                item.quantity += trans.quantity
            item.save()
            trans.delete()

        messages.success(request, 'Transaction deleted and stock adjusted.')
        return redirect('stock_transaction_list')
    return render(request, 'inventory/transaction_delete.html', {'trans': trans})


@role_required('Manager', 'Accountant')
def stock_quick_in(request, item_pk):
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

        try:
            with db_transaction.atomic():
                item = InventoryItem.objects.select_for_update().get(pk=item_pk)
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
        except Exception as e:
            messages.error(request, f'Stock-in failed: {e}')

    return redirect('inventory_list')


@role_required('Manager', 'Accountant')
def stock_quick_out(request, item_pk):
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

        issued_to_type = request.POST.get('issued_to_type', 'General')
        eq_id = request.POST.get('issued_to_equipment') or None
        emp_id = request.POST.get('issued_to_employee') or None
        mine_id = request.POST.get('issued_to_mine') or None

        try:
            with db_transaction.atomic():
                item = InventoryItem.objects.select_for_update().get(pk=item_pk)
                if qty > item.quantity:
                    messages.error(request, f'Not enough stock. Available: {item.quantity} {item.unit}')
                    return redirect('inventory_list')

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
        except Exception as e:
            messages.error(request, f'Stock-out failed: {e}')

    return redirect('inventory_list')