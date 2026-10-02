/**
 * Media Preview Component
 * Shows preview of selected file before sending
 */
import { LitElement, html, css } from 'lit';
import { iconStyles, previewStyles } from '../webchat-styles.js';
import fontAwesomeLoader from '../utils/font-awesome-loader.js';

export class MediaPreview extends LitElement {
  static properties = {
    file: { type: Object },
  };

  static styles = [iconStyles, previewStyles];

  constructor() {
    super();
    this.file = null;
    this._objectUrl = null;
  }

  async firstUpdated() {
    await fontAwesomeLoader.applyToShadowRoot(this.shadowRoot);
  }

  updated(changedProps) {
    if (changedProps.has('file')) {
      if (this._objectUrl) {
        URL.revokeObjectURL(this._objectUrl);
        this._objectUrl = null;
      }
      if (this.file) {
        this._objectUrl = URL.createObjectURL(this.file);
      }
    }
  }

  _formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  _handleRemove() {
    this.dispatchEvent(new CustomEvent('remove', {
      bubbles: true,
      composed: true,
    }));
  }

  render() {
    if (!this.file) return html``;

    const type = this.file.type || '';
    const isImage = type.startsWith('image/');
    const isAudio = type.startsWith('audio/');
    const previewUrl = this._objectUrl;

    return html`
      <div class="media-preview ${isAudio ? 'audio' : ''}">
        ${isImage && previewUrl ? html`
          <img class="preview-thumbnail" src="${previewUrl}" alt="Preview">
        ` : isAudio && previewUrl ? html`
          <div class="preview-audio-container">
            <audio class="preview-audio" controls src="${previewUrl}"></audio>
          </div>
        ` : html`
          <div class="preview-thumbnail icon">
            <i class="fa-solid ${isAudio ? 'fa-music' : 'fa-paperclip'}" aria-hidden="true"></i>
          </div>
        `}
        <div class="preview-info">
          <div class="preview-filename">${this.file.name}</div>
          <div class="preview-filesize">${this._formatFileSize(this.file.size)}</div>
        </div>
        <button class="preview-remove" @click=${this._handleRemove} title="Remove file">
          <i class="fa-solid fa-xmark" aria-hidden="true"></i>
        </button>
      </div>
    `;
  }

  disconnectedCallback() {
    if (this._objectUrl) {
      URL.revokeObjectURL(this._objectUrl);
      this._objectUrl = null;
    }
    super.disconnectedCallback();
  }
}

customElements.define('media-preview', MediaPreview);
