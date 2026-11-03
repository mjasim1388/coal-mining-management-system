"""
Backup views — Manager only.
"""
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from ..decorators import role_required


from ..backup_utils import run_database_backup
from ..models import SystemSettings

@role_required('Manager')
def backup_now(request):
    if request.method == 'POST':
        success, message = run_database_backup()
        if success:
            messages.success(request, f'✅ {message}')
            return redirect('backup_list')
        else:
            messages.error(request, f'❌ {message}')
            return redirect('dashboard')

    return render(request, 'backup/confirm.html')

@role_required('Manager')
def backup_list(request):
    backup_dir = os.path.join(settings.BASE_DIR, 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    backups = []
    for fname in os.listdir(backup_dir):
        if not fname.endswith('.dump'):
            continue
        fpath = os.path.join(backup_dir, fname)
        stat = os.stat(fpath)
        backups.append({
            'filename': fname,
            'is_master': fname == 'coalmining_backup.dump',
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'modified': timezone.datetime.fromtimestamp(stat.st_mtime),
            'modified_ts': stat.st_mtime,
        })

    backups.sort(key=lambda x: (not x['is_master'], -x['modified_ts']))

    total_size = sum(b['size_mb'] for b in backups)
    dated_count = sum(1 for b in backups if not b['is_master'])

    system_settings = SystemSettings.load()
    
    return render(request, 'backup/list.html', {
        'backups': backups,
        'total_size': round(total_size, 2),
        'count': len(backups),
        'dated_count': dated_count,
        'system_settings': system_settings, # Pass it to the UI
    })

    return render(request, 'backup/list.html', {
        'backups': backups,
        'total_size': round(total_size, 2),
        'count': len(backups),
        'dated_count': dated_count,
    })


@role_required('Manager')
def backup_download(request, filename):
    if '/' in filename or '\\' in filename or '..' in filename:
        raise Http404("Invalid filename")

    filepath = os.path.join(settings.BASE_DIR, 'backups', filename)
    if not os.path.exists(filepath):
        raise Http404("File not found")

    return FileResponse(
        open(filepath, 'rb'),
        as_attachment=True,
        filename=filename,
    )

@role_required('Manager')
def update_backup_time(request):
    if request.method == 'POST':
        new_time = request.POST.get('backup_time')
        if new_time:
            settings = SystemSettings.load()
            settings.backup_time = new_time
            settings.save()
            messages.success(request, f'Automated backup time updated to {new_time}.')
        return redirect('backup_list')