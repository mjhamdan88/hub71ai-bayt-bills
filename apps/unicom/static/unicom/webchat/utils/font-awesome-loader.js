/**
 * Font Awesome loader for Lit components.
 * Injects the stylesheet into a shadow root so icon classes work inside the shadow DOM.
 */
const FONT_AWESOME_URL = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css';

let preloadPromise = null;

function preloadStylesheet() {
  if (preloadPromise) return preloadPromise;

  preloadPromise = new Promise((resolve) => {
    // If already present in the document, resolve immediately.
    if (document.head.querySelector('link[data-font-awesome-global]')) {
      resolve();
      return;
    }

    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = FONT_AWESOME_URL;
    link.crossOrigin = 'anonymous';
    link.setAttribute('data-font-awesome-global', 'true');

    link.addEventListener('load', () => resolve());
    link.addEventListener('error', (err) => {
      console.error('Font Awesome failed to load', err);
      resolve(); // Resolve to avoid blocking UI even if FA fails
    });

    document.head.append(link);
  });

  return preloadPromise;
}

async function applyToShadowRoot(shadowRoot) {
  if (!shadowRoot) return;

  // No-op if the shadow root already has the stylesheet.
  if (shadowRoot.querySelector('link[data-font-awesome]')) return;

  await preloadStylesheet();

  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = FONT_AWESOME_URL;
  link.crossOrigin = 'anonymous';
  link.setAttribute('data-font-awesome', 'true');

  // Resolve once this link finishes (or fails) to avoid hanging callers.
  const ready = new Promise((resolve) => {
    link.addEventListener('load', () => resolve());
    link.addEventListener('error', (err) => {
      console.error('Font Awesome failed to load in shadow root', err);
      resolve();
    });
  });

  // Prepend so icon font is available before other styles.
  shadowRoot.prepend(link);

  return ready;
}

export default { applyToShadowRoot, FONT_AWESOME_URL };
