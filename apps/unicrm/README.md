# Unicrm Setup Guide

Unicrm provides CRM models, templates, and campaign tooling that can be dropped into any Django project. It depends on **django-unicom**, so make sure Unicom is installed and configured before proceeding.

At a glance you get:

- Models for `Company`, `Contact`, `MailingList`, `Subscription`, `Segment`, `TemplateVariable`, `Communication`, and `CommunicationMessage`.
- Django-admin integration with code editors (via Django Ace) for template variables and segments, plus live previews.
- A templating runtime that renders communications through a sandboxed Jinja2 environment (`unicrm.services.template_renderer`).
- Staff dashboards at `/unicrm/communications/` showing campaign status, per-contact delivery metadata, and delivery preparation actions.
- Evergreen communications that can keep sending to new contacts who qualify for a segment after the initial launch.
- Engagement tracking for opens, clicks, and recipient replies, surfaced on delivery dashboards.
- A template-variable API used by the TinyMCE integration to offer CRM placeholders.

## 1. Install

Install the apps into your environment (order matters: Unicom first, then Unicrm):

```bash
pip install django-unicom
pip install django-unicrm
```

## 2. Configure Django

Add the required apps to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # …
    "django.contrib.humanize",  # Required for {% load humanize %} in Unicrm templates
    "django_ace",  # Code editor for segments and template variables
    "unicom",      # Messaging primitives used by Unicrm
    "unicrm",      # CRM models and dashboards
]
```

If you use a custom user model, define `AUTH_USER_MODEL` before importing `unicrm`.

## 3. Include URLs

Expose Unicrm endpoints in your root `urls.py`:

```python
from django.urls import include, path

urlpatterns = [
    # …
    path("unicrm/", include("unicrm.urls")),
]
```

This enables staff dashboards at `/unicrm/communications/` plus supporting APIs.

## 4. Run migrations

Apply the Unicrm migrations:

```bash
python manage.py migrate unicrm
```

The final migration fires a post-migrate hook that seeds default segments and ensures every auth user has a matching `Contact`.

## 5. Contact auto-sync

Unicrm wires its signals automatically—no extra registration needed. Behind the scenes:

- `post_save` on the active auth model maintains the corresponding `Contact`.
- `post_migrate` backfills both contacts and default segments.

To force a full resync manually:

```bash
python manage.py shell -c "from unicrm.services.user_contact_sync import sync_all_user_contacts; sync_all_user_contacts()"
```

## 6. Optional settings

| Setting | Purpose | Default |
| --- | --- | --- |
| `UNICRM_AUTO_START_SCHEDULER` | Auto-start the communication delivery scheduler when ASGI workers launch. | `True` |
| `UNICRM_SCHEDULER_INTERVAL` | Poll interval (seconds) for delivery preparation. | `10` |
| `UNICRM_DELIVERY_BURST_LIMIT` | Number of contacts to queue immediately before dripping the rest. | `4` |
| `UNICRM_DELIVERY_DRIP_MIN_MINUTES` | Minimum minutes between each throttled delivery. | `1` |
| `UNICRM_DELIVERY_DRIP_MAX_MINUTES` | Maximum minutes between each throttled delivery. | `2` |
| `GETPROSPECT_API_KEY` | Required for lead search/email reveal tools (GetProspect web-app endpoint). | `""` |
| `UNICRM_GP_POLL_INTERVAL` | Interval (seconds) for the background GetProspect email poller (runs in web server processes). | `60` |
| `UNICRM_DISABLE_GP_POLLER` | Set to `True` to disable the GetProspect email poller. | `False` |
| `UNICRM_UNSUBSCRIBE_PATH` | Path for the public unsubscribe page (joined with `DJANGO_PUBLIC_ORIGIN`). | `/unicrm/unsubscribe/` |
| `UNICRM_CONTACT_COOLDOWN_HOURS` | Cooldown window before sending another email to the same contact. | `24` |
| `UNICRM_CONTACT_UNENGAGED_LIMIT` | Number of outbound attempts without opens/clicks/replies before marking future sends as failed. | `3` |

### Mass mailing & drip throttling

Unicrm treats any communication targeting more contacts than `UNICRM_DELIVERY_BURST_LIMIT` as a mass mailing. The first `burst_limit` contacts are queued immediately, while the rest are “dripped” out one by one. Each additional delivery is assigned a randomized delay between `UNICRM_DELIVERY_DRIP_MIN_MINUTES` and `UNICRM_DELIVERY_DRIP_MAX_MINUTES`, which keeps SMTP providers happy and mimics human-paced outreach.

When you embed Unicrm inside your own Django project you can expose these controls through environment variables in `settings.py`:

```python
import os

UNICRM_DELIVERY_BURST_LIMIT = int(os.environ.get("UNICRM_DELIVERY_BURST_LIMIT", 25))
UNICRM_DELIVERY_DRIP_MIN_MINUTES = int(os.environ.get("UNICRM_DELIVERY_DRIP_MIN_MINUTES", 2))
UNICRM_DELIVERY_DRIP_MAX_MINUTES = int(os.environ.get("UNICRM_DELIVERY_DRIP_MAX_MINUTES", 5))

# GetProspect integration (lead search/email reveal)
GETPROSPECT_API_KEY = os.getenv("GETPROSPECT_API_KEY", "")
UNICRM_GP_POLL_INTERVAL = int(os.environ.get("UNICRM_GP_POLL_INTERVAL", 60))
UNICRM_DISABLE_GP_POLLER = os.environ.get("UNICRM_DISABLE_GP_POLLER", "").lower() == "true"
```

Increasing the burst limit or narrowing the drip window makes campaigns finish faster; lowering them adds more breathing room between messages. Pick values that respect the hourly send limits of your ESP.

Shared settings inherited from Unicom (e.g., `DJANGO_PUBLIC_ORIGIN`, `UNICOM_TINYMCE_API_KEY`) should also be configured when applicable.

### Unsubscribe links & public page

- Built-in template variables:
  - `{{ variables.unsubscribe_link }}` / `{{ variables.unsubscribe_link_url }}` → signed unsubscribe URL for the contact (and mailing list when available).
  - `{{ variables.unsubscribe_link_html }}` → ready-made anchor tag (`<a href="...">Unsubscribe</a>`).
- Public endpoint: `/unicrm/unsubscribe/` accepts `?token=...` and offers “this list” (when provided) or “all” unsubscribe options plus optional feedback. Adjust the path via `UNICRM_UNSUBSCRIBE_PATH`.
- Tokens include contact id, optional mailing list id/slug, and optional communication id; links are signed, not guessable.
- Delivery guards: contacts with UnsubscribeAll, recent-contact cooldown, or repeated unengaged sends are marked failed with a reason; configure via the settings above.
- To rebuild per-contact interaction caches (communication history JSON): `python manage.py refresh_contact_cache [--contact-id N]`.

## 7. Scheduled communications command

Unicrm exposes a management command for preparing and sending deliveries for scheduled communications:

```bash
# Run continuously (default 10-second interval)
python manage.py send_scheduled_communications

# Custom interval
python manage.py send_scheduled_communications --interval 30

# Single pass for debugging
python manage.py send_scheduled_communications --run-once -vv
```

Use this alongside your existing Unicom worker setup when you want Unicrm campaigns to deliver automatically.

## 9. Lead search & email reveal (GetProspect)

If you use the GetProspect-based lead search/email-reveal tools:

- Set `GETPROSPECT_API_KEY` in your environment and expose it to Django settings.
- Apply migrations (includes `0014_contact_gp_fields` for `gp_requested_at`, `gp_email_checked_at`, `gp_email_status`).
- Ensure the web server process loads the key (e.g., via `env_file` or env vars).
- Tools/templates:
  - `lead_search_v2_tool.py` (search via GetProspect web-app endpoint)
  - `save_new_leads_tool.py` (user-confirmed email requests; charges credits)
  - `sync_getprospect_saved_contacts` management command to bulk sync saved contacts/emails (`requestType="included"`).
- Background poller:
  - Runs only in web server processes (gated by settings); interval via `UNICRM_GP_POLL_INTERVAL`.
  - Polls recently requested contacts (`gp_requested_at`) with no email and updates emails/status when found; set `UNICRM_DISABLE_GP_POLLER=True` to turn it off.

## 8. Operating checklist

1. Populate Companies, Contacts, Mailing Lists, and Subscriptions via Django admin.
2. Define template variables under **Unicrm → Template variables** (default snippets live in `unicrm/templates/unicrm/snippets/`).
3. Create or adjust segments via the admin – code snippets are executed through a safe helper before each campaign.
4. Compose communications in the admin, select a channel, segment, template, optional subject, and schedule.
5. Review delivery status from the admin dashboard at `/admin/unicrm/communication/<id>/deliveries/`, jump into chats via *View Chat*, and enable *Auto-send to new segment members* for campaigns that should keep enrolling future contacts automatically.
