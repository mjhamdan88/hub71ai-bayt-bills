"""
Migrate guest webchat data to authenticated user.
"""
from django.apps import apps
from django.db import transaction


def migrate_guest_to_user(old_session_key, user):
    """
    Migrate all guest chats to authenticated user.
    Called after user login/registration.

    Args:
        old_session_key: Previous session key (for guest account)
        user: Django User instance

    Returns:
        User Account instance
    """
    Account = apps.get_model('unicom', 'Account')
    Member = apps.get_model('unicom', 'Member')
    Message = apps.get_model('unicom', 'Message')
    Request = apps.get_model('unicom', 'Request')
    AccountChat = apps.get_model('unicom', 'AccountChat')
    Channel = apps.get_model('unicom', 'Channel')

    guest_account_id = f"webchat_guest_{old_session_key}"
    user_account_id = f"webchat_user_{user.id}"

    with transaction.atomic():
        # Get or create WebChat channel
        channel = Channel.objects.filter(platform='WebChat', active=True).first()
        if not channel:
            # No WebChat channel exists, nothing to migrate
            return None

        # Get or create user account
        name = user.get_full_name() or user.username
        user_account, created = Account.objects.get_or_create(
            id=user_account_id,
            defaults={
                'platform': 'WebChat',
                'channel': channel,
                'name': name,
                'raw': {'user_id': user.id}
            }
        )

        # Link to Member model
        if not user_account.member:
            try:
                member = Member.objects.filter(email=user.email).first()
                if not member:
                    member = Member.objects.create(
                        name=name,
                        email=user.email,
                        user=user
                    )
                user_account.member = member
                user_account.save(update_fields=['member'])
            except Exception as e:
                print(f"Warning: Could not link account to member: {e}")

        # Find guest account
        try:
            guest_account = Account.objects.get(id=guest_account_id, platform='WebChat')
        except Account.DoesNotExist:
            # No guest data to migrate
            return user_account

        # Transfer all messages from guest to user
        Message.objects.filter(sender=guest_account).update(sender=user_account)

        # Transfer all requests from guest to user
        Request.objects.filter(account=guest_account).update(
            account=user_account,
            member=user_account.member
        )

        # Transfer all chats from guest to user
        guest_chats = AccountChat.objects.filter(account=guest_account)

        for account_chat in guest_chats:
            chat = account_chat.chat

            # For chats where chat_id == guest_account_id (single chat per account pattern),
            # update the chat name to reflect the new user
            if chat.id == guest_account_id:
                chat.name = f"Chat with {user_account.name}"
                chat.save(update_fields=['name'])

            # Check if user account is already linked to this chat
            user_account_chat, created = AccountChat.objects.get_or_create(
                account=user_account,
                chat=chat
            )

            # Delete guest link
            account_chat.delete()

        # Delete guest account
        guest_account.delete()

        print(f"Migrated guest account {guest_account_id} to user account {user_account_id}")

        return user_account
