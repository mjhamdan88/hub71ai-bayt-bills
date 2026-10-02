import base64
import os
import secrets
import sys
from urllib.parse import urlparse
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
text = path.read_text()
values = {
    "replace-with-a-long-random-value": secrets.token_urlsafe(64),
    "replace-with-a-strong-password": secrets.token_urlsafe(32),
    "replace-with-a-fernet-key": base64.urlsafe_b64encode(os.urandom(32)).decode(),
}
for old, new in values.items():
    text = text.replace(old, new)

# Portacode publishes the exposed service URL to automation shells.  Derive
# Django's host/origin settings from that value so the public health check and
# browser-facing features work on any device hostname.
public_url = os.environ.get("PORTACODE_PRIMARY_PUBLIC_URL", "").strip()
if public_url:
    parsed = urlparse(public_url)
    if parsed.hostname:
        replacements = {
            "DJANGO_ALLOWED_HOSTS": f"localhost,127.0.0.1,{parsed.hostname}",
            "DJANGO_PUBLIC_ORIGIN": public_url.rstrip("/"),
            "DJANGO_CSRF_TRUSTED_ORIGINS": public_url.rstrip("/"),
        }
        lines = text.splitlines()
        for key, value in replacements.items():
            for index, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[index] = f"{key}={value}"
                    break
            else:
                lines.append(f"{key}={value}")
        text = "\n".join(lines) + "\n"

for key in ("DJANGO_SUPERUSER_USERNAME", "DJANGO_SUPERUSER_EMAIL", "DJANGO_SUPERUSER_PASSWORD"):
    value = os.environ.get(key)
    if value:
        # Compose single-quoted values preserve password dollars and hashes.
        value = "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[index] = f"{key}={value}"
                break
        else:
            lines.append(f"{key}={value}")
        text = "\n".join(lines) + "\n"
path.write_text(text)
path.chmod(0o600)
