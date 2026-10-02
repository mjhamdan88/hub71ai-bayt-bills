/**
 * Chat List Component
 * Displays list of chats in a sidebar
 */
import { LitElement, html, css } from 'lit';
import { formatRelativeTime } from '../utils/datetime-formatter.js';
import { iconStyles } from '../webchat-styles.js';
import fontAwesomeLoader from '../utils/font-awesome-loader.js';

export class ChatList extends LitElement {
  static properties = {
    chats: { type: Array },
    selectedChatId: { type: String, attribute: 'selected-chat-id' },
    loading: { type: Boolean },
  };

  static styles = [iconStyles, css`
    :host {
      display: block;
      height: 100%;
      background: var(--sidebar-bg, var(--background-color, #ffffff));
      border-right: 1px solid var(--sidebar-border-color, var(--border-color, #dee2e6));
      color: var(--sidebar-text-color, var(--text-color, #212529));
    }

    .chat-list-container {
      display: flex;
      flex-direction: column;
      height: 100%;
    }

    .chat-list-header {
      padding: 16px;
      border-bottom: 1px solid var(--sidebar-border-color, var(--border-color, #dee2e6));
      background: var(--sidebar-header-bg, var(--primary-color, #007bff));
      color: var(--sidebar-header-text, #ffffff);
    }

    .chat-list-header h3 {
      margin: 0;
      font-size: 1.1em;
      font-weight: 600;
    }

    .new-chat-btn {
      margin-top: 12px;
      width: 100%;
      padding: 10px;
      background: white;
      color: var(--primary-color, #007bff);
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 500;
      transition: opacity 0.2s;
    }

    .new-chat-btn:hover {
      opacity: 0.9;
    }

    .chat-list-items {
      flex: 1;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: var(--scrollbar-thumb, rgba(0, 0, 0, 0.18)) var(--scrollbar-track, rgba(0, 0, 0, 0.04));
    }

    .chat-list-items::-webkit-scrollbar {
      width: 8px;
    }

    .chat-list-items::-webkit-scrollbar-track {
      background: var(--scrollbar-track, rgba(0, 0, 0, 0.04));
    }

    .chat-list-items::-webkit-scrollbar-thumb {
      background: var(--scrollbar-thumb, rgba(0, 0, 0, 0.18));
      border-radius: 999px;
    }

    .chat-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--sidebar-item-border, var(--border-color, #dee2e6));
      cursor: pointer;
      transition: background 0.2s;
      color: inherit;
    }

    .chat-item:hover {
      background: var(--sidebar-item-hover, rgba(0, 0, 0, 0.03));
    }

    .chat-item.selected {
      background: var(--sidebar-item-selected, var(--primary-color, #007bff));
      color: var(--sidebar-item-selected-text, #ffffff);
    }

    .chat-item.selected .chat-preview,
    .chat-item.selected .chat-time {
      color: var(--sidebar-item-selected-subtext, rgba(255, 255, 255, 0.8));
    }

    .chat-name {
      font-weight: 600;
      margin-bottom: 4px;
      font-size: 0.95em;
      color: inherit;
    }

    .chat-preview {
      font-size: 0.85em;
      color: var(--sidebar-secondary-text, var(--secondary-color, #6c757d));
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      margin-bottom: 4px;
    }

    .chat-time {
      font-size: 0.75em;
      color: var(--sidebar-secondary-text, var(--secondary-color, #6c757d));
    }

    .chat-content {
      flex: 1 1 auto;
      min-width: 0;
    }

    .chat-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      opacity: 0;
      transition: opacity 0.2s;
    }

    .chat-item:hover .chat-actions,
    .chat-item.selected .chat-actions {
      opacity: 1;
    }

    .delete-chat-btn {
      border: 1px solid var(--border-color, #dee2e6);
      background: transparent;
      color: inherit;
      cursor: pointer;
      font-size: 0.8em;
      padding: 6px 8px;
      border-radius: 4px;
      transition: background 0.2s, color 0.2s;
    }

    .delete-chat-btn:hover,
    .delete-chat-btn:focus {
      background: rgba(0, 0, 0, 0.08);
      color: var(--danger-color, #dc3545);
      outline: none;
    }

    .loading-spinner {
      padding: 20px;
      text-align: center;
      color: var(--secondary-color, #6c757d);
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }

    .empty-state {
      padding: 40px 20px;
      text-align: center;
      color: var(--sidebar-secondary-text, var(--secondary-color, #6c757d));
    }

    .empty-state-icon {
      font-size: 2em;
      margin-bottom: 12px;
      opacity: 0.5;
      display: flex;
      align-items: center;
      justify-content: center;
    }
  `];

  constructor() {
    super();
    this.chats = [];
    this.selectedChatId = null;
    this.loading = false;
  }

  async firstUpdated() {
    await fontAwesomeLoader.applyToShadowRoot(this.shadowRoot);
  }

  _handleChatClick(chat) {
    this.dispatchEvent(new CustomEvent('chat-selected', {
      detail: { chatId: chat.id },
      bubbles: true,
      composed: true,
    }));
  }

  _handleNewChat() {
    this.dispatchEvent(new CustomEvent('new-chat', {
      bubbles: true,
      composed: true,
    }));
  }

  _formatTime(timestamp) {
    if (!timestamp) return '';
    return formatRelativeTime(timestamp);
  }

  _handleDeleteClick(event, chat) {
    event.stopPropagation();

    const confirmationMessage = chat.name
      ? `Delete chat "${chat.name}"? This will remove the conversation permanently.`
      : 'Delete this chat? This will remove the conversation permanently.';

    if (!window.confirm(confirmationMessage)) {
      return;
    }

    this.dispatchEvent(new CustomEvent('delete-chat', {
      detail: { chatId: chat.id },
      bubbles: true,
      composed: true,
    }));
  }

  render() {
    return html`
      <div class="chat-list-container">
        <div class="chat-list-header">
          <h3>Chats</h3>
          <button class="new-chat-btn" @click=${this._handleNewChat}>
            + New Chat
          </button>
        </div>

        <div class="chat-list-items">
          ${this.loading ? html`
            <div class="loading-spinner">
              <i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i>
              <span>Loading chats...</span>
            </div>
          ` : ''}

          ${!this.loading && this.chats.length === 0 ? html`
            <div class="empty-state">
              <div class="empty-state-icon" aria-hidden="true">
                <i class="fa-solid fa-message"></i>
              </div>
              <div>No chats yet.<br>Click "New Chat" to start!</div>
            </div>
          ` : ''}

          ${this.chats.map(chat => html`
            <div
              class="chat-item ${chat.id === this.selectedChatId ? 'selected' : ''}"
              @click=${() => this._handleChatClick(chat)}>
              <div class="chat-content">
                <div class="chat-name">${chat.name || 'Chat ' + chat.id}</div>
                ${chat.last_message ? html`
                  <div class="chat-preview">${chat.last_message.text || 'Media message'}</div>
                  <div class="chat-time">${this._formatTime(chat.last_message.timestamp)}</div>
                ` : html`
                  <div class="chat-preview">No messages yet</div>
                `}
              </div>
              <div class="chat-actions">
                <button
                  class="delete-chat-btn"
                  @click=${(event) => this._handleDeleteClick(event, chat)}
                  aria-label="Delete chat">
                  Delete
                </button>
              </div>
            </div>
          `)}
        </div>
      </div>
    `;
  }
}

customElements.define('chat-list', ChatList);
