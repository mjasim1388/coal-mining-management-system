from django.core.management.base import BaseCommand
from django.utils import timezone
from employees.models import SystemSettings, Notification
from employees.backup_utils import run_database_backup
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Checks if it is time to run the automated backup.'

    def handle(self, *args, **kwargs):
        settings = SystemSettings.load()
        now = timezone.localtime()

        # If today's backup is already done, exit.
        if settings.last_auto_backup == now.date():
            return

        # Check if current time has passed the scheduled backup time
        if now.time() >= settings.backup_time:
            self.stdout.write("Time matched. Starting automated backup...")
            success, message = run_database_backup()

            if success:
                # Mark as done for today
                settings.last_auto_backup = now.date()
                settings.save()
                self.stdout.write(self.style.SUCCESS(message))

                # Notify Managers
                managers = User.objects.filter(groups__name='Manager')
                for m in managers:
                    Notification.objects.create(
                        user=m, 
                        message=f"Automated Nightly Backup successful: {message}",
                        link="/backup/list/"
                    )
            else:
                self.stdout.write(self.style.ERROR(message))