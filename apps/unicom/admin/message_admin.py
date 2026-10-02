from django.contrib import admin
from django.urls import path
from django.http import HttpResponse, Http404
from django.utils.text import slugify
from ..models import Message

# We should add a try-except block for the import, as weasyprint might not be installed
try:
    from weasyprint import HTML
except ImportError:
    HTML = None

# Prefer using a real browser (Chromium via Playwright) for pixel-perfect PDF output.
# This preserves selectable text & vector graphics. Fallback to WeasyPrint if Playwright
# is unavailable or PDF rendering fails.
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

# Helper to render HTML → PDF with Playwright/Chromium.
def _html_to_pdf_playwright(html: str) -> bytes:
    """Render *html* string to PDF using headless Chromium via Playwright.

    Returns PDF bytes. Raises RuntimeError on failure.
    """
    if not sync_playwright:
        raise RuntimeError("Playwright is not installed")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()

            # Load the HTML content. `about:blank` is implicit, we directly set content.
            page.set_content(html, wait_until="load")

            # Generate the PDF. print_background=True ensures backgrounds/images are rendered.
            pdf_bytes = page.pdf(format="A4", print_background=True)
            browser.close()
            return pdf_bytes
    except Exception as exc:
        raise RuntimeError(f"Playwright PDF generation failed: {exc}") from exc

def download_pdf_view(request, message_id):
    if not HTML:
        raise Http404("WeasyPrint is not installed. Please install it to use this feature.")
    
    try:
        # The message ID can be a complex string, so we use pk
        message = Message.objects.get(pk=message_id)
    except Message.DoesNotExist:
        raise Http404("Message not found")

    if message.platform != 'Email':
        raise Http404("PDF download is only available for email messages.")

    # Use original_content as requested, with a fallback
    html_string = message.original_content_with_cdn_icons
    if not html_string and message.text:
        # Simple text-to-html for plaintext emails
        html_string = f"<html><body><pre>{message.text}</pre></body></html>"
    elif not html_string:
        html_string = "<html><body><p>Message content is empty.</p></body></html>"

    # --- PDF generation ----------------------------------------------------
    pdf_file: bytes | None = None

    # First try Playwright/Chromium for modern CSS support.
    if sync_playwright:
        try:
            pdf_file = _html_to_pdf_playwright(html_string)
        except Exception:
            # Playwright failed; we'll try WeasyPrint (if available) before giving up.
            pdf_file = None

    # Fallback to WeasyPrint if Playwright wasn't available or errored out.
    if pdf_file is None:
        if HTML:
            pdf_file = HTML(string=html_string).write_pdf()
        else:
            raise Http404(
                "PDF generation is not available. Install Playwright (recommended) or WeasyPrint."
            )

    # Generate a safe filename from the subject, or fall back to message ID
    if message.subject:
        filename = f"{slugify(message.subject)}.pdf"
    else:
        filename = f"message_{message_id}.pdf"
    
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class MessageAdmin(admin.ModelAdmin):
    # This will be used for the change list view
    list_display = ('__str__', 'platform', 'chat', 'is_outgoing', 'timestamp')
    list_filter = ('platform', 'is_outgoing', 'channel')
    search_fields = ('id', 'subject', 'text', 'chat__name')
    readonly_fields = [field.name for field in Message._meta.fields]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<path:message_id>/download_pdf/', self.admin_site.admin_view(download_pdf_view), name='unicom_message_download_pdf'),
        ]
        return custom_urls + urls

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False 