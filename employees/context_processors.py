from django.db.models import F
from .models import Employee, InventoryItem, Notification, Payroll

def user_role(request):
    if not request.user.is_authenticated:
        return {
            'user_role': '',
            'is_admin': False,
            'is_manager': False,
            'is_accountant': False,
            'is_viewer': False,
            'unread_notifications_count': 0,
            'pending_approvals_count': 0,
            'low_stock_count': 0,
        }

    if request.user.is_superuser:
        role = 'Admin'
    else:
        groups = list(request.user.groups.values_list('name', flat=True))
        role = groups[0] if groups else 'No Role'

    unread = Notification.objects.filter(user=request.user, is_read=False).count()
    
    # --- Calculate Sidebar Badges ---
    pending_approvals_count = 0
    low_stock_count = 0

    if role in ('Admin', 'Manager'):
        pending_approvals_count = (
            Employee.objects.filter(approval_status='Pending', voided=False).count() +
            InventoryItem.objects.filter(approval_status='Pending', voided=False).count() +
            Payroll.objects.filter(status='Pending', voided=False).count()
        )

    if role in ('Admin', 'Manager', 'Accountant'):
        # Super fast database query to find low stock
        low_stock_count = InventoryItem.objects.filter(
            quantity__lte=F('reorder_level'), 
            voided=False, 
            approval_status='Approved'
        ).count()

    return {
        'user_role': role,
        'is_admin': role == 'Admin',
        'is_manager': role in ('Admin', 'Manager'),
        'is_accountant': role in ('Admin', 'Accountant'),
        'is_viewer': role == 'Viewer',
        'unread_notifications_count': unread,
        'pending_approvals_count': pending_approvals_count,
        'low_stock_count': low_stock_count,
    }