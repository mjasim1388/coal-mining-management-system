from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required


def role_required(*allowed_roles):
    """Only allow superusers or users in one of the given roles."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            user_roles = set(request.user.groups.values_list('name', flat=True))
            if user_roles & set(allowed_roles):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped
    return decorator


def get_user_role(user):
    """Return the user's primary role name, or 'Admin' if superuser."""
    if user.is_superuser:
        return 'Admin'
    groups = list(user.groups.values_list('name', flat=True))
    return groups[0] if groups else 'No Role'