from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Return dictionary item by key safely."""
    if isinstance(mapping, dict):
        return mapping.get(key, "")
    return ""
