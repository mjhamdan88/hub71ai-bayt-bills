from __future__ import annotations

from typing import Iterable, Optional

from django.contrib.auth import get_user_model
from django.db import transaction

from unicrm.models import Contact


def _clean_email(email: Optional[str]) -> Optional[str]:
    """
    Normalise user emails for consistent comparisons.
    """
    if not email:
        return None
    cleaned = email.strip().lower()
    return cleaned or None


def _is_user_email_verified(user) -> bool:
    """
    Determine whether the user's email address has been verified.

    Supports common patterns (custom flags, django-allauth). Without any of the
    known markers the user is treated as unverified.
    """
    if getattr(user, 'is_superuser', False):
        return True

    for attr in ('is_email_verified', 'email_verified', 'email_confirmed'):
        value = getattr(user, attr, None)
        if value is not None:
            return bool(value)

    emailaddresses = getattr(user, 'emailaddress_set', None)
    if emailaddresses is not None:
        try:
            email = _clean_email(user.email)
            query = emailaddresses.filter(verified=True)
            if email:
                query = query.filter(email__iexact=email)
            if query.exists():
                return True
        except Exception:
            # fall back to broader check if the manager does not behave like a queryset
            try:
                return emailaddresses.filter(verified=True).exists()
            except Exception:
                pass

    return False


def ensure_contact_for_user(user) -> Contact:
    """
    Ensure a Contact instance exists for the supplied auth user.
    """
    email = _clean_email(user.email)
    if hasattr(user, 'get_username'):
        username_raw = user.get_username()
    else:
        username_raw = getattr(user, 'username', '')
    username = (username_raw or '').strip()

    first_name = (user.first_name or '').strip()
    last_name = (user.last_name or '').strip()

    is_verified = _is_user_email_verified(user)

    if not first_name and not last_name:
        first_name = username or (email.split('@')[0] if email else f"User {user.pk}")

    auth_attributes = {
        'auth_user_id': user.pk,
        'auth_user_email_verified': is_verified,
        'auth_user_has_email': bool(email),
    }
    if username:
        auth_attributes['auth_user_username'] = username

    with transaction.atomic():
        contact = Contact.objects.filter(user=user).first()

        if contact is None:
            contact = Contact.objects.filter(attributes__auth_user_id=user.pk).first()

        if contact is None and email:
            contact = Contact.objects.filter(email__iexact=email).first()

        if contact is None:
            contact = Contact.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                owner=user if user.is_staff else None,
                user=user,
                attributes=auth_attributes,
            )
            return contact

        update_fields: set[str] = set()

        if contact.user_id != user.pk:
            contact.user = user
            update_fields.add('user')

        current_email = _clean_email(contact.email)
        if current_email != email:
            if email:
                conflict_exists = Contact.objects.filter(email__iexact=email).exclude(pk=contact.pk).exists()
                if not conflict_exists:
                    contact.email = email
                    update_fields.add('email')
            else:
                contact.email = None
                update_fields.add('email')

        if contact.first_name != first_name:
            contact.first_name = first_name
            update_fields.add('first_name')

        if contact.last_name != last_name:
            contact.last_name = last_name
            update_fields.add('last_name')

        desired_owner = user if user.is_staff else None
        if contact.owner != desired_owner:
            contact.owner = desired_owner
            update_fields.add('owner')

        attributes = contact.attributes or {}
        for key, value in auth_attributes.items():
            if attributes.get(key) != value:
                attributes[key] = value
                update_fields.add('attributes')

        if update_fields:
            if 'attributes' in update_fields:
                contact.attributes = attributes
            contact.save(update_fields=[*update_fields, 'updated_at'])

        return contact


def sync_contacts_for_users(users: Iterable) -> None:
    """
    Ensure contacts exist for each provided user.
    """
    for user in users:
        ensure_contact_for_user(user)


def sync_all_user_contacts() -> None:
    """
    Ensure every auth user is represented as a contact.
    """
    UserModel = get_user_model()
    sync_contacts_for_users(UserModel.objects.all())
