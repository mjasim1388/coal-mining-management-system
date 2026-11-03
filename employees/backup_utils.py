import os
import shutil
import subprocess
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone

def run_database_backup():
    """
    Core function to trigger pg_dump. 
    Returns (success_boolean, message_string).
    """
    try:
        backup_dir = os.path.join(settings.BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        today_str = timezone.localtime().strftime('%Y-%m-%d')
        dated_filename = f'coalmining_{today_str}.dump'
        dated_filepath = os.path.join(backup_dir, dated_filename)

        master_filename = 'coalmining_backup.dump'
        master_filepath = os.path.join(backup_dir, master_filename)

        # Find pg_dump.exe
        pg_dump_path = shutil.which('pg_dump')
        if not pg_dump_path:
            for ver in ['18', '17', '16', '15', '14']:
                test_path = rf'C:\Program Files\PostgreSQL\{ver}\bin\pg_dump.exe'
                if os.path.exists(test_path):
                    pg_dump_path = test_path
                    break
        if not pg_dump_path:
            return False, 'pg_dump.exe not found.'

        db = settings.DATABASES['default']
        env = os.environ.copy()
        env['PGPASSWORD'] = str(db.get('PASSWORD', ''))

        # Run pg_dump
        result = subprocess.run(
            [
                pg_dump_path, '-U', db.get('USER') or 'postgres',
                '-h', db.get('HOST') or 'localhost',
                '-p', str(db.get('PORT') or '5432'),
                '-Fc', '-f', dated_filepath, db['NAME'],
            ],
            env=env, capture_output=True, text=True, timeout=120,
        )

        if result.returncode != 0:
            return False, f'Backup failed: {result.stderr}'

        shutil.copy2(dated_filepath, master_filepath)

        # Cleanup old backups (>7 days)
        cutoff_date = timezone.localdate() - timedelta(days=7)
        for fname in os.listdir(backup_dir):
            if fname.startswith('coalmining_') and fname.endswith('.dump') and fname != master_filename:
                try:
                    date_str = fname.replace('coalmining_', '').replace('.dump', '')
                    file_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if file_date < cutoff_date:
                        os.remove(os.path.join(backup_dir, fname))
                except (ValueError, OSError):
                    pass

        size_mb = os.path.getsize(dated_filepath) / (1024 * 1024)
        return True, f'Backup saved: {dated_filename} ({size_mb:.2f} MB)'

    except subprocess.TimeoutExpired:
        return False, 'Backup timed out after 2 minutes.'
    except Exception as e:
        return False, f'Backup error: {str(e)}'