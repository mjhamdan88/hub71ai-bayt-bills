# Example template variable snippet.
# The system expects a function named `compute(contact)` that returns a string.
# You can access `contact`, `contact.company`, and any custom attributes.

def compute(contact):
    """
    Return the contact's preferred display name.
    """
    first = (contact.first_name or '').strip()
    last = (contact.last_name or '').strip()
    if first or last:
        return f"{first} {last}".strip()
    # Fall back to a value stored in the `attributes` JSON or the email address.
    nickname = contact.attributes.get('nickname')
    return nickname or contact.email

