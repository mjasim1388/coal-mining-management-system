from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


ROLES = {
    'Manager': 'Full access to everything except user management',
    'Accountant': 'Production, attendance, inventory, payroll, sales',
    'Viewer': 'Read-only dashboard access',
}


class Command(BaseCommand):
    help = 'Create default user roles (Manager, Accountant, Viewer)'

    def handle(self, *args, **options):
        for role_name, description in ROLES.items():
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created role: {role_name}'))
            else:
                self.stdout.write(self.style.WARNING(f'Role already exists: {role_name}'))

        self.stdout.write(self.style.SUCCESS('All roles are ready.'))