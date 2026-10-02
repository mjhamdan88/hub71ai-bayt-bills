from bs4 import BeautifulSoup
from django.urls import reverse
from django.conf import settings
from unicom.services.get_public_origin import get_public_origin
import re
import uuid

# Unique identifiers for our tracking elements
TRACKING_PIXEL_CLASS = 'e-px-' # Will be followed by tracking ID
TRACKING_LINK_CLASS = 'e-lc-'  # Will be followed by tracking ID
TRACKING_LINK_INDEX_ATTR = 'data-link-index'


def add_tracking_pixel(html_content: str, tracking_id: uuid.UUID) -> str:
    """
    Add a 1x1 transparent tracking pixel to HTML email content.
    The pixel will have a unique class name that includes the tracking ID.
    """
    if not html_content:
        return html_content

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Create tracking pixel with unique identifier
    tracking_url = f"{get_public_origin()}{reverse('e_px', args=[tracking_id])}"
    pixel = soup.new_tag('img', 
                        src=tracking_url,
                        width="1",
                        height="1",
                        style="display:none",
                        **{'class': f"{TRACKING_PIXEL_CLASS}{tracking_id}"})
    
    # Add pixel to the end of the body, or create body if it doesn't exist
    if soup.body:
        soup.body.append(pixel)
    else:
        body = soup.new_tag('body')
        body.append(pixel)
        soup.append(body)
    
    return str(soup)


def wrap_links(html_content: str, tracking_id: uuid.UUID) -> tuple[str, list[str]]:
    """
    Wrap all links in the HTML content with tracking URLs.
    Each wrapped link will have a unique class and data attribute for the link index.
    Returns tuple of (modified_html, original_urls)
    """
    if not html_content:
        return html_content, []

    soup = BeautifulSoup(html_content, 'html.parser')
    original_urls = []
    
    # Find all links
    for link in soup.find_all('a', href=True):
        original_url = link['href']
        
        # Skip mailto: links and anchor links
        if original_url.startswith(('mailto:', '#', 'tel:')):
            continue
            
        # Store original URL and create tracking URL with index
        original_urls.append(original_url)
        link_index = len(original_urls) - 1
        tracking_url = f"{get_public_origin()}{reverse('e_lc', args=[tracking_id, link_index])}"
        link['href'] = tracking_url
        link['class'] = link.get('class', []) + [f"{TRACKING_LINK_CLASS}{tracking_id}"]
        link[TRACKING_LINK_INDEX_ATTR] = str(link_index)
    
    return str(soup), original_urls


def prepare_email_for_tracking(html_content: str, tracking_id: uuid.UUID) -> tuple[str, list[str]]:
    """
    Prepare an HTML email for tracking by adding a tracking pixel and wrapping links.
    Returns tuple of (modified_html, original_urls)
    """
    if not html_content:
        return html_content, []
        
    # First wrap all links
    html_with_wrapped_links, original_urls = wrap_links(html_content, tracking_id)
    
    # Then add tracking pixel
    final_html = add_tracking_pixel(html_with_wrapped_links, tracking_id)
    
    return final_html, original_urls


def remove_tracking(html_content: str, original_urls: list[str]) -> str:
    """
    Remove tracking elements and restore original URLs in an HTML email.
    """
    if not html_content:
        return html_content

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove tracking pixels
    for pixel in soup.find_all('img', class_=re.compile(f'^{TRACKING_PIXEL_CLASS}')):
        pixel.decompose()
    
    # Restore original URLs
    for link in soup.find_all('a', class_=re.compile(f'^{TRACKING_LINK_CLASS}')):
        try:
            link_index = int(link.get(TRACKING_LINK_INDEX_ATTR, -1))
            if 0 <= link_index < len(original_urls):
                link['href'] = original_urls[link_index]
            # Remove tracking attributes
            link['class'] = [c for c in link.get('class', []) 
                           if not c.startswith((TRACKING_LINK_CLASS, TRACKING_PIXEL_CLASS))]
            if not link['class']:  # Remove empty class attribute
                del link['class']
            del link[TRACKING_LINK_INDEX_ATTR]
        except (ValueError, IndexError):
            continue
    
    return str(soup) 