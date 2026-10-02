from django.http import HttpResponse, Http404
from unicom.models import EmailInlineImage
from unicom.models.message_template import MessageTemplateInlineImage
import string

def base62_decode(s):
    chars = string.digits + string.ascii_letters
    n = 0
    for c in s:
        n = n * 62 + chars.index(c)
    return n

def serve_inline_image(request, shortid):
    try:
        pk = base62_decode(shortid)
        try:
            image = EmailInlineImage.objects.get(pk=pk)
        except EmailInlineImage.DoesNotExist:
            image = MessageTemplateInlineImage.objects.get(pk=pk)
        response = HttpResponse(image.file, content_type='image/*')
        filename = image.file.name.split('/')[-1]
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except (EmailInlineImage.DoesNotExist, MessageTemplateInlineImage.DoesNotExist, ValueError, IndexError):
        raise Http404('Image not found')

def serve_template_inline_image(request, shortid):
    try:
        pk = base62_decode(shortid)
        image = MessageTemplateInlineImage.objects.get(pk=pk)
        response = HttpResponse(image.file, content_type='image/*')
        filename = image.file.name.split('/')[-1]
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except (MessageTemplateInlineImage.DoesNotExist, ValueError, IndexError):
        raise Http404('Image not found') 