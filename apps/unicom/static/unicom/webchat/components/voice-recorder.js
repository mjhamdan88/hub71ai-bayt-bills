/**
 * Voice Recorder Component
 * Handles in-browser audio recording and emits audio files for sending.
 */
import { LitElement, html, css } from 'lit';
import { iconStyles } from '../webchat-styles.js';
import fontAwesomeLoader from '../utils/font-awesome-loader.js';

export class VoiceRecorder extends LitElement {
  static properties = {
    disabled: { type: Boolean, reflect: true },
    recording: { type: Boolean, state: true },
    recordingTime: { type: Number, state: true },
  };

  static styles = [iconStyles, css`
    :host {
      display: inline-flex;
      align-items: center;
    }

    button {
      border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
      background: var(--background-color, #fff);
      color: var(--text-color, #212529);
      border-radius: 12px;
      cursor: pointer;
      transition: all 0.2s ease;
      font: inherit;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }

    button:disabled {
      cursor: not-allowed;
      opacity: 0.5;
    }

    button:hover:not(:disabled) {
      transform: translateY(-1px);
    }

    .record-btn {
      width: var(--input-height, 44px);
      height: var(--input-height, 44px);
      font-size: 1.3em;
      color: var(--text-color, currentColor);
    }

    .recording-controls {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 12px;
      border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
      background: var(--message-bg-incoming, rgba(0, 0, 0, 0.04));
    }

    .recording-indicator {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.85em;
      color: var(--primary-color, #007bff);
    }

    .recording-indicator i {
      color: #ff4d4f;
      font-size: 0.8em;
    }

    .control-btn {
      padding: 6px 10px;
      border-radius: 10px;
      background: var(--background-color, #fff);
      font-size: 0.85em;
      border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));
    }

    .control-btn.stop {
      background: var(--primary-color, #007bff);
      border-color: var(--primary-color, #007bff);
      color: #fff;
      font-weight: 600;
    }
  `];

  constructor() {
    super();
    this.disabled = false;
    this.recording = false;
    this.recordingTime = 0;

    this.mediaRecorder = null;
    this.audioChunks = [];
    this.stream = null;
    this._timer = null;
    this._discardRecording = false;
  }

  async firstUpdated() {
    await fontAwesomeLoader.applyToShadowRoot(this.shadowRoot);
  }

  render() {
    if (this.recording) {
      return html`
        <div class="recording-controls" role="status" aria-live="polite">
          <span class="recording-indicator">
            <i class="fa-solid fa-circle" aria-hidden="true"></i>
            <span>${this._formatTime(this.recordingTime)}</span>
          </span>
          <button
            class="control-btn stop"
            @click=${this._stopRecording}
            ?disabled=${this.disabled}>
            Stop
          </button>
          <button
            class="control-btn"
            @click=${this._cancelRecording}
            ?disabled=${this.disabled}>
            Cancel
          </button>
        </div>
      `;
    }

    return html`
      <button
        class="record-btn"
        @click=${this._startRecording}
        ?disabled=${this.disabled}
        title="Record voice note">
        <i class="fa-solid fa-microphone" aria-hidden="true"></i>
      </button>
    `;
  }

  async _startRecording() {
    if (this.disabled || this.recording) return;

    if (typeof window.MediaRecorder === 'undefined') {
      this._notifyError('Voice recording is not available in this browser.');
      return;
    }

    const isSecure = window.isSecureContext ||
      /^localhost$|^127\.|^0\.0\.0\.0$|^\[::1\]$/.test(window.location.hostname);

    if (!isSecure) {
      this._notifyError('Voice recording requires HTTPS or localhost. Please open this page over a secure connection.');
      return;
    }

    const getUserMedia = this._getUserMedia();
    if (!getUserMedia) {
      this._notifyError('Microphone access APIs are unavailable. Please update your browser or use a different one.');
      return;
    }

    try {
      this.stream = await getUserMedia({ audio: true });
    } catch (err) {
      const message = err && err.name === 'NotAllowedError'
        ? 'Microphone access was denied. Please allow access and try again.'
        : 'Could not access the microphone on this device.';
      this._notifyError(message);
      return;
    }

    try {
      this.audioChunks = [];
      this._discardRecording = false;
      const options = this._buildRecorderOptions();
      this.mediaRecorder = Object.keys(options).length
        ? new MediaRecorder(this.stream, options)
        : new MediaRecorder(this.stream);
    } catch (err) {
      this._notifyError('Unable to start audio recorder on this device.');
      this._cleanupStream();
      return;
    }

    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        this.audioChunks.push(event.data);
      }
    };

    this.mediaRecorder.onstop = () => {
      this._cleanupStream();
      this.recording = false;
      this._stopTimer();
      this.dispatchEvent(new CustomEvent('voice-recording-stopped', {
        bubbles: true,
        composed: true,
      }));

      if (!this._discardRecording && this.audioChunks.length) {
        const blob = new Blob(this.audioChunks, { type: 'audio/webm' });
        const file = new File([blob], `voice-message-${Date.now()}.webm`, { type: 'audio/webm' });

        this.dispatchEvent(new CustomEvent('voice-recorded', {
          detail: { file },
          bubbles: true,
          composed: true,
        }));
      }

      this.audioChunks = [];
      this._discardRecording = false;
    };

    this.mediaRecorder.start();
    this.recording = true;
    this.recordingTime = 0;
    this.dispatchEvent(new CustomEvent('voice-recording-started', {
      bubbles: true,
      composed: true,
    }));
    this._startTimer();
  }

  _stopRecording() {
    if (!this.recording || !this.mediaRecorder) return;
    this._discardRecording = false;
    if (this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
  }

  _cancelRecording() {
    if (!this.recording || !this.mediaRecorder) return;
    this._discardRecording = true;
    if (this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this.recording) {
      this._discardRecording = true;
      if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
        this.mediaRecorder.stop();
      }
    }
    this._cleanupStream();
    this._stopTimer();
  }

  _cleanupStream() {
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
    this.mediaRecorder = null;
  }

  _getUserMedia() {
    if (navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === 'function') {
      return navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    }

    const legacyGetUserMedia =
      navigator.getUserMedia ||
      navigator.webkitGetUserMedia ||
      navigator.mozGetUserMedia ||
      navigator.msGetUserMedia;

    if (legacyGetUserMedia) {
      return (constraints) =>
        new Promise((resolve, reject) => legacyGetUserMedia.call(navigator, constraints, resolve, reject));
    }

    return null;
  }

  _buildRecorderOptions() {
    const options = {};
    if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
      return options;
    }

    const preferredTypes = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
    ];

    const supportedType = preferredTypes.find((type) => MediaRecorder.isTypeSupported(type));
    if (supportedType) {
      options.mimeType = supportedType;
    }

    return options;
  }

  _startTimer() {
    this._stopTimer();
    this._timer = setInterval(() => {
      this.recordingTime += 1;
      if (this.recordingTime >= 300) {
        this._stopRecording();
      }
    }, 1000);
  }

  _stopTimer() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
    this.recordingTime = 0;
  }

  _formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  _notifyError(message) {
    this.dispatchEvent(new CustomEvent('voice-recorder-error', {
      detail: { message },
      bubbles: true,
      composed: true,
    }));
    alert(message);
  }
}

customElements.define('voice-recorder', VoiceRecorder);
