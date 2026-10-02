/**
 * Message Input Component
 * Textarea, send button, and media upload
 */
import { LitElement, html } from 'lit';
import { iconStyles, inputStyles } from '../webchat-styles.js';
import fontAwesomeLoader from '../utils/font-awesome-loader.js';
import './media-preview.js';
import './voice-recorder.js';

export class MessageInput extends LitElement {
  static properties = {
    disabled: { type: Boolean },
    editingMessageId: { type: String, attribute: 'editing-message-id' },
    sending: { type: Boolean },
    sendAck: { type: Number },
    inputText: { type: String, state: true },
    previewFile: { type: Object, state: true },
    isRecording: { type: Boolean, state: true },
  };

  static styles = [iconStyles, inputStyles];

  constructor() {
    super();
    this.disabled = false;
    this.sending = false;
    this.sendAck = 0;
    this.editingMessageId = null;
    this.inputText = '';
    this.previewFile = null;
    this.isRecording = false;
  }

  async firstUpdated() {
    await fontAwesomeLoader.applyToShadowRoot(this.shadowRoot);
  }

  _handleInput(e) {
    this.inputText = e.target.value;
    // Auto-resize textarea
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
  }

  _handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      this._handleSend();
    }
  }

  _handleSend() {
    if (this.disabled || this.sending) return;

    const text = this.inputText.trim();
    if (!text && !this.previewFile) return;

    this.dispatchEvent(new CustomEvent('send-message', {
      detail: {
        text: text,
        file: this.previewFile,
        replyToMessageId: this.editingMessageId, // Include for editing/branching
      },
      bubbles: true,
      composed: true,
    }));
  }

  _handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    // Validate file type
    const validTypes = [
      'image/jpeg',
      'image/png',
      'image/gif',
      'image/webp',
      'audio/mpeg',
      'audio/ogg',
      'audio/wav',
      'audio/webm',
      'audio/mp4',
    ];
    if (!validTypes.includes(file.type)) {
      alert('Please select a valid image or audio file');
      return;
    }

    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      alert('File size must be less than 10MB');
      return;
    }

    this.previewFile = file;
    // Clear the input so the same file can be selected again
    e.target.value = '';
  }

  _handleRemoveFile() {
    this.previewFile = null;
  }

  _openFilePicker() {
    const fileInput = this.shadowRoot.getElementById('media-upload');
    if (fileInput && !this.disabled) {
      fileInput.click();
    }
  }

  _handleVoiceRecordingStarted() {
    this.isRecording = true;
  }

  _handleVoiceRecordingStopped() {
    this.isRecording = false;
  }

  _handleVoiceRecorded(e) {
    this.isRecording = false;
    if (this.disabled || this.sending) return;

    const file = e.detail?.file;
    if (!file) return;

    this.previewFile = file;
    this.requestUpdate();
  }

  _handleVoiceRecorderError() {
    this.isRecording = false;
  }

  updated(changed) {
    if (changed.has('sendAck') && changed.get('sendAck') !== this.sendAck) {
      this._clearInput();
    }
  }

  _clearInput() {
    this.inputText = '';
    this.previewFile = null;
    this.editingMessageId = null;
    const textarea = this.shadowRoot.querySelector('textarea');
    if (textarea) {
      textarea.style.height = 'auto';
    }
  }

  _handleCancelEdit() {
    this.editingMessageId = null;
    this.inputText = '';
    this.previewFile = null;
    
    // Reset textarea height
    const textarea = this.shadowRoot.querySelector('textarea');
    if (textarea) {
      textarea.style.height = 'auto';
    }
  }

  render() {
    const hasText = Boolean(this.inputText.trim());
    const hasAttachment = Boolean(this.previewFile);
    const showSend = !this.isRecording && (hasText || hasAttachment);
    const isEditing = Boolean(this.editingMessageId);
    const isDisabled = this.disabled || this.sending;

    return html`
      <div class="message-input-container">
        ${isEditing ? html`
          <div class="edit-mode-indicator">
            <span>
              <i class="fa-solid fa-pen" aria-hidden="true"></i>
              <span>Editing message</span>
            </span>
            <button class="cancel-edit-btn" @click=${this._handleCancelEdit}>Cancel</button>
          </div>
        ` : ''}

        ${this.previewFile ? html`
          <media-preview
            .file=${this.previewFile}
            @remove=${this._handleRemoveFile}>
          </media-preview>
        ` : ''}

        <input
          type="file"
          id="media-upload"
          accept="image/*,audio/*"
          @change=${this._handleFileSelect}
          style="display: none;">

        <div class="input-row">
          ${this.isRecording ? html`` : html`
            <textarea
              .value=${this.inputText}
              @input=${this._handleInput}
              @keydown=${this._handleKeyDown}
              placeholder=${isEditing ? "Edit your message..." : "Type a message..."}
              ?disabled=${isDisabled}
              rows="1"></textarea>
          `}

          <div class="actions">
            ${showSend ? html`
              <button
                class="send-btn"
                @click=${this._handleSend}
                ?disabled=${isDisabled || (!hasText && !hasAttachment)}>
                ${this.sending ? 'Sending…' : (isEditing ? 'Update' : 'Send')}
              </button>
            ` : html`
              <voice-recorder
                @voice-recording-started=${this._handleVoiceRecordingStarted}
                @voice-recording-stopped=${this._handleVoiceRecordingStopped}
                @voice-recorded=${this._handleVoiceRecorded}
                @voice-recorder-error=${this._handleVoiceRecorderError}
                ?disabled=${isDisabled}>
              </voice-recorder>
              <button
                class="icon-btn attach-btn"
                @click=${this._openFilePicker}
                ?disabled=${isDisabled}
                title="Attach media">
                <i class="fa-solid fa-paperclip" aria-hidden="true"></i>
              </button>
            `}
          </div>
          ${this.sending ? html`
            <div class="sending-indicator">
              <i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i>
              <span>Sending…</span>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }
}

customElements.define('message-input', MessageInput);
