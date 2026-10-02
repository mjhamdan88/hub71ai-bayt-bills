import re
from bs4 import BeautifulSoup, Tag, NavigableString
from difflib import SequenceMatcher

REPLY_HEADER_REGEX = re.compile(
    r'((On .+?wrote:)|([0-9]{1,2}:[0-9]{2} ?[ap]m,? .+? <.+?>:)|'  # original
    r'(From: .+?\n)|'  # From: ...\n
    r'(To: .+?\n)|'    # To: ...\n
    r'(Subject: .+?\n)|' # Subject: ...\n
    r'([0-9]{1,2}:[0-9]{2}\s*[ap]m,? .+?\n)|' # time, name, email\n
    r'([A-Za-z]{3,9},? \d{1,2} [A-Za-z]{3,9} \d{4} .+?\n)|' # date, name, email\n
    r'(Sent: .+?\n)|' # Sent: ...\n
    r'(\b[A-Za-z]+: .+?\n)' # Any header-like line
    r')',
    re.IGNORECASE | re.DOTALL
)

def normalize_text(text):
    # Lowercase, strip, collapse whitespace, remove non-breaking spaces and invisible chars
    text = text.replace('\xa0', ' ').replace('\u200b', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.lower().strip()

def is_similar(a, b, threshold=0.85):
    return SequenceMatcher(None, a, b).ratio() > threshold

def get_direct_text(element):
    # Clone the element, remove all nested blockquotes, then extract all text
    html = str(element)
    print('---BLOCKQUOTE HTML---')
    print(html[:1000])
    print('---BLOCKQUOTE HTML BYTES---')
    print(repr(html.encode(errors='replace')[:1000]))
    try:
        clone = BeautifulSoup(html, 'lxml')
    except Exception:
        clone = BeautifulSoup(html, 'html.parser')
    for nested in clone.find_all('blockquote'):
        nested.decompose()
    raw_text = clone.get_text()
    if not raw_text.strip():
        print('Fallback: using element.get_text()')
        raw_text = element.get_text()
    if not raw_text.strip():
        print('Fallback: using regex extraction')
        m = re.search(r'<blockquote.*?>(.*?)</blockquote>', html, re.DOTALL | re.IGNORECASE)
        if m:
            raw_text = BeautifulSoup(m.group(1), 'lxml').get_text()
    print('---BLOCKQUOTE RAW TEXT---')
    print(repr(raw_text[:1000]))
    text = raw_text.strip()
    print('---BLOCKQUOTE EXTRACTED TEXT---')
    print(text[:1000])
    return text

def remove_reply_header(block):
    # Remove previous siblings that are reply headers or <br> tags
    prev = block.previous_sibling
    while prev:
        to_remove = None
        # If it's a <br> or whitespace, remove and continue
        if isinstance(prev, Tag) and prev.name == 'br':
            to_remove = prev
        elif isinstance(prev, Tag) and prev.name in ('div', 'span', 'p'):
            # Check text content for reply header
            if REPLY_HEADER_REGEX.search(prev.get_text()):
                to_remove = prev
            else:
                break
        elif isinstance(prev, NavigableString):
            if REPLY_HEADER_REGEX.search(str(prev)) or str(prev).strip() == '':
                to_remove = prev
            else:
                break
        else:
            break
        next_prev = prev.previous_sibling
        prev.extract()
        prev = next_prev
    # Additionally, try to remove a sequence of header lines in the parent if present
    parent = block.parent
    if parent:
        # Look for a sequence of header-like lines just before the block
        header_lines = []
        for sibling in reversed(list(parent.children)):
            if sibling == block:
                break
            if isinstance(sibling, Tag) and sibling.name == 'br':
                continue
            if isinstance(sibling, (Tag, NavigableString)):
                text = sibling.get_text() if isinstance(sibling, Tag) else str(sibling)
                if REPLY_HEADER_REGEX.search(text):
                    header_lines.append(sibling)
                elif text.strip() == '':
                    continue
                else:
                    break
        for header in header_lines:
            header.extract()

def filter_redundant_quoted_content(html: str, chat, references: list[str]):
    """
    Remove quoted blocks from html if their direct text matches referenced messages in the chat.
    Only removes a quote if it matches the referenced message (by id in references).
    Handles nested blockquotes recursively.
    """
    if not html or not references or not chat:
        return html
    from unicom.models import Message
    soup = BeautifulSoup(html, 'html.parser')

    # Reverse references to process newest first
    ref_ids = list(references)[::-1]

    def process_blockquote(block, ref_ids):
        if not ref_ids:
            return
        ref_id = ref_ids[0]
        try:
            msg = chat.messages.filter(id=ref_id).first()
        except Exception:
            msg = None
        if not msg:
            return
        block_direct_text = normalize_text(get_direct_text(block))
        msg_html = msg.html or msg.text or ''
        msg_text = normalize_text(BeautifulSoup(msg_html, 'html.parser').get_text())
        print('---BLOCKQUOTE---')
        print(block_direct_text[:500])
        print('---MSG TEXT---')
        print(msg_text[:500])
        sim = SequenceMatcher(None, block_direct_text, msg_text).ratio()
        print(f'Similarity: {sim}')
        if sim > 0.85:
            remove_reply_header(block)
            block.decompose()
            return True
        return False

    def recursive_filter(element, ref_ids):
        for bq in element.find_all('blockquote', recursive=False):
            if ref_ids:
                matched = process_blockquote(bq, ref_ids)
                if matched:
                    ref_ids.pop(0)
                    continue
                recursive_filter(bq, ref_ids[1:])

    recursive_filter(soup, ref_ids)
    return str(soup) 