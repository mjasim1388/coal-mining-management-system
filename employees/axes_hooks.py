"""
Custom lockout handler for django-axes.
Renders the login page with a professional countdown
that does NOT reset on further login attempts.

The unlock timestamp is computed ONCE per (username, ip) pair and
stored in Django's cache. Every subsequent request reads the same
timestamp, so the countdown ticks down normally regardless of
whether the user submits more attempts (correct or wrong password).
"""
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render
from django.utils import timezone


def lockout_response(request, credentials=None, *args, **kwargs):
    """Called by django-axes when a login attempt is locked out."""

    # --- Cooloff duration ---
    cooloff = getattr(settings, 'AXES_COOLOFF_TIME', timedelta(minutes=5))
    if hasattr(cooloff, 'total_seconds'):
        cooloff_seconds = int(cooloff.total_seconds())
    else:
        cooloff_seconds = int(cooloff) * 3600

    # --- Identify this lockout ---
    ip = request.META.get('REMOTE_ADDR', '')
    username = (credentials or {}).get('username', '') or ''

    cache_key = f'axes_lockout_end:{username}:{ip}'
    lockout_end_ts = cache.get(cache_key)
    now_ts = timezone.now().timestamp()

    # --- Compute unlock time ONCE (first time we see this lockout) ---
    if lockout_end_ts is None:
        remaining = cooloff_seconds
        try:
            from axes.models import AccessAttempt
            attempt = AccessAttempt.objects.filter(
                ip_address=ip,
                username=username,
            ).order_by('-last_attempt').first()
            if attempt and attempt.last_attempt:
                elapsed = (timezone.now() - attempt.last_attempt).total_seconds()
                remaining = max(0, cooloff_seconds - elapsed)
        except Exception:
            pass

        lockout_end_ts = now_ts + remaining
        # Freeze in cache; TTL = cooloff + 1 min buffer
        cache.set(cache_key, lockout_end_ts, timeout=cooloff_seconds + 60)

    # --- Always report remaining based on the frozen timestamp ---
    remaining = max(0, int(lockout_end_ts - now_ts))

    if remaining <= 0:
        cache.delete(cache_key)

    return render(request, 'registration/login.html', {
        'locked_out': True,
        'lockout_seconds': remaining,
        'lockout_username': username,
    }, status=429)