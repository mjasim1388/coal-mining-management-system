"""
Customer views: list, add, edit, void, autofill API.
"""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..decorators import role_required
from ..forms import CustomerForm
from ..models import Customer
from ._helpers import void_record


@role_required('Manager', 'Accountant', 'Viewer')
def customer_list(request):
    query = request.GET.get('q', '')
    show_voided = request.GET.get('show_voided', '')

    customers = Customer.objects.all()
    if not show_voided:
        customers = customers.filter(voided=False)

    if query:
        customers = customers.filter(name__icontains=query) | \
                    customers.filter(company__icontains=query) | \
                    customers.filter(phone__icontains=query)

    return render(request, 'sales/customer_list.html', {
        'customers': customers,
        'query': query,
        'show_voided': show_voided,
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


@role_required('Manager')
def customer_void(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if customer.voided:
        messages.warning(request, 'This customer is already voided.')
        return redirect('customer_list')

    if request.method == 'POST':
        reason = request.POST.get('void_reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for voiding.')
            return redirect('customer_void', pk=customer.pk)

        if void_record(customer, request.user, reason, request, customer.name):
            messages.success(request, f'Customer "{customer.name}" has been voided.')
        return redirect('customer_list')

    return render(request, 'shared/void_confirm.html', {
        'title': 'Void Customer',
        'object_label': customer.name,
        'object_type': 'Customer',
        'details': [
            ('Company', customer.company or '—'),
            ('Phone', customer.phone or '—'),
            ('NTN', customer.ntn or '—'),
        ],
        'cancel_url': 'customer_list',
    })


@role_required('Manager', 'Accountant')
def customer_autofill_api(request, pk):
    try:
        customer = Customer.objects.get(pk=pk)
    except Customer.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    return JsonResponse({
        'coal_type': customer.default_coal_type or '',
        'rate': float(customer.default_rate) if customer.default_rate else '',
        'truck_no': customer.default_truck_no or '',
        'driver_name': customer.default_driver_name or '',
        'driver_phone': customer.default_driver_phone or '',
        'mine_id': customer.default_mine.pk if customer.default_mine else '',
    })