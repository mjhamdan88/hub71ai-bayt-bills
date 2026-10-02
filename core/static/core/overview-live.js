(() => {
  const selector = '[data-live], dialog[data-live-dialog]';
  let refreshing = false;
  let pointerTarget = null;
  const dirty = element => Array.from(element.querySelectorAll('input,select,textarea')).some(input => {
    if (input.type === 'hidden') return false;
    if (input.tagName === 'SELECT') {
      const initial = Array.from(input.options).findIndex(option => option.defaultSelected);
      return input.selectedIndex !== (initial < 0 ? 0 : initial);
    }
    if (['checkbox', 'radio'].includes(input.type)) return input.checked !== input.defaultChecked;
    return input.value !== input.defaultValue;
  });
  const protectedRegion = element => element.matches('dialog[open]') ||
    element.contains(document.activeElement) || (pointerTarget && element.contains(pointerTarget)) || dirty(element);
  const signature = element => {
    const copy = element.cloneNode(true);
    copy.querySelectorAll('input[name="csrfmiddlewaretoken"]').forEach(input => input.remove());
    return copy.innerHTML;
  };
  document.addEventListener('pointerdown', event => { pointerTarget = event.target; }, true);
  for (const name of ['pointerup', 'pointercancel']) document.addEventListener(name, () => {
    setTimeout(() => { pointerTarget = null; }, 0);
  }, true);
  document.addEventListener('change', event => {
    if (!event.target.matches('.method-select select')) return;
    event.target.form.querySelector('button').hidden = !dirty(event.target.form);
  });
  async function refresh() {
    if (refreshing || document.hidden) return;
    refreshing = true;
    try {
      const response = await fetch('/?fragment=overview', {cache: 'no-store', headers: {'Accept': 'text/html'}});
      if (!response.ok || response.redirected) return;
      const fresh = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (!fresh.querySelector('[data-live="summary"]')) return;
      const dialogIds = new Set(Array.from(fresh.querySelectorAll('dialog'), dialog => dialog.id));
      // Patch independent display regions, never the chat or an active/edited form.
      for (const next of fresh.querySelectorAll(selector)) {
        const key = next.dataset.live;
        const current = key ? document.querySelector(`[data-live="${CSS.escape(key)}"]`) : document.getElementById(next.id);
        if (!current) {
          if (next.matches('dialog')) document.querySelector('#chat-toggle').before(next);
          continue;
        }
        if (!protectedRegion(current) && signature(current) !== signature(next)) current.replaceWith(next);
      }
      for (const current of document.querySelectorAll('dialog[data-live-dialog]')) {
        if (!dialogIds.has(current.id) && !protectedRegion(current)) current.remove();
      }
    } catch (_) {
      // Keep the last good view and retry on the next interval.
    } finally { refreshing = false; }
  }
  document.addEventListener('finance-data-changed', refresh);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  document.addEventListener('close', event => {
    if (event.target.matches('dialog[data-live-dialog]')) refresh();
  }, true);
  window.addEventListener('focus', refresh);
  setInterval(refresh, 5000);
})();
