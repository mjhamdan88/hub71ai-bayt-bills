/**
 * Message List Component
 * Scrollable container for messages with pagination
 */
import { LitElement, html, css } from 'lit';
import { iconStyles, listStyles } from '../webchat-styles.js';
import fontAwesomeLoader from '../utils/font-awesome-loader.js';
import './message-item.js';

export class MessageList extends LitElement {
  static properties = {
    messages: { type: Array },
    loading: { type: Boolean },
    hasMore: { type: Boolean },
  };

  static styles = [iconStyles, listStyles];

  constructor() {
    super();
    this.messages = [];
    this.loading = false;
    this.hasMore = false;
    this._shouldScrollToBottom = true;
  }

  async firstUpdated() {
    await fontAwesomeLoader.applyToShadowRoot(this.shadowRoot);
  }

  _processMessages(messages) {
    // Merge tool_call and tool_response pairs into single status messages
    const processed = [];
    const toolCallMap = new Map();

    for (const msg of messages) {
      if (msg.media_type === 'tool_call') {
        // Store tool call and render as pending
        toolCallMap.set(msg.id, { ...msg, _toolStatus: 'pending' });
        processed.push(toolCallMap.get(msg.id));
      } else if (msg.media_type === 'tool_response' && msg.reply_to_message_id) {
        // Find matching tool call and update its status
        const toolCall = toolCallMap.get(msg.reply_to_message_id);
        if (toolCall) {
          toolCall._toolStatus = 'completed';
          toolCall._toolResponse = msg;
          // Don't add tool_response as separate message
        } else {
          processed.push(msg); // Fallback if no matching tool call
        }
      } else {
        processed.push(msg);
      }
    }

    return processed;
  }

  updated(changedProperties) {
    super.updated(changedProperties);

    if (changedProperties.has('messages')) {
      // Scroll to bottom when new messages arrive
      if (this._shouldScrollToBottom) {
        this._scrollToBottom();
      }
      this._shouldScrollToBottom = true;
    }
  }

  _scrollToBottom() {
    requestAnimationFrame(() => {
      const container = this.shadowRoot.querySelector('.message-list');
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    });
  }

  _handleEditMessage(e) {
    // Pass through edit message events to parent
    this.dispatchEvent(new CustomEvent('edit-message', {
      detail: e.detail,
      bubbles: true,
      composed: true,
    }));
  }

  _handleBranchNavigation(e) {
    console.log('Message list received branch navigation:', e.detail);
    this.dispatchEvent(new CustomEvent('branch-navigation', {
      detail: e.detail,
      bubbles: true,
      composed: true,
    }));
  }

  _handleScroll(e) {
    // Detect if user is at the top for "load more"
    // This is handled by the parent component
  }

  _loadMore() {
    this._shouldScrollToBottom = false;
    this.dispatchEvent(new CustomEvent('load-more', {
      bubbles: true,
      composed: true,
    }));
  }

  render() {
    const processedMessages = this._processMessages(this.messages);

    if (processedMessages.length === 0 && !this.loading) {
      return html`
        <div class="message-list">
          <div class="empty-state">
            <div class="empty-state-icon" aria-hidden="true">
              <i class="fa-solid fa-message"></i>
            </div>
            <div>No messages yet. Start the conversation!</div>
          </div>
        </div>
      `;
    }

    return html`
      <div class="message-list" @scroll=${this._handleScroll}>
        ${this.loading ? html`
          <div class="loading-spinner">
            <i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i>
            <span>Loading messages...</span>
          </div>
        ` : ''}

        ${this.hasMore && !this.loading ? html`
          <button @click=${this._loadMore} class="load-more-btn">
            Load earlier messages
          </button>
        ` : ''}

        ${processedMessages.map(msg => html`
          <message-item 
            .message=${msg} 
            @edit-message=${this._handleEditMessage}
            @branch-navigation=${this._handleBranchNavigation}>
          </message-item>
        `)}
      </div>
    `;
  }
}

customElements.define('message-list', MessageList);
