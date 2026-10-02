/**
 * Lightweight real-time helper used by the WebChat components.
 * It prefers WebSockets but automatically falls back to HTTP polling
 * whenever Channels is not available or the connection cannot be established.
 * 
 * When WebSocket is explicitly enabled (websocketOnly mode), it will retry
 * with exponential backoff instead of falling back to polling.
 */

import { WebChatAPI } from './api-client.js';

export class RealTimeWebChatClient {
  constructor(baseURL = '/unicom/webchat', wsURL = null, options = {}) {
    this.baseURL = baseURL;
    this.wsBaseURL = wsURL || this._getWebSocketBaseURL();
    this.channelId = options.channelId ?? null;
    this.api = new WebChatAPI(baseURL, this.channelId);

    const normalizedOptions = options || {};
    const explicitlyEnable =
      normalizedOptions.enableWebsocket ?? normalizedOptions.enableWebSocket;
    const explicitlyDisable =
      normalizedOptions.disableWebsocket ||
      normalizedOptions.disableWebSocket ||
      normalizedOptions.forcePolling ||
      false;

    // Connection state
    this.ws = null;
    this.connected = false;
    if (explicitlyEnable === true) {
      this.useWebSocket = true;
      this.websocketOnly = true; // Force WebSocket only mode
    } else if (explicitlyEnable === false) {
      this.useWebSocket = false;
      this.websocketOnly = false;
    } else {
      this.useWebSocket = !explicitlyDisable; // Try WebSocket first unless disabled
      this.websocketOnly = false; // Allow fallback
    }
    this.pollingInterval = null;
    this.pollingRate = 5000; // 5 seconds default

    // Retry logic for WebSocket-only mode
    this.retryAttempt = 0;
    this.maxRetryInterval = 60000; // Cap at 1 minute
    this.retryTimeout = null;
    this.isRetrying = false;

    // Filters and subscriptions
    this.filters = {};
    this.currentChatId = null;

    // Event handlers
    this.onMessage = null;
    this.onMessageUpdated = null;
    this.onStream = null;
    this.onChatUpdate = null;
    this.onChatsUpdate = null;
    this.onConnectionChange = null;
    this.onError = null;
    this.onRetryStatusChange = null; // New handler for retry status

    // Message cache for polling
    this.lastMessageId = null;
  }

  /**
   * Enable or disable WebSocket usage dynamically.
   * Reconnects using the requested transport.
   */
  setWebSocketEnabled(enabled) {
    const shouldUseWebSocket = Boolean(enabled);
    if (this.useWebSocket === shouldUseWebSocket) {
      return;
    }

    const activeChat = this.currentChatId;
    this.disconnect();
    this.useWebSocket = shouldUseWebSocket;
    this.websocketOnly = shouldUseWebSocket; // Set WebSocket-only mode when explicitly enabled
    this.connect();
    if (activeChat) {
      this.subscribeToChat(activeChat);
    }
  }

  /**
   * Get base WebSocket URL from current location (no chat id appended yet).
   */
  _getWebSocketBaseURL() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}/ws/unicom/webchat/`;
  }

  _buildChatWebSocketURL(chatId) {
    const base = this.wsBaseURL.endsWith('/') ? this.wsBaseURL : `${this.wsBaseURL}/`;
    const query = this.channelId ? `?channel_id=${encodeURIComponent(this.channelId)}` : '';
    return `${base}${encodeURIComponent(chatId)}/${query}`;
  }

  /**
   * Prepare the transport. The socket itself is created when a chat is selected.
   */
  async connect() {
    if (this.useWebSocket) {
      this.connected = false;
      this._notifyConnectionChange(false, 'websocket');
    } else {
      this._startPolling();
    }
  }

  /**
   * Disconnect from real-time updates.
   */
  disconnect() {
    this._clearRetryTimeout();
    if (this.ws) {
      // Prevent reconnection attempts after manual disconnect.
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
    }
    this.connected = false;
    this.isRetrying = false;
    this.retryAttempt = 0;
    const transport = this.useWebSocket ? 'websocket' : 'polling';
    this._notifyConnectionChange(false, transport);
    this._notifyRetryStatus(false, 0);
  }

  /**
   * Set filters for chat list (e.g., project_id, department).
   * Currently filters are only applied to REST calls.
   */
  setFilters(filters) {
    this.filters = filters || {};
  }

  /**
   * Subscribe to a specific chat for real-time updates.
   */
  subscribeToChat(chatId) {
    this.currentChatId = chatId;
    this.lastMessageId = null;

    if (!chatId) {
      this._closeWebSocket();
      return;
    }

    if (this.useWebSocket) {
      this._connectChatWebSocket(chatId);
    } else {
      this._startPolling();
    }
  }

  /**
   * Unsubscribe from a chat.
   */
  unsubscribeFromChat(chatId) {
    if (this.currentChatId !== chatId) {
      return;
    }

    this.currentChatId = null;
    this.lastMessageId = null;

    if (this.useWebSocket) {
      this._closeWebSocket();
      this.connected = false;
      this._notifyConnectionChange(false, 'websocket');
    }
    this._clearRetryTimeout();
    this.retryAttempt = 0;
    this.isRetrying = false;
    this._notifyRetryStatus(false, 0);
  }

  /**
   * Send a message using the REST API.
   * Keeping message submission via HTTP keeps the websocket consumer simple.
   */
  async sendMessage(text, chatId = null, mediaFile = null, options = {}) {
    return await this.api.sendMessage(text, chatId, mediaFile, { ...options, channelId: options.channelId ?? this.channelId });
  }

  /**
   * Get list of chats (REST).
   */
  async getChats(filters = null) {
    const response = await this.api.getChats(filters || this.filters);
    return response.chats;
  }

  /**
   * Get messages for a chat (REST).
   */
  async getMessages(chatId, limit = 50, branch = 'latest') {
    const response = await this.api.getMessages(chatId, limit, null, null, branch);
    return response.messages;
  }

  /**
   * Update the polling cursor using the most recent message list.
   * Call this after loading messages via HTTP so polling starts from the end.
   */
  updateBaselineFromMessages(messages = []) {
    if (Array.isArray(messages) && messages.length > 0) {
      this.lastMessageId = messages[messages.length - 1].id;
    } else {
      this.lastMessageId = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Private helpers

  _connectChatWebSocket(chatId) {
    this._closeWebSocket();

    const url = this._buildChatWebSocketURL(chatId);
    try {
      this.ws = new WebSocket(url);
    } catch (err) {
      console.warn('Failed to create WebSocket:', err);
      if (this.websocketOnly) {
        this._scheduleWebSocketRetry(chatId);
      } else {
        this._fallbackToPolling();
      }
      return;
    }

    const socket = this.ws;

    socket.onopen = () => {
      // Connection established, waiting for server readiness message.
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this._handleWebSocketMessage(data);
      } catch (err) {
        console.error('Invalid WebSocket payload:', err);
      }
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
      this._notifyError(error);
    };

    socket.onclose = (event) => {
      const shouldAttemptReconnect =
        this.useWebSocket && this.currentChatId === chatId && !event.wasClean && event.code !== 4000;

      const wasConnected = this.connected;
      this.connected = false;
      if (wasConnected) {
        this._notifyConnectionChange(false, 'websocket');
      }

      if (!wasConnected) {
        // Handshake failed or access denied
        if (this.websocketOnly) {
          this._scheduleWebSocketRetry(chatId);
        } else {
          this._fallbackToPolling();
        }
        return;
      }

      if (shouldAttemptReconnect) {
        if (this.websocketOnly) {
          this._scheduleWebSocketRetry(chatId);
        } else {
          setTimeout(() => {
            if (this.useWebSocket && this.currentChatId === chatId) {
              this._connectChatWebSocket(chatId);
            }
          }, this.pollingRate);
        }
      }
    };
  }

  _handleWebSocketMessage(data) {
    switch (data.type) {
      case 'ready':
        this.connected = true;
        this.retryAttempt = 0; // Reset retry counter on successful connection
        this.isRetrying = false;
        this._notifyConnectionChange(true, 'websocket');
        this._notifyRetryStatus(false, 0);
        break;

      case 'new_message':
        if (data.message) {
          this.lastMessageId = data.message.id;
        }
        if (this.onMessage) {
          this.onMessage(data.message, data.chat_id);
        }
        break;

      case 'message_updated':
        if (this.onMessageUpdated && data.message) {
          this.onMessageUpdated(data.message, data.chat_id);
        } else if (this.onMessage && data.message) {
          this.onMessage(data.message, data.chat_id);
        }
        break;

      case 'llm_stream':
        if (this.onStream && data.event) {
          this.onStream(data.event, data.chat_id, data.request_id);
        }
        break;

      case 'chat_update':
        if (this.onChatUpdate) {
          this.onChatUpdate(data.chat);
        }
        break;

      case 'chats_list':
        if (this.onChatsUpdate) {
          this.onChatsUpdate(data.chats);
        }
        break;

      case 'pong':
        // heartbeat response, nothing else to do
        break;

      default:
        console.log('WebSocket message:', data);
    }
  }

  _closeWebSocket() {
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }

  _fallbackToPolling() {
    if (this.websocketOnly) {
      // In WebSocket-only mode, don't fall back to polling
      console.warn('WebSocket connection failed in WebSocket-only mode. Will retry...');
      return;
    }
    
    if (this.useWebSocket) {
      console.warn('Falling back to HTTP polling for WebChat updates.');
    }
    this.useWebSocket = false;
    this._startPolling();
  }

  _scheduleWebSocketRetry(chatId) {
    this._clearRetryTimeout();
    
    // Calculate retry delay with exponential backoff
    const baseDelay = 1000; // Start with 1 second
    const delay = Math.min(baseDelay * Math.pow(2, this.retryAttempt), this.maxRetryInterval);
    
    this.retryAttempt++;
    this.isRetrying = true;
    this._notifyRetryStatus(true, delay);
    
    console.log(`WebSocket retry attempt ${this.retryAttempt} in ${delay}ms`);
    
    this.retryTimeout = setTimeout(() => {
      if (this.useWebSocket && this.currentChatId === chatId) {
        this._connectChatWebSocket(chatId);
      }
    }, delay);
  }

  _clearRetryTimeout() {
    if (this.retryTimeout) {
      clearTimeout(this.retryTimeout);
      this.retryTimeout = null;
    }
  }

  _startPolling() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
    }

    this.connected = true;
    this._notifyConnectionChange(true, 'polling');

    this.pollingInterval = setInterval(async () => {
      try {
        if (!this.currentChatId) {
          return;
        }

        const response = await this.api.getMessages(
          this.currentChatId,
          50,
          null,
          this.lastMessageId
        );

        if (response.messages && response.messages.length > 0) {
          this.lastMessageId = response.messages[response.messages.length - 1].id;
          response.messages.forEach((msg) => {
            if (this.onMessage) {
              this.onMessage(msg, this.currentChatId);
            }
          });
        }
      } catch (err) {
        console.error('Polling error:', err);
        this._notifyError(err);
      }
    }, this.pollingRate);
  }

  _notifyConnectionChange(connected, transport) {
    if (this.onConnectionChange) {
      const type = transport || (this.useWebSocket ? 'websocket' : 'polling');
      this.onConnectionChange(connected, type);
    }
  }

  _notifyError(error) {
    if (this.onError) {
      this.onError(error);
    }
  }

  _notifyRetryStatus(isRetrying, nextRetryIn) {
    if (this.onRetryStatusChange) {
      this.onRetryStatusChange(isRetrying, nextRetryIn);
    }
  }

  setPollingRate(ms) {
    this.pollingRate = ms;
    if (this.pollingInterval && !this.useWebSocket) {
      clearInterval(this.pollingInterval);
      this._startPolling();
    }
  }

  isUsingWebSocket() {
    return this.connected && this.useWebSocket;
  }

  isConnected() {
    return this.connected;
  }

  isRetryingWebSocket() {
    return this.isRetrying;
  }

  getRetryAttempt() {
    return this.retryAttempt;
  }
}
