"""
Approval views — Manager only.
Includes legacy payroll approval views (no longer reachable through UI).
"""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..decorators import role_required
from ..models import ApprovalLog, Employee, InventoryItem, Notification, Payroll
from .notifications import create_notification


@role_required('Manager')
def approval_list(request):
    pending_employees = Employee.objects.filter(approval_status='Pending', voided=False)
    pending_inventory = InventoryItem.objects.filter(approval_status='Pending', voided=False)
    return render(request, 'approvals/list.html', {
        'pending_employees': pending_employees,
        'pending_inventory': pending_inventory,
    })


@role_required('Manager')
def approve_employee(request, pk):
    emp = get_object_or_404(Employee, pk=pk)

    if request.method == 'POST':
        emp.approval_status = 'Approved'
        emp.approved_by = request.user
        emp.approved_at = timezone.now()
        emp.save()

        if emp.added_by:
            create_notification(
                emp.added_by,
                f'Your employee record for {emp.first_name} {emp.last_name} has been approved by {request.user.username}.',
                link=f'/employees/{emp.pk}/',
            )

        Notification.objects.filter(
            user=request.user,
            object_type='Employee',
            object_id=emp.pk,
            status='Pending',
        ).update(
            status='Approved',
            message=f'You approved employee {emp.first_name} {emp.last_name}.',
            is_read=True,
        )

        ApprovalLog.objects.create(
            object_type='Employee', object_id=emp.pk,
            object_label=f'{emp.first_name} {emp.last_name}',
            requested_by=emp.added_by or request.user,
            status='Approved', reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        messages.success(request, f'Employee {emp.first_name} {emp.last_name} approved.')
    return redirect('approval_list')


@role_required('Manager')
def reject_employee(request, pk):
    emp = get_object_or_404(Employee, pk=pk)

    if request.method == 'POST':
        emp.approval_status = 'Rejected'
        emp.save()

        if emp.added_by:
            create_notification(
                emp.added_by,
                f'Your employee record for {emp.first_name} {emp.last_name} was rejected by {request.user.username}.',
            )

        Notification.objects.filter(
            user=request.user,
            object_type='Employee',
            object_id=emp.pk,
            status='Pending',
        ).update(
            status='Rejected',
            message=f'You rejected employee {emp.first_name} {emp.last_name}.',
            is_read=True,
        )

        ApprovalLog.objects.create(
            object_type='Employee', object_id=emp.pk,
            object_label=f'{emp.first_name} {emp.last_name}',
            requested_by=emp.added_by or request.user,
            status='Rejected', reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        messages.warning(request, f'Employee {emp.first_name} {emp.last_name} rejected.')
    return redirect('approval_list')


@role_required('Manager')
def approve_inventory(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)

    if request.method == 'POST':
        item.approval_status = 'Approved'
        item.approved_by = request.user
        item.approved_at = timezone.now()
        item.save()

        if item.added_by:
            create_notification(
                item.added_by,
                f'Inventory item "{item.name}" has been approved by {request.user.username}.',
                link=f'/inventory/{item.pk}/edit/',
            )

        Notification.objects.filter(
            user=request.user,
            object_type='InventoryItem',
            object_id=item.pk,
            status='Pending',
        ).update(
            status='Approved',
            message=f'You approved inventory item "{item.name}".',
            is_read=True,
        )

        messages.success(request, f'Inventory item "{item.name}" approved.')
    return redirect('approval_list')


@role_required('Manager')
def reject_inventory(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)

    if request.method == 'POST':
        item.approval_status = 'Rejected'
        item.save()

        if item.added_by:
            create_notification(
                item.added_by,
                f'Inventory item "{item.name}" was rejected by {request.user.username}.',
            )

        Notification.objects.filter(
            user=request.user,
            object_type='InventoryItem',
            object_id=item.pk,
            status='Pending',
        ).update(
            status='Rejected',
            message=f'You rejected inventory item "{item.name}".',
            is_read=True,
        )

        messages.warning(request, f'Inventory item "{item.name}" rejected.')
    return redirect('approval_list')


# ---------------------------------------------------------------------
# LEGACY — kept so old URLs don't 404. Payroll no longer uses approval
# workflow, so these views are unreachable from the UI.
# ---------------------------------------------------------------------
@role_required('Manager')
def approve_payroll(request, pk):
    """LEGACY — payroll no longer goes through approval. Kept for URL compat."""
    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method == 'POST':
        if payroll.voided or payroll.status != 'Pending':
            messages.warning(request, 'This payroll is not waiting for approval.')
            return redirect('approval_list')

        name = f'{payroll.employee.first_name} {payroll.employee.last_name}'
        period = f'{payroll.get_month_display()} {payroll.year}'

        payroll.status = 'Approved'
        payroll.approved_by = request.user
        payroll.approved_at = timezone.now()
        payroll.save()

        if payroll.created_by:
            create_notification(
                payroll.created_by,
                f'Payroll for {name} ({period}) has been approved by {request.user.username}.',
                link=f'/payroll/{payroll.pk}/',
            )

        Notification.objects.filter(
            user=request.user,
            object_type='Payroll',
            object_id=payroll.pk,
            status='Pending',
        ).update(
            status='Approved',
            message=f'You approved payroll for {name} ({period}).',
            is_read=True,
        )

        messages.success(request, f'Payroll for {name} approved.')
    return redirect('approval_list')


@role_required('Manager')
def approve_payroll_paid(request, pk):
    """LEGACY — kept for URL compat."""
    payroll = get_object_or_404(Payroll, pk=pk)

    if request.method == 'POST':
        if payroll.voided or payroll.status != 'Paid Pending':
            messages.warning(request, 'This payment is not waiting for approval.')
            return redirect('approval_list')

        name = f'{payroll.employee.first_name} {payroll.employee.last_name}'
        period = f'{payroll.get_month_display()} {payroll.year}'

        payroll.status = 'Paid'
        payroll.payment_date = timezone.localdate()
        payroll.paid_by = request.user
        payroll.confirmed_at = timezone.now()
        payroll.employee_confirmed = True
        payroll.save()

        if payroll.paid_requested_by:
            create_notification(
                payroll.paid_requested_by,
                f'Payment for {name} ({period}) has been approved '
                f'and marked as PAID by {request.user.username}.',
                link=f'/payroll/{payroll.pk}/',
            )

        Notification.objects.filter(
            user=request.user,
            object_type='Payroll',
            object_id=payroll.pk,
            status='Pending',
        ).update(
            status='Approved',
            message=f'You approved payment for {name} ({period}).',
            is_read=True,
        )

        messages.success(request, 'Payment approved and marked as PAID.')
    return redirect('approval_list')