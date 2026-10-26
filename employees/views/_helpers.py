"""
Shared helpers used across view modules.
"""
from django.utils import timezone

from ..models import VoidLog


def distinct_values(queryset, field, limit=30):
    """Return a list of distinct non-empty values from a model field."""
    values = queryset.exclude(**{f'{field}__isnull': True}).exclude(**{field: ''})
    seen = []
    for v in values.values_list(field, flat=True).distinct():
        if v and str(v).strip() and str(v).strip() not in seen:
            seen.append(str(v).strip())
        if len(seen) >= limit:
            break
    return seen


def void_record(record, user, reason, request, object_label=''):
    """Void a record: sets void fields + creates VoidLog entry.
    Returns True if successful, False if already voided.
    """
    if getattr(record, 'voided', False):
        return False

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')

    record.voided = True
    record.voided_by = user
    record.voided_at = timezone.now()
    record.voided_reason = reason
    record.save()

    VoidLog.objects.create(
        object_type=record.__class__.__name__,
        object_id=record.pk,
        object_label=object_label or str(record),
        voided_by=user,
        reason=reason,
        ip_address=ip,
    )

    return True


def _is_manager_user(user):
    return user.is_superuser or user.groups.filter(name='Manager').exists()


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _parse_amount(raw, default):
    from decimal import Decimal, InvalidOperation
    text = str(raw or '').strip()
    if not text:
        return default
    try:
        return Decimal(text)
    except InvalidOperation:
        return default