/**
 * Minimal morphdom-style DOM patcher for message HTML updates.
 * Keeps existing nodes when possible to preserve client-side state (e.g. scroll/details open).
 */

function isSameNodeType(fromNode, toNode) {
  if (fromNode.nodeType !== toNode.nodeType) return false;
  if (fromNode.nodeType !== Node.ELEMENT_NODE) return true;
  return fromNode.tagName === toNode.tagName;
}

function syncAttributes(fromEl, toEl) {
  // Remove attributes no longer present, while preserving runtime-expanded details.
  for (const attr of Array.from(fromEl.attributes)) {
    if (attr.name === 'open' && fromEl.tagName === 'DETAILS' && fromEl.open && !toEl.hasAttribute('open')) {
      continue;
    }
    if (!toEl.hasAttribute(attr.name)) {
      fromEl.removeAttribute(attr.name);
    }
  }

  // Add/update attributes from target.
  for (const attr of Array.from(toEl.attributes)) {
    if (fromEl.getAttribute(attr.name) !== attr.value) {
      fromEl.setAttribute(attr.name, attr.value);
    }
  }
}

function morphNode(fromNode, toNode) {
  if (!isSameNodeType(fromNode, toNode)) {
    fromNode.replaceWith(toNode.cloneNode(true));
    return;
  }

  if (fromNode.nodeType === Node.TEXT_NODE) {
    if (fromNode.nodeValue !== toNode.nodeValue) {
      fromNode.nodeValue = toNode.nodeValue;
    }
    return;
  }

  if (fromNode.nodeType !== Node.ELEMENT_NODE) {
    return;
  }

  const fromEl = fromNode;
  const toEl = toNode;
  syncAttributes(fromEl, toEl);
  morphChildren(fromEl, toEl);
}

function morphChildren(fromParent, toParent) {
  const fromChildren = Array.from(fromParent.childNodes);
  const toChildren = Array.from(toParent.childNodes);
  const max = Math.max(fromChildren.length, toChildren.length);

  for (let i = 0; i < max; i += 1) {
    const fromChild = fromParent.childNodes[i];
    const toChild = toChildren[i];

    if (!fromChild && toChild) {
      fromParent.appendChild(toChild.cloneNode(true));
      continue;
    }
    if (fromChild && !toChild) {
      fromParent.removeChild(fromChild);
      continue;
    }
    morphNode(fromChild, toChild);
  }
}

export function morphdom(fromNode, toNode, options = {}) {
  if (!fromNode || !toNode) return fromNode;
  if (options.childrenOnly) {
    morphChildren(fromNode, toNode);
    return fromNode;
  }
  morphNode(fromNode, toNode);
  return fromNode;
}

