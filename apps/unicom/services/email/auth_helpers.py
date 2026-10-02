from __future__ import annotations
from typing import Tuple


def get_email_service_credentials(config: dict, service: str) -> Tuple[str | None, str | None]:
    """
    Return the credentials that should be used for the given service (IMAP or SMTP),
    falling back to the shared EMAIL_ADDRESS/EMAIL_PASSWORD values when overrides
    like IMAP_USERNAME or SMTP_PASSWORD are not provided.
    """
    service_key = service.upper()
    if service_key not in {'IMAP', 'SMTP'}:
        raise ValueError(f"Unknown service for email credentials: {service}")

    shared_username = config.get('EMAIL_ADDRESS')
    shared_password = config.get('EMAIL_PASSWORD')
    username = config.get(f'{service_key}_USERNAME')
    password = config.get(f'{service_key}_PASSWORD')

    if username is None:
        username = shared_username
    if password is None:
        password = shared_password

    return username, password
