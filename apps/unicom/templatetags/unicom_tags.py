"""
Django template tags for Unicom WebChat component.
"""
from django import template
from django.utils.safestring import mark_safe
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def webchat_component(
    api_base='/unicom/webchat',
    chat_id=None,
    channel_id=None,
    theme='light',
    max_messages=50,
    auto_refresh=5,
    height='600px',
    **custom_styles
):
    """
    Render the WebChat LitElement component.

    Usage in template:
        {% load unicom_tags %}
        {% webchat_component theme="dark" primary_color="#ff5722" %}

    Parameters:
        api_base: Base URL for WebChat APIs (default: '/unicom/webchat')
        chat_id: Specific chat ID (optional)
        channel_id: Specific channel ID (optional)
        theme: 'light' or 'dark' (default: 'light')
        max_messages: Max messages to load (default: 50)
        auto_refresh: Auto-refresh interval in seconds (default: 5, 0 to disable)
        height: Container height (default: '600px')
        **custom_styles: CSS custom properties (primary_color, background_color, etc.)

    Available custom style properties:
        - primary_color: Primary brand color
        - background_color: Background color
        - text_color: Text color
        - message_bg_incoming: Incoming message background
        - message_bg_outgoing: Outgoing message background
        - message_text_incoming: Incoming message text color
        - message_text_outgoing: Outgoing message text color
        - border_color: Border color
        - border_radius: Border radius
        - font_family: Font family
        - max_width: Max width of component
    """
    # Build component attributes
    attrs = [
        f'api-base="{api_base}"',
        f'theme="{theme}"',
        f'max-messages="{max_messages}"',
        f'auto-refresh="{auto_refresh}"',
    ]

    if chat_id:
        attrs.append(f'chat-id="{chat_id}"')
    if channel_id:
        attrs.append(f'channel-id="{channel_id}"')

    # Build inline style for custom CSS properties
    styles = []
    css_var_mapping = {
        'primary_color': '--unicom-primary-color',
        'secondary_color': '--unicom-secondary-color',
        'background_color': '--unicom-background-color',
        'text_color': '--unicom-text-color',
        'message_bg_incoming': '--unicom-message-bg-incoming',
        'message_bg_outgoing': '--unicom-message-bg-outgoing',
        'message_text_incoming': '--unicom-message-text-incoming',
        'message_text_outgoing': '--unicom-message-text-outgoing',
        'border_color': '--unicom-border-color',
        'border_radius': '--unicom-border-radius',
        'font_family': '--unicom-font-family',
        'max_width': '--unicom-max-width',
    }

    for key, css_var in css_var_mapping.items():
        if key in custom_styles:
            styles.append(f'{css_var}: {custom_styles[key]}')

    # Add height to container
    if height:
        styles.append(f'height: {height}')

    style_attr = f'style="{"; ".join(styles)}"' if styles else ''

    # Generate HTML
    html = f'''
    <script type="module" src="https://cdn.jsdelivr.net/npm/lit@3/+esm"></script>
    <script type="module" src="{static("unicom/webchat/webchat-component.js")}"></script>
    <unicom-chat {" ".join(attrs)} {style_attr}></unicom-chat>
    '''

    return mark_safe(html)
