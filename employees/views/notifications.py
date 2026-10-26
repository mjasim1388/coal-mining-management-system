"""
Notification helpers and the notification list view.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..models import Notification


def create_notification(user, message, link=''):
    """Create a single notification for one user (no-op if user is None/anon)."""
    if user and user.is_authenticated:
        Notification.objects.create(user=user, message=message, link=link)


def notify_role(role_name, message, link='', status='Info', object_type='', object_id=None):
    """Notify every user in a group/role."""
    from django.contrib.auth.models import User
    users = User.objects.filter(groups__name=role_name)
    for user in users:
        Notification.objects.create(
            user=user,
            message=message,
            link=link,
            status=status,
            object_type=object_type,
            object_id=object_id,
        )


def notify_accountants(message, link='', status='Info', object_type='', object_id=None):
    notify_role('Accountant', message, link, status, object_type, object_id)


def notify_managers(message, link='', status='Info', object_type='', object_id=None):
    notify_role('Manager', message, link, status, object_type, object_id)


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user)
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return render(request, 'notifications/list.html', {'notifications': notifications})