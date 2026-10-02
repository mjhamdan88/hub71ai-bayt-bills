"""
WebChat account management.
Handles account creation and retrieval for both authenticated and guest users.
"""
from django.apps import apps


def get_or_create_account(channel, request):
    """
    Get or create WebChat account based on Django auth state.

    For authenticated users:
        - Account ID: webchat_user_{user.id}
        - Automatically links to Member model if exists

    For guest users:
        - Account ID: webchat_guest_{session_key}
        - Ensures session is created

    Args:
        channel: WebChat Channel instance
        request: Django HTTP request object

    Returns:
        Account instance
    """
    Account = apps.get_model('unicom', 'Account')
    Member = apps.get_model('unicom', 'Member')

    user = request.user

    if user.is_authenticated:
        # Authenticated user
        account_id = f"webchat_user_{user.id}"
        name = user.get_full_name() or user.username

        account, created = Account.objects.get_or_create(
            id=account_id,
            defaults={
                'platform': 'WebChat',
                'channel': channel,
                'name': name,
                'raw': {'user_id': user.id}
            }
        )

        # Link to Member model if exists and not already linked
        if not account.member:
            try:
                # Try to find member by user's email
                member = Member.objects.filter(email=user.email).first()

                if not member:
                    # Create member for this user
                    member = Member.objects.create(
                        name=name,
                        email=user.email,
                        user=user
                    )

                account.member = member
                account.save(update_fields=['member'])
            except Exception as e:
                print(f"Warning: Could not link account to member: {e}")

        return account

    else:
        # Guest user
        # Ensure session exists
        if not request.session.session_key:
            request.session.create()

        session_key = request.session.session_key
        account_id = f"webchat_guest_{session_key}"

        account, created = Account.objects.get_or_create(
            id=account_id,
            defaults={
                'platform': 'WebChat',
                'channel': channel,
                'name': 'Guest User',
                'raw': {'session_key': session_key, 'is_guest': True}
            }
        )

        return account
