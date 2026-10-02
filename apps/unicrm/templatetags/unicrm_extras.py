from django import template

register = template.Library()


@register.filter
def dict_get(value, key):
    """Safely fetch a value from a dict; returns empty string if missing."""
    if value is None:
        return ''
    try:
        return value.get(key, '')
    except AttributeError:
        return ''
