import os
import sys
from pathlib import Path

import django

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
if not username or not password:
    raise SystemExit("DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD are required")

User = get_user_model()
user, created = User.objects.get_or_create(username=username, defaults={"email": email})
user.email = email
user.is_staff = True
user.is_superuser = True
if created or not user.has_usable_password():
    user.set_password(password)
user.save()
print(f"superuser {'created' if created else 'updated'}: {username}")
