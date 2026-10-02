/**
 * Message Item Component
 * Renders individual message with media support
 */
import { LitElement, html, css } from 'lit';
import { iconStyles, messageStyles } from '../webchat-styles.js';
import { formatTimestamp } from '../utils/datetime-formatter.js';
import fontAwesomeLoader from '../utils/font-awesome-loader.js';
import { morphdom } from '../utils/morphdom.js';

export class MessageItem extends LitElement {
  static properties = {
    message: { type: Object },
    loadingButtons: { type: Set },
  };

  static styles = [iconStyles, messageStyles];

  constructor() {
    super();
    this.message = null;
    this.loadingButtons = new Set();
    this._elapsedTimer = null;
    this._lastRenderedHtml = null;
    this._viewerImage = null;
    this._viewerZoom = 1;
    this._handleViewerKeydown = this._handleViewerKeydown.bind(this);
  }

  async firstUpdated() {
    await fontAwesomeLoader.applyToShadowRoot(this.shadowRoot);
    this._morphMessageHtml();
    this._syncElapsedTimerState();
  }

  updated(changedProperties) {
    super.updated(changedProperties);
    if (changedProperties.has('message')) {
      this._morphMessageHtml();
      this._syncElapsedTimerState();
    }
  }

  disconnectedCallback() {
    this._stopElapsedTimer();
    window.removeEventListener('keydown', this._handleViewerKeydown);
    super.disconnectedCallback();
  }

  _sanitizeHTML(html) {
    // Basic HTML sanitization
    // For production, consider using a library like DOMPurify
    const div = document.createElement('div');
    div.textContent = html;
    return div.innerHTML;
  }

  _formatTimestamp(timestamp) {
    return formatTimestamp(timestamp);
  }

  _getMessageHtmlPayload() {
    if (!this.message) return '';
    if (this.message.media_type !== 'html') return '';
    const rawHtml = this.message.html || '';
    if (rawHtml) return rawHtml;
    return this._sanitizeHTML(this.message.text || '');
  }

  _morphMessageHtml() {
    const container = this.shadowRoot?.querySelector('.message-html');
    if (!container) return;

    const nextHtml = this._getMessageHtmlPayload();
    if (nextHtml === this._lastRenderedHtml) return;

    const temp = document.createElement('div');
    temp.innerHTML = nextHtml;
    morphdom(container, temp, { childrenOnly: true });
    this._lastRenderedHtml = nextHtml;
  }

  _syncElapsedTimerState() {
    const html = this._getMessageHtmlPayload();
    const hasRunningElapsed = html.includes('data-terminal-elapsed=');
    if (hasRunningElapsed) {
      this._startElapsedTimer();
      this._updateElapsedTimerDisplay();
      return;
    }
    this._stopElapsedTimer();
  }

  _startElapsedTimer() {
    if (this._elapsedTimer) return;
    this._elapsedTimer = setInterval(() => {
      this._updateElapsedTimerDisplay();
    }, 250);
  }

  _stopElapsedTimer() {
    if (!this._elapsedTimer) return;
    clearInterval(this._elapsedTimer);
    this._elapsedTimer = null;
  }

  _updateElapsedTimerDisplay() {
    const root = this.shadowRoot;
    if (!root) return;
    const nodes = root.querySelectorAll('[data-terminal-elapsed]');
    if (!nodes.length) return;

    const now = Date.now();
    nodes.forEach((node) => {
      const baseSeconds = Number(node.getAttribute('data-elapsed-seconds') || 0);
      const serverNowMs = Number(node.getAttribute('data-server-now-ms') || now);
      const extraSeconds = Math.max(0, Math.floor((now - serverNowMs) / 1000));
      const elapsedSeconds = Math.max(0, baseSeconds + extraSeconds);
      const nextText = `Elapsed: ${elapsedSeconds}s`;
      if (node.textContent !== nextText) {
        node.textContent = nextText;
      }
    });
  }

  _renderInteractiveButtons(buttons) {
    if (!buttons || !buttons.length) return '';
    
    return html`
      <div class="interactive-buttons">
        ${buttons.map(row => html`
          <div class="button-row">
            ${row.map(button => {
              const isLoading = this.loadingButtons.has(button.callback_execution_id);
              return html`
                <button 
                  class="interactive-btn ${button.style || 'primary'}"
                  @click=${() => this._handleButtonClick(button)}
                  ?disabled=${button.disabled || isLoading}>
                  ${isLoading
                    ? html`<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i>`
                    : button.text}
                </button>
              `;
            })}
          </div>
        `)}
      </div>
    `;
  }

  _handleButtonClick(button) {
    if (button.type === 'url') {
      window.open(button.url, '_blank');
      return;
    }
    
    if (button.type === 'callback' && button.callback_execution_id) {
      // Prevent multiple clicks
      if (this.loadingButtons.has(button.callback_execution_id)) return;
      
      // Add to loading set
      this.loadingButtons.add(button.callback_execution_id);
      this.requestUpdate();
      
      // Send button click to backend
      fetch('/unicom/webchat/button-click/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this._getCSRFToken()
        },
        body: JSON.stringify({
          callback_execution_id: button.callback_execution_id
        })
      }).then(response => {
        if (!response.ok) {
          console.error('Button click failed:', response.statusText);
        }
      }).catch(error => {
        console.error('Button click error:', error);
      }).finally(() => {
        // Remove from loading set
        this.loadingButtons.delete(button.callback_execution_id);
        this.requestUpdate();
      });
    }
  }

  _getCSRFToken() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'csrftoken') {
        return value;
      }
    }
    return '';
  }

  _handleHtmlInteractions(event) {
    const toggleButton = event.target && event.target.closest
      ? event.target.closest('.diff-review-toggle')
      : null;
    if (toggleButton) {
      event.preventDefault();
      const body = toggleButton.closest('.diff-review-file-body');
      if (!body || body.getAttribute('data-has-full') === 'false') return;
      const currentMode = body.getAttribute('data-view-mode') === 'full' ? 'full' : 'minimal';
      const nextMode = currentMode === 'minimal' ? 'full' : 'minimal';
      body.setAttribute('data-view-mode', nextMode);
      toggleButton.textContent = nextMode === 'minimal' ? 'Show All Lines' : 'Show Changes Only';
      return;
    }
  }

  _openImageModal(url, details = {}) {
    this._viewerImage = { url, ...details };
    this._viewerZoom = 1;
    window.addEventListener('keydown', this._handleViewerKeydown);
    this.requestUpdate();
    this.updateComplete.then(() => this.shadowRoot?.querySelector('.image-viewer')?.focus());
  }

  _closeImageModal() {
    this._viewerImage = null;
    window.removeEventListener('keydown', this._handleViewerKeydown);
    this.requestUpdate();
  }

  _handleViewerKeydown(event) {
    if (!this._viewerImage) return;
    if (event.key === 'Escape') this._closeImageModal();
    else if (event.key === '+' || event.key === '=') this._viewerZoom = Math.min(4, this._viewerZoom + .25);
    else if (event.key === '-') this._viewerZoom = Math.max(.5, this._viewerZoom - .25);
    else if (event.key === '0') this._viewerZoom = 1;
    else return;
    event.preventDefault();
    this.requestUpdate();
  }

  _renderImageViewer() {
    const image = this._viewerImage;
    if (!image) return html``;
    const source = String(image.filename || image.caption || '').split(/[?#]/)[0];
    const candidate = source.split('/').pop();
    const subtype = String(image.url || '').match(/^data:image\/(png|jpe?g|gif|webp|bmp|avif);/i)?.[1];
    const filename = candidate && /\.[a-z0-9]{2,5}$/i.test(candidate)
      ? candidate
      : `image.${subtype === 'jpeg' ? 'jpg' : subtype || 'png'}`;
    return html`<div class="image-viewer" role="dialog" aria-modal="true" aria-label="Image viewer" tabindex="-1" @click=${(event) => { if (event.target === event.currentTarget) this._closeImageModal(); }}>
      <header><div><strong>${filename}</strong>${image.caption ? html`<small>${image.caption}</small>` : ''}</div><div class="image-viewer-actions"><button @click=${() => { this._viewerZoom = Math.max(.5, this._viewerZoom - .25); this.requestUpdate(); }} ?disabled=${this._viewerZoom <= .5} aria-label="Zoom out"><i class="fa-solid fa-minus"></i></button><span>${Math.round(this._viewerZoom * 100)}%</span><button @click=${() => { this._viewerZoom = Math.min(4, this._viewerZoom + .25); this.requestUpdate(); }} ?disabled=${this._viewerZoom >= 4} aria-label="Zoom in"><i class="fa-solid fa-plus"></i></button><button @click=${() => { this._viewerZoom = 1; this.requestUpdate(); }}><i class="fa-solid fa-expand"></i> Fit</button><a href=${image.url} download=${filename}><i class="fa-solid fa-download"></i> Download</a><button @click=${() => this._closeImageModal()} aria-label="Close"><i class="fa-solid fa-xmark"></i></button></div></header>
      <div class="image-viewer-canvas"><img src=${image.url} alt=${image.alt || 'Image'} style=${`transform:scale(${this._viewerZoom})`}></div>
      ${image.alt ? html`<footer>${image.alt}</footer>` : ''}
    </div>`;
  }

  _renderMessageContent(message) {
    switch (message.media_type) {
      case 'text':
        return html`<div class="message-text">${message.text}</div>`;

      case 'html':
        return html`<div class="message-html" @click=${this._handleHtmlInteractions}></div>`;

      case 'image':
        return html`
          <div class="message-media">
            ${message.text && message.text !== '**Image**' ?
              html`<div class="message-caption">${message.text}</div>` : ''}
            ${message.media_url ?
              html`<img src="${message.media_url}" alt="Image" @click=${() => this._openImageModal(message.media_url, { alt: message.text || 'Image', caption: message.text || '', filename: message.media_url })}>` :
              html`<div style="color: red;">Image file is missing.</div>`
            }
          </div>
        `;

      case 'audio':
        return html`
          <div class="message-media">
            ${message.text && message.text !== '**Voice Message**' && message.text !== '**Audio**' ?
              html`<div class="message-caption">${message.text}</div>` : ''}
            ${message.media_url ?
              html`<audio controls src="${message.media_url}"></audio>` :
              html`<div style="color: red;">Audio file is missing.</div>`
            }
          </div>
        `;

      case 'tool_call':
        // Render as status line with loading or completion state
        const progress = message.progress_updates_for_user;
        const status = message._toolStatus || 'pending';
        const resultStatus = (message.result_status || message._toolResponse?.result_status || '').toUpperCase();

        const icon = status === 'pending'
          ? html`<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i>`
          : resultStatus === 'ERROR'
            ? html`<i class="fa-solid fa-circle-xmark" aria-hidden="true"></i>`
            : resultStatus === 'WARNING'
              ? html`<i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>`
              : html`<i class="fa-solid fa-circle-check" aria-hidden="true"></i>`;

        const shimmerClass = status === 'pending' ? 'shimmer' : '';
        const presentation = message._toolResponse?.tool_presentation;

        return html`
          <div class="tool-status ${status} ${shimmerClass}">
            <span class="tool-icon" aria-hidden="true">${icon}</span>
            ${progress ? html`<span class="tool-progress">${progress}</span>` : ''}
            ${status === 'pending' ? html`<span class="loading-dots">...</span>` : ''}
            ${presentation?.type === 'image' ? html`
              <figure class="tool-presentation-image">
                <img src=${presentation.url} alt=${presentation.alt || 'Tool image'} @click=${() => this._openImageModal(presentation.url, presentation)}>
                ${presentation.caption ? html`<figcaption>${presentation.caption}</figcaption>` : ''}
              </figure>
            ` : ''}
          </div>
        `;

      case 'tool_response':
        // This should not render separately anymore (handled by tool_call)
        return html``;

      default:
        return html`<div class="message-text">${message.text}</div>`;
    }
  }

  _handleEditMessage() {
    this.dispatchEvent(new CustomEvent('edit-message', {
      detail: { messageId: this.message.id },
      bubbles: true,
      composed: true,
    }));
  }

  _handleBranchNavigation(direction) {
    console.log('Branch navigation clicked:', direction, 'for message:', this.message.id);
    
    // Stop event from bubbling to prevent double handling
    const event = new CustomEvent('branch-navigation', {
      detail: { 
        groupId: this.message.branchInfo.groupId,
        direction: direction
      },
      bubbles: true,
      composed: true,
    });
    
    this.dispatchEvent(event);
    console.log('Branch navigation event dispatched');
  }

  render() {
    if (!this.message) return html``;

    const message = this.message;
    const isUserMessage = message.is_outgoing === false;
    const mediaType = message.media_type;
    
    // Handle tool calls as simple status lines (no bubble)
    if (mediaType === 'tool_call') {
      return html`
        <div class="message-item system">
          ${this._renderMessageContent(message)}
        </div>
        ${this._renderImageViewer()}
      `;
    }

    const alignment = isUserMessage ? 'outgoing' : 'incoming';
    const classes = ['message-item', alignment];
    const bubbleClasses = ['message-bubble'];

    if (message.is_outgoing === null) {
      classes.push('system');
    }

    if (['image', 'audio'].includes(mediaType)) {
      bubbleClasses.push('media');
    }
    if (mediaType === 'audio') {
      bubbleClasses.push('audio');
    }

    return html`
      <div class="${classes.join(' ')}">
        ${!isUserMessage && message.sender_name ? html`
          <div class="sender-name">${message.sender_name}</div>
        ` : ''}
        <div class="${bubbleClasses.join(' ')}">
          ${this._renderMessageContent(message)}
          <div class="message-footer">
            <div class="message-timestamp">${this._formatTimestamp(message.timestamp)}</div>
            <div class="message-actions">
              ${message.branchInfo ? html`
                <div class="branch-navigation">
                  <button 
                    class="branch-nav-btn" 
                    ?disabled=${!message.branchInfo.canGoPrev}
                    @click=${() => this._handleBranchNavigation('prev')}>
                    <i class="fa-solid fa-chevron-left" aria-hidden="true"></i>
                  </button>
                  <span class="branch-counter">
                    ${message.branchInfo.current} / ${message.branchInfo.total}
                  </span>
                  <button 
                    class="branch-nav-btn" 
                    ?disabled=${!message.branchInfo.canGoNext}
                    @click=${() => this._handleBranchNavigation('next')}>
                    <i class="fa-solid fa-chevron-right" aria-hidden="true"></i>
                  </button>
                </div>
              ` : ''}
              ${isUserMessage ? html`
                <button class="edit-btn" @click=${this._handleEditMessage} title="Edit message">
                  <i class="fa-solid fa-pen" aria-hidden="true"></i>
                </button>
              ` : ''}
            </div>
          </div>
        </div>
        ${this._renderInteractiveButtons(message.interactive_buttons)}
      </div>
      ${this._renderImageViewer()}
    `;
  }
}

customElements.define('message-item', MessageItem);
