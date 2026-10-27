"""
Sales views: list, detail, add, edit, void, slip, live API, payments.
"""
from datetime import date as date_today, timedelta
from decimal import Decimal

from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..decorators import role_required
from ..forms import SaleForm
from ..models import Customer, Mine, Sale, SalePayment
from ._helpers import _is_manager_user, distinct_values, void_record


@role_required('Manager', 'Accountant')
def sale_list(request):
    customer_filter = request.GET.get('customer', '')
    status_filter = request.GET.get('status', '')
    show_voided = request.GET.get('show_voided', '')

    sales = Sale.objects.select_related('customer', 'mine').all()
    if not show_voided:
        sales = sales.filter(voided=False)
    if customer_filter:
        sales = sales.filter(customer_id=customer_filter)
    if status_filter:
        sales = sales.filter(payment_status=status_filter)

    # --- KPI Calculations (must happen BEFORE pagination) ---
    total_amount = sum(s.total_amount for s in sales)
    total_paid = sum(s.amount_paid for s in sales)
    total_balance = total_amount - total_paid

    # --- Pagination (25 per page) ---
    paginator = Paginator(sales, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'sales/sale_list.html', {
        'sales': page_obj, # Pass the page object to the template
        'customers': Customer.objects.all(),
        'customer_filter': customer_filter,
        'status_filter': status_filter,
        'show_voided': show_voided,
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
            sale = form.save(commit=False)
            sale.created_by = request.user
            sale.date = date_today.today()
            sale.dispatch_date = date_today.today()

            total = (sale.quantity_tons or Decimal('0')) * (sale.price_per_ton or Decimal('0'))
            if sale.payment_status == 'Unpaid':
                sale.amount_paid = Decimal('0')
            elif sale.payment_status == 'Paid':
                sale.amount_paid = total
            else:
                if sale.amount_paid is None:
                    sale.amount_paid = Decimal('0')

            sale.save()
            messages.success(request, f'Dispatch {sale.dispatch_no} saved successfully.')
            return redirect('sale_detail', pk=sale.pk)
    else:
        initial = {}
        last = Sale.objects.order_by('-created_at').first()
        if last:
            initial['coal_type'] = last.coal_type
            initial['mine'] = last.mine
            initial['price_per_ton'] = last.price_per_ton
            initial['customer'] = last.customer
            initial['truck_no'] = last.truck_no
            initial['driver_name'] = last.driver_name
            initial['driver_phone'] = last.driver_phone
            initial['payment_status'] = last.payment_status
        form = SaleForm(initial=initial)

    suggestions = {
        'truck_numbers': distinct_values(Sale.objects.filter(voided=False), 'truck_no'),
        'driver_names': distinct_values(Sale.objects.filter(voided=False), 'driver_name'),
        'driver_phones': distinct_values(Sale.objects.filter(voided=False), 'driver_phone'),
    }

    return render(request, 'sales/sale_form.html', {
        'form': form,
        'title': 'New Dispatch',
        'suggestions': suggestions,
    })


@role_required('Manager', 'Accountant')
def sale_edit(request, pk):
    sale = get_object_or_404(Sale, pk=pk)

    is_manager_user = _is_manager_user(request.user)
    if sale.is_locked and not is_manager_user:
        messages.error(request, 'This dispatch is locked and cannot be edited. Contact the manager.')
        return redirect('sale_detail', pk=sale.pk)

    if sale.voided:
        messages.error(request, 'This dispatch has been voided and cannot be edited.')
        return redirect('sale_detail', pk=sale.pk)

    if request.method == 'POST':
        form = SaleForm(request.POST, instance=sale)
        if form.is_valid():
            form.save()
            messages.success(request, 'Dispatch updated.')
            return redirect('sale_list')
    else:
        form = SaleForm(instance=sale)
    return render(request, 'sales/sale_form.html', {'form': form, 'title': 'Edit Dispatch'})


@role_required('Manager')
def sale_delete(request, pk):
    sale = get_object_or_404(Sale, pk=pk)

    if sale.voided:
        messages.warning(request, 'This dispatch is already voided.')
        return redirect('sale_list')

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('sale_delete', pk=sale.pk)

        label = f'{sale.dispatch_no or sale.invoice_no} — {sale.customer.name}'
        if void_record(sale, request.user, reason, request, label):
            messages.success(request, f'Dispatch {sale.dispatch_no} has been voided.')
        else:
            messages.warning(request, 'This dispatch was already voided.')
        return redirect('sale_list')

    return render(request, 'sales/sale_void.html', {'sale': sale})


@role_required('Manager', 'Accountant', 'Viewer')
def sale_slip(request, pk):
    """Printable dispatch slip for the driver."""
    sale = get_object_or_404(Sale, pk=pk)
    return render(request, 'sales/slip.html', {'sale': sale})


@role_required('Manager', 'Accountant', 'Viewer')
def sales_live_api(request):
    """Returns recent dispatches as JSON for live polling."""
    today = date_today.today()
    yesterday = today - timedelta(days=1)

    recent = Sale.objects.select_related('customer', 'mine').filter(
        date__gte=yesterday
    ).order_by('-created_at')[:15]

    data = []
    for s in recent:
        data.append({
            'id': s.pk,
            'invoice_no': s.invoice_no,
            'customer': s.customer.name,
            'mine': s.mine.name if s.mine else '',
            'quantity_tons': float(s.quantity_tons),
            'total_amount': float(s.total_amount),
            'truck_no': s.truck_no or '',
            'driver_name': s.driver_name or '',
            'dispatch_date': str(s.dispatch_date) if s.dispatch_date else '',
            'date': str(s.date),
            'payment_status': s.payment_status,
            'created_at': s.created_at.isoformat(),
            'created_at_display': s.created_at.strftime('%H:%M:%S'),
        })

    return JsonResponse({
        'dispatches': data,
        'server_time': today.isoformat(),
        'count': len(data),
    })


@role_required('Manager', 'Accountant')
def sale_add_payment(request, pk):
    sale = get_object_or_404(Sale, pk=pk)

    if request.method == 'POST':
        if sale.voided:
            messages.error(request, 'Cannot add payment to a voided dispatch.')
            return redirect('sale_detail', pk=sale.pk)

        try:
            amount = Decimal(request.POST.get('amount', '0'))
        except Exception:
            messages.error(request, 'Invalid amount.')
            return redirect('sale_detail', pk=sale.pk)

        if amount <= 0:
            messages.error(request, 'Amount must be greater than 0.')
            return redirect('sale_detail', pk=sale.pk)

        balance = (sale.total_amount or 0) - (sale.amount_paid or 0)
        if amount > balance:
            messages.error(request, f'Amount exceeds outstanding balance (PKR {balance}).')
            return redirect('sale_detail', pk=sale.pk)

        SalePayment.objects.create(
            sale=sale,
            date=date_today.today(),
            amount=amount,
            method=request.POST.get('method', 'Cash'),
            reference_no=request.POST.get('reference_no', ''),
            notes=request.POST.get('notes', ''),
            received_by=request.user,
        )

        sale.amount_paid = (sale.amount_paid or 0) + amount
        new_balance = (sale.total_amount or 0) - sale.amount_paid

        if new_balance <= 0:
            sale.payment_status = 'Paid'
        elif sale.amount_paid > 0:
            sale.payment_status = 'Partial'

        sale.save()

        messages.success(request, f'Payment of PKR {amount} recorded. Balance: PKR {new_balance}')

    return redirect('sale_detail', pk=sale.pk)


@role_required('Manager')
def sale_payment_delete(request, pk):
    """Delete a payment (reverses the balance). Manager only."""
    payment = get_object_or_404(SalePayment, pk=pk)
    sale = payment.sale

    if request.method == 'POST':
        sale.amount_paid = (sale.amount_paid or 0) - payment.amount
        if sale.amount_paid <= 0:
            sale.amount_paid = 0
            sale.payment_status = 'Unpaid'
        elif sale.amount_paid < sale.total_amount:
            sale.payment_status = 'Partial'
        else:
            sale.payment_status = 'Paid'
        sale.save()

        payment.delete()
        messages.success(request, f'Payment of PKR {payment.amount} removed.')

    return redirect('sale_detail', pk=sale.pk)