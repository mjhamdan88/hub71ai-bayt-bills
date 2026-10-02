from django.db import models
from django.utils.translation import gettext_lazy as _
import re
from bs4 import BeautifulSoup
import base64
from django.core.files.base import ContentFile
from django.urls import reverse
from unicom.services.get_public_origin import get_public_origin
import openai
from django.conf import settings
from unicom.services.html_inline_images import html_base64_images_to_shortlinks
from .fields import DedupFileField, only_delete_file_if_unused

class MessageTemplate(models.Model):
    """Model for storing reusable message templates."""
    
    title = models.CharField(
        _('Title'),
        max_length=200,
        help_text=_('Template title/name for easy identification')
    )
    
    description = models.TextField(
        _('Description'),
        blank=True,
        help_text=_('Optional description of what this template is used for')
    )
    
    content = models.TextField(
        _('Content'),
        help_text=_('The HTML content of the template')
    )
    
    category = models.CharField(
        _('Category'),
        max_length=100,
        blank=True,
        help_text=_('Optional category for organizing templates')
    )

    channels = models.ManyToManyField(
        'Channel',
        verbose_name=_('Channels'),
        blank=True,
        help_text=_('Channels where this template can be used')
    )
    
    created_at = models.DateTimeField(
        _('Created at'),
        auto_now_add=True
    )
    
    updated_at = models.DateTimeField(
        _('Updated at'),
        auto_now=True
    )

    class Meta:
        verbose_name = _('Message Template')
        verbose_name_plural = _('Message Templates')
        ordering = ['category', 'title']

    def __str__(self):
        return self.title 

    @property
    def html_with_base64_images(self):
        """
        Returns the HTML content with all inline image shortlinks replaced by their original base64 data, if available.
        """
        if not self.content:
            return self.content
        soup = BeautifulSoup(self.content, 'html.parser')
        images = {img.get_short_id(): img for img in getattr(self, 'inline_images', [])}
        for img_tag in soup.find_all('img'):
            src = img_tag.get('src', '')
            m = re.search(r'/i/([A-Za-z0-9]+)', src)
            if m:
                short_id = m.group(1)
                image_obj = images.get(short_id)
                if image_obj:
                    data = image_obj.file.read()
                    image_obj.file.seek(0)
                    mime = 'image/png'
                    if hasattr(image_obj.file, 'file') and hasattr(image_obj.file.file, 'content_type'):
                        mime = image_obj.file.file.content_type
                    elif image_obj.file.name:
                        import mimetypes
                        mime = mimetypes.guess_type(image_obj.file.name)[0] or 'image/png'
                    b64 = base64.b64encode(data).decode('ascii')
                    img_tag['src'] = f'data:{mime};base64,{b64}'
        return str(soup)

    def save(self, *args, **kwargs):
        # First, save the template to ensure it has a PK
        is_new = self.pk is None
        super().save(*args, **kwargs)
        # Only process if content is present
        if self.content:
            from bs4 import BeautifulSoup
            import base64
            import mimetypes
            from django.core.files.base import ContentFile
            from django.urls import reverse
            from unicom.services.get_public_origin import get_public_origin
            soup = BeautifulSoup(self.content, 'html.parser')
            changed = False
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if src.startswith('data:image/') and ';base64,' in src:
                    header, b64data = src.split(';base64,', 1)
                    mime = header.split(':')[1]
                    ext = mimetypes.guess_extension(mime) or '.png'
                    data = base64.b64decode(b64data)
                    content_id = img.get('cid') or None
                    image_obj = MessageTemplateInlineImage.objects.create(
                        template=self,
                        content_id=content_id
                    )
                    fname = f'inline_{image_obj.pk}{ext}'
                    image_obj.file.save(fname, ContentFile(data), save=True)
                    short_id = image_obj.get_short_id()
                    path = reverse('template_inline_image', kwargs={'shortid': short_id})
                    public_url = f"{get_public_origin().rstrip('/')}{path}"
                    img['src'] = public_url
                    changed = True
            if changed:
                self.content = str(soup)
                # Save again to update content with shortlinks
                super().save(update_fields=['content'])

    def populate(self, html_prompt, custom_system_prompt=None, model="gpt-4o"):
        """
        Uses OpenAI GPT models to populate and customize the template content based on the given prompt.
        Returns the AI-generated content.
        """
        if not settings.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured in settings.")
        openai.api_key = settings.OPENAI_API_KEY
        system_prompt = (
            "You are a template population function. Given a message template (HTML) and a user prompt, "
            "populate the template with relevant content, customizing it as per the user's instructions. "
            "Do not use any placeholders in the output and treat it as a final ready to send email."
            "If the user didn't provide data for specific sections of the template you might have to remove that section from the output."
            "Your output MUST be valid HTML only, with NO markdown, code blocks, or plain text. "
            "Do NOT use any markdown formatting. Only output the populated HTML template. "
            "For clarity, you may wrap the system and user instructions in <p> tags if you need to reference them, but the main output must be the HTML template itself."
        ) if not custom_system_prompt else custom_system_prompt
        user_content = f"""
<p><b>System:</b> Populate the following HTML template as per the user prompt. Output only valid HTML, no markdown or plain text.</p>
<p><b>User Prompt:</b> {html_base64_images_to_shortlinks(html_prompt)[0]}</p>
<p><b>Template:</b></p>
{self.content}
"""
        try:
            response = openai.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")

class MessageTemplateInlineImage(models.Model):
    file = DedupFileField(upload_to='message_template_inline_images/', hash_field='hash')
    template = models.ForeignKey(MessageTemplate, on_delete=models.CASCADE, related_name='inline_images')
    created_at = models.DateTimeField(auto_now_add=True)
    content_id = models.CharField(max_length=255, blank=True, null=True, help_text='Content-ID for cid: references in HTML')
    hash = models.CharField(max_length=64, blank=True, null=True, db_index=True, help_text='SHA256 hash of file for deduplication')

    def delete(self, *args, **kwargs):
        only_delete_file_if_unused(self, 'file', 'hash')
        super().delete(*args, **kwargs)

    def get_short_id(self):
        import string
        chars = string.digits + string.ascii_letters
        n = self.pk
        s = ''
        if n == 0:
            return chars[0]
        while n > 0:
            n, r = divmod(n, 62)
            s = chars[r] + s
        return s 