from .models import Notification


def user_role(request):
    if not request.user.is_authenticated:
        return {
            'user_role': '',
            'is_admin': False,
            'is_manager': False,
            'is_accountant': False,
            'is_viewer': False,
            'unread_notifications_count': 0,
        }

    if request.user.is_superuser:
        role = 'Admin'
    else:
        groups = list(request.user.groups.values_list('name', flat=True))
        role = groups[0] if groups else 'No Role'

    unread = Notification.objects.filter(user=request.user, is_read=False).count()

    return {
        'user_role': role,
        'is_admin': role == 'Admin',
        'is_manager': role in ('Admin', 'Manager'),
        'is_accountant': role in ('Admin', 'Accountant'),
        'is_viewer': role == 'Viewer',
        'unread_notifications_count': unread,
    }