import base64
import mimetypes
import re
from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.urls import reverse
from unicom.services.get_public_origin import get_public_origin
from typing import Optional
from django.apps import apps
import string

def base62_encode(n: int) -> str:
    chars = string.digits + string.ascii_letters
    s = ''
    if n == 0:
        return chars[0]
    while n > 0:
        n, r = divmod(n, 62)
        s = chars[r] + s
    return s

def base62_decode(s: str) -> int:
    chars = string.digits + string.ascii_letters
    n = 0
    for c in s:
        n = n * 62 + chars.index(c)
    return n

def html_base64_images_to_shortlinks(html: str) -> tuple[str, list[int]]:
    """
    Converts base64 images in HTML to shortlinks, saves them as EmailInlineImage (email_message=None),
    and replaces <img src="data:image/..."> with <img src="shortlink">.
    Returns the modified HTML and the list of inline image pks.
    """
    EmailInlineImage = apps.get_model('unicom', 'EmailInlineImage')
    MessageTemplateInlineImage = apps.get_model('unicom', 'MessageTemplateInlineImage')
    if not html:
        return html
    soup = BeautifulSoup(html, 'html.parser')
    inline_image_pks = []
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if src.startswith('data:image/') and ';base64,' in src:
            header, b64data = src.split(';base64,', 1)
            mime = header.split(':')[1]
            ext = mimetypes.guess_extension(mime) or '.png'
            data = base64.b64decode(b64data)
            content_id = img.get('cid') or None
            image_obj = EmailInlineImage.objects.create(
                email_message=None,
                content_id=content_id
            )
            fname = f'inline_{image_obj.pk}{ext}'
            image_obj.file.save(fname, ContentFile(data), save=True)
            # Generate shortlink
            short_id = image_obj.get_short_id()
            path = reverse('inline_image', kwargs={'shortid': short_id})
            public_url = f"{get_public_origin().strip('/')}{path}"
            img['src'] = public_url
            inline_image_pks.append(image_obj.pk)
    return str(soup), inline_image_pks

def html_shortlinks_to_base64_images(html: str) -> str:
    """
    Converts <img src="shortlink"> in HTML to <img src="data:image/..."> by looking up EmailInlineImage or MessageTemplateInlineImage.
    Returns the modified HTML.
    """
    EmailInlineImage = apps.get_model('unicom', 'EmailInlineImage')
    MessageTemplateInlineImage = apps.get_model('unicom', 'MessageTemplateInlineImage')
    if not html:
        return html
    soup = BeautifulSoup(html, 'html.parser')
    for img_tag in soup.find_all('img'):
        src = img_tag.get('src', '')
        # Match /i/<shortid> or /t/<shortid> anywhere in the path, possibly with trailing slash
        m_i = re.search(r'/i/([A-Za-z0-9]+)(?:/)?', src)
        m_t = re.search(r'/t/([A-Za-z0-9]+)(?:/)?', src)
        if m_i:
            short_id = m_i.group(1)
            try:
                pk = base62_decode(short_id)
                image_obj = EmailInlineImage.objects.get(pk=pk)
                data = image_obj.file.read()
                image_obj.file.seek(0)
                mime = 'image/png'
                if hasattr(image_obj.file, 'file') and hasattr(image_obj.file.file, 'content_type'):
                    mime = image_obj.file.file.content_type
                elif image_obj.file.name:
                    mime = mimetypes.guess_type(image_obj.file.name)[0] or 'image/png'
                b64 = base64.b64encode(data).decode('ascii')
                img_tag['src'] = f'data:{mime};base64,{b64}'
            except Exception as e:
                continue
        elif m_t:
            short_id = m_t.group(1)
            try:
                pk = base62_decode(short_id)
                image_obj = MessageTemplateInlineImage.objects.get(pk=pk)
                data = image_obj.file.read()
                image_obj.file.seek(0)
                mime = 'image/png'
                if hasattr(image_obj.file, 'file') and hasattr(image_obj.file.file, 'content_type'):
                    mime = image_obj.file.file.content_type
                elif image_obj.file.name:
                    mime = mimetypes.guess_type(image_obj.file.name)[0] or 'image/png'
                b64 = base64.b64encode(data).decode('ascii')
                img_tag['src'] = f'data:{mime};base64,{b64}'
            except Exception as e:
                continue
    return str(soup)
