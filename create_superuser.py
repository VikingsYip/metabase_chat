"""
Create a Django superuser for development.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'metabase_chat.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# Check if superuser already exists
username = 'admin'
email = 'admin@example.com'
password = 'admin123'

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(
        username=username,
        email=email,
        password=password
    )
    print(f"[OK] Superuser created successfully!")
    print(f"  Username: {username}")
    print(f"  Password: {password}")
    print(f"  Email: {email}")
    print(f"\nYou can now login at: http://localhost:8001/admin/")
else:
    print(f"[OK] Superuser '{username}' already exists.")
