"""
Global search API used by the topbar inline search.
"""
from django.db.models import Q
from django.http import JsonResponse

from ..decorators import role_required
from ..models import (
    Customer, Employee, Equipment, InventoryItem, Mine, Sale,
)


@role_required('Manager', 'Accountant', 'Viewer')
def global_search(request):
    q = request.GET.get('q', '').strip()

    if len(q) < 2:
        return JsonResponse({'results': [], 'query': q})

    results = []
    user_roles = set(request.user.groups.values_list('name', flat=True))
    is_viewer_only = (user_roles == {'Viewer'}) and not request.user.is_superuser

    if not is_viewer_only:
        for e in Employee.objects.filter(voided=False).filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(employee_code__icontains=q) |
            Q(cnic__icontains=q) |
            Q(phone__icontains=q)
        )[:5]:
            results.append({
                'type': 'Employee',
                'icon': 'bi-person-badge',
                'label': f'{e.employee_code} — {e.first_name} {e.last_name}',
                'sublabel': e.designation,
                'url': f'/employees/{e.pk}/',
            })

    for c in Customer.objects.filter(voided=False).filter(
        Q(name__icontains=q) |
        Q(company__icontains=q) |
        Q(phone__icontains=q)
    )[:5]:
        results.append({
            'type': 'Customer',
            'icon': 'bi-person-vcard',
            'label': c.name,
            'sublabel': c.company or c.phone or 'Customer',
            'url': f'/customers/{c.pk}/edit/' if not is_viewer_only else '/customers/',
        })

    for s in Sale.objects.filter(voided=False).filter(
        Q(dispatch_no__icontains=q) |
        Q(invoice_no__icontains=q) |
        Q(truck_no__icontains=q) |
        Q(driver_name__icontains=q) |
        Q(customer__name__icontains=q)
    ).select_related('customer')[:5]:
        results.append({
            'type': 'Dispatch',
            'icon': 'bi-receipt',
            'label': s.dispatch_no or s.invoice_no,
            'sublabel': f'{s.customer.name} — {s.quantity_tons} tons',
            'url': f'/sales/{s.pk}/',
        })

    if not is_viewer_only:
        for m in Mine.objects.filter(voided=False).filter(
            Q(name__icontains=q) |
            Q(location__icontains=q)
        )[:4]:
            results.append({
                'type': 'Mine',
                'icon': 'bi-geo-alt-fill',
                'label': m.name,
                'sublabel': m.location,
                'url': f'/mines/{m.pk}/edit/',
            })

    for eq in Equipment.objects.filter(voided=False).filter(
        Q(equipment_code__icontains=q) |
        Q(name__icontains=q) |
        Q(serial_number__icontains=q) |
        Q(model_number__icontains=q)
    )[:4]:
        results.append({
            'type': 'Equipment',
            'icon': 'bi-tools',
            'label': f'{eq.equipment_code} — {eq.name}',
            'sublabel': eq.equipment_type,
            'url': f'/equipment/{eq.pk}/',
        })

    for i in InventoryItem.objects.filter(voided=False).filter(
        Q(name__icontains=q) |
        Q(location__icontains=q)
    )[:4]:
        results.append({
            'type': 'Item',
            'icon': 'bi-box-seam',
            'label': i.name,
            'sublabel': f'{i.quantity} {i.unit} — {i.category}',
            'url': f'/inventory/{i.pk}/edit/' if not is_viewer_only else '/inventory/',
        })

    return JsonResponse({'results': results, 'query': q})