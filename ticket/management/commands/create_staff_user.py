from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Creates a staff user'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='The email for the staff user')
        parser.add_argument('password', type=str, help='The password for the staff user')

    def handle(self, *args, **options):
        email = options['email']
        password = options['password']
        
        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password
            )
            user.is_staff = True
            user.save()
            
            self.stdout.write(self.style.SUCCESS(
                f'Successfully created staff user: {email}'
            ))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f'Failed to create staff user: {str(e)}'
            ))
