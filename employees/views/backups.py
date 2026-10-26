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


@role_required('Manager')
def backup_now(request):
    from datetime import timedelta

    if request.method == 'POST':
        try:
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')
            os.makedirs(backup_dir, exist_ok=True)

            today_str = timezone.localtime().strftime('%Y-%m-%d')
            dated_filename = f'coalmining_{today_str}.dump'
            dated_filepath = os.path.join(backup_dir, dated_filename)

            master_filename = 'coalmining_backup.dump'
            master_filepath = os.path.join(backup_dir, master_filename)

            pg_dump_path = shutil.which('pg_dump')
            if not pg_dump_path:
                for ver in ['18', '17', '16', '15', '14']:
                    test_path = rf'C:\Program Files\PostgreSQL\{ver}\bin\pg_dump.exe'
                    if os.path.exists(test_path):
                        pg_dump_path = test_path
                        break
            if not pg_dump_path:
                messages.error(request, 'pg_dump.exe not found. Please check PostgreSQL installation path.')
                return redirect('dashboard')

            db = settings.DATABASES['default']
            env = os.environ.copy()
            env['PGPASSWORD'] = str(db.get('PASSWORD', ''))

            result = subprocess.run(
                [
                    pg_dump_path,
                    '-U', db.get('USER') or 'postgres',
                    '-h', db.get('HOST') or 'localhost',
                    '-p', str(db.get('PORT') or '5432'),
                    '-Fc', '-f', dated_filepath,
                    db['NAME'],
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                messages.error(request, f'Backup failed: {result.stderr}')
                return redirect('dashboard')

            shutil.copy2(dated_filepath, master_filepath)

            cutoff_date = timezone.localdate() - timedelta(days=7)
            removed_count = 0
            for fname in os.listdir(backup_dir):
                if not (fname.startswith('coalmining_') and fname.endswith('.dump')):
                    continue
                if fname == master_filename:
                    continue
                try:
                    date_str = fname.replace('coalmining_', '').replace('.dump', '')
                    from datetime import datetime
                    file_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if file_date < cutoff_date:
                        os.remove(os.path.join(backup_dir, fname))
                        removed_count += 1
                except (ValueError, OSError):
                    pass

            size_mb = os.path.getsize(dated_filepath) / (1024 * 1024)

            msg = f'✅ Backup saved: {dated_filename} ({size_mb:.2f} MB)'
            if removed_count > 0:
                msg += f' — cleaned up {removed_count} old backup(s)'

            messages.success(request, msg)
            return redirect('backup_list')

        except subprocess.TimeoutExpired:
            messages.error(request, 'Backup timed out after 2 minutes.')
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f'Backup error: {str(e)}')
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