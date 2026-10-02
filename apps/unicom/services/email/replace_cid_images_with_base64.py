import base64
import re
from email import message_from_bytes, policy
from bs4 import BeautifulSoup
from typing import Optional
import mimetypes

def replace_cid_images_with_base64(raw_message_bytes: bytes) -> Optional[str]:
    """
    Given raw email bytes, find all <img src="cid:..."> in the HTML part,
    replace them with base64 data URLs from the corresponding attachments,
    and return the modified HTML. If no HTML part is found, returns None.
    """
    msg = message_from_bytes(raw_message_bytes, policy=policy.default)

    # Find HTML part
    html = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == 'text/html':
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or 'utf-8'
                html = payload.decode(charset, errors='replace')
                break
    if not html:
        return None

    # Build a map of Content-ID (without <>) to attachment part
    cid_to_part = {}
    for part in msg.walk():
        if part.get_content_disposition() == 'attachment' or part.get_content_disposition() == 'inline':
            cid = part.get('Content-ID')
            if cid:
                cid = cid.strip('<>')
                cid_to_part[cid] = part

    soup = BeautifulSoup(html, 'html.parser')
    for img in soup.find_all('img'):
        src = img.get('src', '')
        m = re.match(r'cid:(.+)', src)
        if m:
            cid = m.group(1)
            part = cid_to_part.get(cid)
            if part:
                data = part.get_payload(decode=True)
                if data:
                    mime = part.get_content_type() or 'application/octet-stream'
                    b64 = base64.b64encode(data).decode('ascii')
                    img['src'] = f'data:{mime};base64,{b64}'
    return str(soup) 