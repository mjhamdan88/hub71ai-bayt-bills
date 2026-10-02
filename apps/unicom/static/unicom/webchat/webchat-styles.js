/**
 * Shared styles for WebChat components
 */
import { css } from 'lit';

export const iconStyles = css``;

export const baseStyles = css`
  :host {
    /* CSS custom properties for theming */
    --primary-color: var(--unicom-primary-color, #007bff);
    --secondary-color: var(--unicom-secondary-color, #6c757d);
    --background-color: var(--unicom-background-color, #ffffff);
    --message-bg-incoming: var(--unicom-message-bg-incoming, #f1f3f4);
    --message-bg-outgoing: var(--unicom-message-bg-outgoing, #007bff);
    --message-text-incoming: var(--unicom-message-text-incoming, #212529);
    --message-text-outgoing: var(--unicom-message-text-outgoing, #ffffff);
    --text-color: var(--unicom-text-color, #212529);
    --border-color: var(--unicom-border-color, #dee2e6);
    --border-radius: var(--unicom-border-radius, 0px);
    --bubble-radius: var(--unicom-bubble-radius, 16px);
    --control-radius: var(--unicom-control-radius, 12px);
    --media-radius: var(--unicom-media-radius, 12px);
    --scrollbar-track: var(--unicom-scrollbar-track, rgba(0, 0, 0, 0.04));
    --scrollbar-thumb: var(--unicom-scrollbar-thumb, rgba(0, 0, 0, 0.18));
    --sidebar-bg: var(--unicom-sidebar-bg, var(--background-color));
    --sidebar-border-color: var(--unicom-sidebar-border-color, var(--border-color));
    --sidebar-text-color: var(--unicom-sidebar-text-color, var(--text-color));
    --sidebar-secondary-text: var(--unicom-sidebar-secondary-text, var(--secondary-color));
    --sidebar-header-bg: var(--unicom-sidebar-header-bg, var(--primary-color));
    --sidebar-header-text: var(--unicom-sidebar-header-text, #ffffff);
    --sidebar-item-border: var(--unicom-sidebar-item-border, var(--border-color));
    --sidebar-item-hover: var(--unicom-sidebar-item-hover, rgba(0, 0, 0, 0.03));
    --sidebar-item-selected: var(--unicom-sidebar-item-selected, var(--primary-color));
    --sidebar-item-selected-text: var(--unicom-sidebar-item-selected-text, #ffffff);
    --sidebar-item-selected-subtext: var(--unicom-sidebar-item-selected-subtext, rgba(255, 255, 255, 0.8));
    --font-family: var(--unicom-font-family, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif);
    --input-height: var(--unicom-input-height, 44px);

    display: block;
    width: 100%;
    height: 100%;
    font-family: var(--font-family);
    box-sizing: border-box;
  }

  .unicom-chat-container {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    max-height: 100%;
    min-height: 0;
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
    background: var(--background-color);
    overflow: hidden;
    position: relative;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    box-sizing: border-box;
    padding-left: env(safe-area-inset-left, 0px);
    padding-right: env(safe-area-inset-right, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }

  @supports (height: 100dvh) {
    .unicom-chat-container {
      container-type: inline-size;
      height: 100%;
      max-height: 100%;
    }
  }

  .unicom-chat-container.dark {
    --background-color: var(--unicom-background-color, #1e1e1e);
    --text-color: var(--unicom-text-color, #ffffff);
    --border-color: var(--unicom-border-color, #444);
    --message-bg-incoming: var(--unicom-message-bg-incoming, #2d2d2d);
    --message-bg-outgoing: var(--unicom-message-bg-outgoing, #0056b3);
    --message-text-incoming: var(--unicom-message-text-incoming, #ffffff);
    --sidebar-bg: var(--unicom-sidebar-bg, #1b1b1b);
    --sidebar-border-color: var(--unicom-sidebar-border-color, #2d2d2d);
    --sidebar-text-color: var(--unicom-sidebar-text-color, #f3f3f3);
    --sidebar-secondary-text: var(--unicom-sidebar-secondary-text, #b0b0b0);
    --sidebar-header-bg: var(--unicom-sidebar-header-bg, #1f1f1f);
    --sidebar-header-text: var(--unicom-sidebar-header-text, #f3f3f3);
    --sidebar-item-border: var(--unicom-sidebar-item-border, rgba(255, 255, 255, 0.08));
    --sidebar-item-hover: rgba(255, 255, 255, 0.08);
    --sidebar-item-selected: var(--primary-color);
    --sidebar-item-selected-text: #ffffff;
    --sidebar-item-selected-subtext: rgba(255, 255, 255, 0.85);
    --scrollbar-track: rgba(255, 255, 255, 0.06);
    --scrollbar-thumb: rgba(255, 255, 255, 0.24);
  }

  .error-banner {
    background-color: #f8d7da;
    color: #721c24;
    padding: 12px;
    border-bottom: 1px solid #f5c6cb;
    text-align: center;
    font-size: 0.9em;
  }

  .dark .error-banner {
    background-color: #5a1a1a;
    color: #f8d7da;
    border-bottom-color: #721c24;
  }
`;

export const messageStyles = css`
  .message-item {
    padding: 8px 8px;
    display: flex;
    flex-direction: column;
    width: 100%;
    animation: fadeIn 0.3s ease-in;
    box-sizing: border-box;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .message-item.outgoing {
    align-items: flex-end;
  }

  .message-item.incoming {
    align-items: flex-start;
  }

  .sender-name {
    font-size: 0.8rem;
    color: var(--secondary-color);
    margin-bottom: 4px;
    font-weight: 500;
  }

  .message-bubble {
    display: inline-block;
    max-width: calc(100% - 32px);
    padding: 12px 16px;
    border-radius: var(--bubble-radius);
    word-wrap: break-word;
    word-break: break-word;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    box-sizing: border-box;
  }

  .message-item.outgoing .message-bubble {
    margin-left: auto;
    background: var(--primary-color);
    color: var(--message-text-outgoing);
    border-bottom-right-radius: clamp(4px, calc(var(--bubble-radius) / 2), var(--bubble-radius));
  }

  .message-item.incoming .message-bubble {
    background: var(--message-bg-incoming);
    color: var(--message-text-incoming);
    border-bottom-left-radius: clamp(4px, calc(var(--bubble-radius) / 2), var(--bubble-radius));
  }

  .message-bubble.media {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: min(100%, 460px);
    max-width: 100%;
  }

  .message-bubble.audio {
    width: min(100%, 520px);
  }

  .message-bubble.media .message-media {
    width: 100%;
  }

  .message-bubble.media .message-timestamp {
    align-self: flex-end;
  }

  .message-item.outgoing .message-bubble.media,
  .message-item.incoming .message-bubble.media {
    max-width: 100%;
  }

  .message-text {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .message-html {
    margin: 0;
  }

  .message-html * {
    max-width: 100%;
  }

  .message-html .diff-review-message {
    display: flex;
    flex-direction: column;
    gap: 12px;
    font-size: 0.95rem;
    color: rgba(255, 255, 255, 0.95);
  }

  .message-html .diff-review-message h3 {
    margin: 0;
    font-size: 1rem;
  }

  .message-html .diff-review-summary {
    margin: 0;
    font-weight: 500;
  }

  .message-html .diff-review-preview-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .message-html .diff-review-preview {
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    overflow: hidden;
    background: rgba(0, 0, 0, 0.25);
  }

  .dark .message-html .diff-review-preview {
    border-color: rgba(255, 255, 255, 0.18);
    background: rgba(255, 255, 255, 0.08);
  }

  .message-html .diff-review-preview summary {
    list-style: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 12px;
    cursor: pointer;
    background: rgba(0, 0, 0, 0.35);
    font-weight: 600;
    position: relative;
    color: rgba(255, 255, 255, 0.95);
  }

  .message-html .diff-review-preview summary::-webkit-details-marker {
    display: none;
  }

  .message-html .diff-review-preview summary::after {
    content: '▾';
    font-size: 0.9rem;
    color: rgba(255, 255, 255, 0.7);
    transition: transform 0.2s ease;
  }

  .message-html .diff-review-preview[open] summary::after {
    transform: rotate(-180deg);
  }

  .message-html .diff-review-preview[open] summary {
    border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  }

  .dark .message-html .diff-review-preview[open] summary {
    border-bottom-color: rgba(255, 255, 255, 0.1);
  }

  .message-html .diff-review-preview.diff-review-preview-added {
    border-color: rgba(46, 133, 64, 0.55);
    background: rgba(46, 133, 64, 0.15);
  }

  .message-html .diff-review-preview.diff-review-preview-added summary {
    background: rgba(46, 133, 64, 0.35);
  }

  .message-html .diff-review-preview.diff-review-preview-deleted {
    border-color: rgba(198, 40, 40, 0.55);
    background: rgba(198, 40, 40, 0.15);
  }

  .message-html .diff-review-preview.diff-review-preview-deleted summary {
    background: rgba(198, 40, 40, 0.35);
  }

  .message-html .diff-review-preview.diff-review-preview-modified {
    border-color: rgba(245, 124, 0, 0.6);
    background: rgba(245, 124, 0, 0.18);
  }

  .message-html .diff-review-preview.diff-review-preview-modified summary {
    background: rgba(245, 124, 0, 0.4);
  }

  .message-html .diff-review-file-header {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
  }

  .message-html .diff-review-badge {
    display: inline-flex;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    color: #fff;
    font-weight: 600;
  }

  .message-html .diff-review-badge-added {
    background: #2e8540;
  }

  .message-html .diff-review-badge-deleted {
    background: #c62828;
  }

  .message-html .diff-review-badge-modified {
    background: #f57c00;
  }

  .message-html .diff-review-file-name {
    font-family: Consolas, 'SFMono-Regular', Menlo, Monaco, monospace;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .message-html .diff-review-file-action {
    font-size: 0.85rem;
    color: rgba(255, 255, 255, 0.75);
  }

  .message-html .diff-review-file-action.error {
    color: #ff8a80;
  }

  .message-html .diff-review-file-body {
    padding: 0;
    margin: 0;
  }

  .message-html .diff-review-file-body[data-has-full="false"] .diff-review-file-toolbar {
    display: none;
  }

  .message-html .diff-review-file-body[data-view-mode="minimal"] .diff-view-full {
    display: none;
  }

  .message-html .diff-review-file-body[data-view-mode="full"] .diff-view-minimal {
    display: none;
  }

  .message-html .diff-review-file-toolbar {
    display: flex;
    justify-content: flex-end;
    padding: 6px 0 4px;
    gap: 8px;
  }

  .message-html .diff-review-toggle {
    border: 1px solid rgba(255, 255, 255, 0.3);
    background: transparent;
    color: rgba(255, 255, 255, 0.9);
    border-radius: 999px;
    padding: 4px 12px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.2s ease, color 0.2s ease, border-color 0.2s ease;
  }

  .message-html .diff-review-toggle:hover {
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(255, 255, 255, 0.5);
  }

  .message-html .diff-review-toggle:focus-visible {
    outline: 2px solid rgba(255, 255, 255, 0.8);
    outline-offset: 2px;
  }

  .message-html .diff-review-error {
    margin: 0;
    padding: 12px;
    color: #ff8a80;
    font-size: 0.9rem;
  }

  .message-html .diff-review-note {
    margin: 0;
    font-size: 0.85rem;
    color: rgba(255, 255, 255, 0.7);
  }

  .message-html .unified-diff-container {
    border-top: 1px solid rgba(0, 0, 0, 0.08);
    background: #0f111a;
    color: #f8f8f2;
    font-family: Consolas, 'JetBrains Mono', Menlo, Monaco, monospace;
  }

  .dark .message-html .unified-diff-container {
    border-top-color: rgba(255, 255, 255, 0.08);
  }

  .message-html .unified-diff-container .diff-stats {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    font-size: 0.85rem;
    background: rgba(255, 255, 255, 0.04);
  }

  .message-html .unified-diff-container .diff-stats-left {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .message-html .unified-diff-container .diff-stats .additions {
    color: #81c784;
    font-weight: 600;
  }

  .message-html .unified-diff-container .diff-stats .deletions {
    color: #ef9a9a;
    font-weight: 600;
  }

  .message-html .unified-diff-container .diff-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }

  .message-html .unified-diff-container .diff-line {
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }

  .message-html .unified-diff-container .diff-line:last-child {
    border-bottom: none;
  }

  .message-html .unified-diff-container .diff-line.diff-add {
    background: rgba(46, 133, 64, 0.35);
  }

  .message-html .unified-diff-container .diff-line.diff-delete {
    background: rgba(198, 40, 40, 0.35);
  }

  .message-html .unified-diff-container .line-num {
    width: 52px;
    min-width: 52px;
    padding: 0.3rem;
    background: rgba(255, 255, 255, 0.05);
    text-align: right;
    font-size: 0.78rem;
    color: rgba(255, 255, 255, 0.75);
    user-select: none;
    white-space: nowrap;
    overflow: hidden;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.02em;
  }

  .message-html .unified-diff-container .line-num.old-line-num {
    border-right: 1px solid rgba(255, 255, 255, 0.25);
  }

  .message-html .unified-diff-container .line-num.new-line-num {
    border-right: 1px solid rgba(255, 255, 255, 0.08);
  }

  .message-html .unified-diff-container .line-content {
    padding: 0.3rem 0.6rem;
    white-space: pre;
  }

  .message-html .unified-diff-container .diff-add .line-content {
    color: #c8e6c9;
  }

  .message-html .unified-diff-container .diff-delete .line-content {
    color: #ffcdd2;
  }

  .message-html .unified-diff-container .diff-content {
    overflow-x: auto;
  }

  .message-html .diff-review-file-body .diff-toggle-btn {
    display: none !important;
  }

  .message-html .unified-diff-container .hll { background-color: #49483e }
  .message-html .unified-diff-container .c { color: #959077 }
  .message-html .unified-diff-container .err { color: #ed007e; background-color: #1e0010 }
  .message-html .unified-diff-container .k { color: #66d9ef }
  .message-html .unified-diff-container .l { color: #ae81ff }
  .message-html .unified-diff-container .n { color: #f8f8f2 }
  .message-html .unified-diff-container .o { color: #ff4689 }
  .message-html .unified-diff-container .p { color: #f8f8f2 }
  .message-html .unified-diff-container .ch { color: #959077 }
  .message-html .unified-diff-container .cm { color: #959077 }
  .message-html .unified-diff-container .cp { color: #959077 }
  .message-html .unified-diff-container .cpf { color: #959077 }
  .message-html .unified-diff-container .c1 { color: #959077 }
  .message-html .unified-diff-container .cs { color: #959077 }
  .message-html .unified-diff-container .gd { color: #ff4689 }
  .message-html .unified-diff-container .ge { font-style: italic }
  .message-html .unified-diff-container .ges { font-weight: bold; font-style: italic }
  .message-html .unified-diff-container .gi { color: #a6e22e }
  .message-html .unified-diff-container .go { color: #66d9ef }
  .message-html .unified-diff-container .gp { color: #ff4689; font-weight: bold }
  .message-html .unified-diff-container .gs { font-weight: bold }
  .message-html .unified-diff-container .gu { color: #959077 }
  .message-html .unified-diff-container .gt { color: #f8f8f2 }
  .message-html .unified-diff-container .kc { color: #66d9ef }
  .message-html .unified-diff-container .kd { color: #66d9ef }
  .message-html .unified-diff-container .kn { color: #ff4689 }
  .message-html .unified-diff-container .kp { color: #66d9ef }
  .message-html .unified-diff-container .kr { color: #66d9ef }
  .message-html .unified-diff-container .kt { color: #66d9ef }
  .message-html .unified-diff-container .ld { color: #e6db74 }
  .message-html .unified-diff-container .m { color: #ae81ff }
  .message-html .unified-diff-container .s { color: #e6db74 }
  .message-html .unified-diff-container .na { color: #a6e22e }
  .message-html .unified-diff-container .nb { color: #f8f8f2 }
  .message-html .unified-diff-container .nc { color: #a6e22e }
  .message-html .unified-diff-container .no { color: #66d9ef }
  .message-html .unified-diff-container .nd { color: #a6e22e }
  .message-html .unified-diff-container .ni { color: #f8f8f2 }
  .message-html .unified-diff-container .ne { color: #a6e22e }
  .message-html .unified-diff-container .nf { color: #a6e22e }
  .message-html .unified-diff-container .nl { color: #f8f8f2 }
  .message-html .unified-diff-container .nn { color: #f8f8f2 }
  .message-html .unified-diff-container .nx { color: #a6e22e }
  .message-html .unified-diff-container .py { color: #f8f8f2 }
  .message-html .unified-diff-container .nt { color: #ff4689 }
  .message-html .unified-diff-container .nv { color: #f8f8f2 }
  .message-html .unified-diff-container .ow { color: #ff4689 }
  .message-html .unified-diff-container .w { color: #f8f8f2 }
  .message-html .unified-diff-container .mb { color: #ae81ff }
  .message-html .unified-diff-container .mf { color: #ae81ff }
  .message-html .unified-diff-container .mh { color: #ae81ff }
  .message-html .unified-diff-container .mi { color: #ae81ff }
  .message-html .unified-diff-container .mo { color: #ae81ff }
  .message-html .unified-diff-container .sa { color: #e6db74 }
  .message-html .unified-diff-container .sb { color: #e6db74 }
  .message-html .unified-diff-container .sc { color: #e6db74 }
  .message-html .unified-diff-container .dl { color: #e6db74 }
  .message-html .unified-diff-container .sd { color: #e6db74 }
  .message-html .unified-diff-container .s2 { color: #e6db74 }
  .message-html .unified-diff-container .se { color: #ae81ff }
  .message-html .unified-diff-container .sh { color: #e6db74 }
  .message-html .unified-diff-container .si { color: #e6db74 }
  .message-html .unified-diff-container .sx { color: #e6db74 }
  .message-html .unified-diff-container .sr { color: #e6db74 }
  .message-html .unified-diff-container .s1 { color: #e6db74 }
  .message-html .unified-diff-container .ss { color: #e6db74 }
  .message-html .unified-diff-container .bp { color: #f8f8f2 }
  .message-html .unified-diff-container .fm { color: #a6e22e }
  .message-html .unified-diff-container .vc { color: #f8f8f2 }
  .message-html .unified-diff-container .vg { color: #f8f8f2 }
  .message-html .unified-diff-container .vi { color: #f8f8f2 }
  .message-html .unified-diff-container .vm { color: #f8f8f2 }
  .message-html .unified-diff-container .il { color: #ae81ff }

  .message-timestamp {
    font-size: 0.7rem;
    opacity: 0.7;
    margin-top: 6px;
  }

  .message-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 6px;
    gap: 8px;
  }

  .message-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .branch-navigation {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 0.8rem;
  }

  .branch-nav-btn {
    background: none;
    border: 1px solid var(--unicom-border-color);
    color: var(--unicom-text-color);
    width: 20px;
    height: 20px;
    border-radius: 3px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.9rem;
    transition: background-color 0.2s;
  }

  .branch-nav-btn:hover:not(:disabled) {
    background-color: var(--unicom-primary-color);
    color: white;
  }

  .branch-nav-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  .branch-nav-btn i {
    color: currentColor;
  }

  .branch-counter {
    font-size: 0.75rem;
    opacity: 0.7;
    min-width: 30px;
    text-align: center;
  }

  .edit-btn {
    background: none;
    border: none;
    cursor: pointer;
    padding: 2px 4px;
    border-radius: 4px;
    font-size: 0.8rem;
    opacity: 0.6;
    transition: opacity 0.2s, background-color 0.2s;
    color: var(--unicom-text-color, inherit);
  }

  .edit-btn i {
    color: currentColor;
  }

  .edit-btn:hover {
    opacity: 1;
    background-color: rgba(0, 0, 0, 0.1);
  }

  .dark .edit-btn:hover {
    background-color: rgba(255, 255, 255, 0.1);
  }

  .message-media {
    margin: 0;
  }

  .message-caption {
    margin-bottom: 8px;
    font-size: 0.9em;
  }

  .message-media img {
    max-width: 100%;
    max-height: 400px;
    border-radius: var(--media-radius);
    cursor: pointer;
    display: block;
  }

  .message-media audio {
    width: 100%;
    max-width: 100%;
    display: block;
    margin-top: 4px;
    border-radius: var(--control-radius);
    background: rgba(0, 0, 0, 0.05);
  }

  .dark .message-media audio {
    background: rgba(255, 255, 255, 0.1);
  }

  .message-system {
    font-style: italic;
    opacity: 0.8;
    font-size: 0.9em;
  }

  .tool-status {
    font-size: 0.85em;
    opacity: 0.9;
    display: flex;
    align-items: center;
    gap: 0.5em;
    padding: 0.25em 0;
    color: var(--message-text-incoming, #212529);
    flex-wrap: wrap;
  }

  .tool-icon {
    font-size: 0.9em;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: currentColor;
  }

  .tool-icon i {
    color: currentColor;
  }

  .tool-progress {
    font-weight: 500;
    font-size: 0.9em;
  }

  .tool-presentation-image {
    flex-basis: 100%;
    margin: 0.5rem 0 0;
    max-width: 32rem;
  }

  .tool-presentation-image img {
    display: block;
    max-width: 100%;
    max-height: 24rem;
    border-radius: 0.65rem;
    cursor: pointer;
    object-fit: contain;
  }

  .tool-presentation-image figcaption {
    margin-top: 0.3rem;
    overflow-wrap: anywhere;
    font-size: 0.75rem;
    opacity: 0.75;
  }

  .image-viewer {
    position: fixed;
    z-index: 10000;
    inset: 0;
    display: grid;
    grid-template-rows: auto 1fr auto;
    color: var(--message-text-incoming, #212529);
    background: rgba(0, 0, 0, 0.9);
    backdrop-filter: blur(12px);
  }

  .image-viewer header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.8rem 1rem;
    background: var(--chat-bg, #fff);
  }

  .image-viewer header > div:first-child { display: grid; min-width: 0; }
  .image-viewer header small { overflow: hidden; opacity: 0.7; text-overflow: ellipsis; white-space: nowrap; }
  .image-viewer-actions { display: flex; align-items: center; gap: 0.35rem; }
  .image-viewer-actions button, .image-viewer-actions a { padding: 0.45rem 0.65rem; border: 1px solid currentColor; border-radius: 0.4rem; background: transparent; color: inherit; font: inherit; text-decoration: none; cursor: pointer; }
  .image-viewer-actions span { min-width: 3rem; text-align: center; }
  .image-viewer-canvas { display: grid; overflow: auto; padding: 2rem; place-items: center; }
  .image-viewer-canvas img { max-width: 100%; max-height: calc(100vh - 10rem); transform-origin: center; transition: transform 120ms ease; }
  .image-viewer footer { padding: 0.55rem 1rem; background: var(--chat-bg, #fff); font-size: 0.8rem; opacity: 0.8; }

  .shimmer {
    animation: shimmer-text 2.5s ease-in-out infinite;
    will-change: opacity;
  }

  .loading-dots {
    animation: loading-dots 1.5s infinite;
  }

  @keyframes loading-dots {
    0%, 20% { content: ''; }
    40% { content: '.'; }
    60% { content: '..'; }
    80%, 100% { content: '...'; }
  }

  @keyframes shimmer-text {
    0% { opacity: 0.5; }
    50% { opacity: 1; }
    100% { opacity: 0.5; }
  }

  @container (max-width: 768px) {
    .message-bubble {
      max-width: calc(100% - 24px);
    }
  }

  /* Interactive Buttons - Telegram-style positioning and theming */
  .interactive-buttons {
    margin-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    width: 100%;
    max-width: calc(100% - 32px);
  }

  .message-item.outgoing .interactive-buttons {
    align-self: flex-end;
    margin-left: auto;
  }

  .message-item.incoming .interactive-buttons {
    align-self: flex-start;
    margin-right: auto;
  }

  .button-row {
    display: flex;
    gap: 6px;
    width: 100%;
  }

  .interactive-btn {
    padding: 12px 16px;
    border: none;
    border-radius: var(--bubble-radius);
    cursor: pointer;
    font-size: inherit;
    font-weight: inherit;
    font-family: inherit;
    transition: all 0.15s ease;
    flex: 1;
    min-height: 44px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    word-wrap: break-word;
    word-break: break-word;
    box-sizing: border-box;
  }

  /* Use exact message bubble colors and styling */
  .message-item.outgoing .interactive-btn {
    background: var(--primary-color);
    color: var(--message-text-outgoing);
    border-bottom-right-radius: clamp(4px, calc(var(--bubble-radius) / 2), var(--bubble-radius));
  }

  .message-item.incoming .interactive-btn {
    background: var(--message-bg-incoming);
    color: var(--message-text-incoming);
    border-bottom-left-radius: clamp(4px, calc(var(--bubble-radius) / 2), var(--bubble-radius));
  }

  .interactive-btn:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
  }

  .interactive-btn:active:not(:disabled) {
    transform: translateY(0);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  }

  .interactive-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }

  /* Responsive button sizing */
  @container (max-width: 768px) {
    .interactive-buttons {
      max-width: calc(100% - 24px);
      align-self: center !important;
      margin-left: auto;
      margin-right: auto;
    }
  }

  /* Desktop: Match message bubble width */
  @container (min-width: 769px) {
    .interactive-buttons {
      max-width: min(calc(100% - 32px), 460px);
    }
  }
`;

export const inputStyles = css`
  :host {
    display: block;
    flex-shrink: 0;
  }

  .message-input-container {
    border-top: 1px solid var(--border-color);
    background: var(--background-color);
    padding: 12px;
    box-sizing: border-box;
  }

  .input-row {
    display: flex;
    align-items: flex-end;
    gap: 12px;
    position: relative;
  }

  .edit-mode-indicator {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background: rgba(255, 193, 7, 0.1);
    border-left: 3px solid #ffc107;
    font-size: 0.9em;
    color: #856404;
  }

  .dark .edit-mode-indicator {
    background: rgba(255, 193, 7, 0.2);
    color: #fff3cd;
  }

  .cancel-edit-btn {
    background: none;
    border: 1px solid #ffc107;
    color: #856404;
    padding: 4px 8px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8em;
    transition: background-color 0.2s;
  }

  .cancel-edit-btn:hover {
    background-color: rgba(255, 193, 7, 0.1);
  }

  .edit-mode-indicator i {
    margin-right: 6px;
    color: #856404;
  }

  .dark .edit-mode-indicator i {
    color: #fff3cd;
  }

  .dark .cancel-edit-btn {
    color: #fff3cd;
    border-color: #fff3cd;
  }

  .dark .cancel-edit-btn:hover {
    background-color: rgba(255, 193, 7, 0.2);
  }

  .input-row textarea {
    flex: 1;
    padding: 10px 12px;
    min-height: var(--input-height);
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
    font-family: inherit;
    font-size: 0.95em;
    resize: none;
    max-height: 160px;
    background: var(--background-color);
    color: var(--text-color);
    overflow-y: auto;
    line-height: 1.35;
    box-sizing: border-box;
  }

  .input-row textarea:focus {
    outline: none;
    border-color: var(--primary-color);
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
  }

  .icon-btn,
  .send-btn {
    flex-shrink: 0;
    height: var(--input-height);
    border-radius: var(--control-radius);
    border: 1px solid var(--border-color);
    background: var(--background-color);
    color: var(--text-color);
    font-size: 0.95em;
    font-weight: 500;
    padding: 0 16px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .icon-btn {
    width: var(--input-height);
    padding: 0;
    font-size: 1.2em;
    color: var(--text-color);
  }

  .icon-btn i {
    font-size: 1.1em;
    color: currentColor;
  }

  .send-btn {
    background: var(--primary-color);
    border-color: var(--primary-color);
    color: #fff;
    font-weight: 600;
    padding: 0 20px;
  }

  .icon-btn:hover:not(:disabled),
  .send-btn:hover:not(:disabled) {
    transform: translateY(-1px);
  }

  .icon-btn:disabled,
  .send-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .sending-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
    position: absolute;
    right: 0;
    bottom: -18px;
    font-size: 0.85em;
    color: var(--secondary-color);
  }

  .sending-indicator i {
    color: currentColor;
  }

  @keyframes pulse {
    0% { opacity: 0.6; transform: translateY(0); }
    50% { opacity: 1; transform: translateY(-1px); }
    100% { opacity: 0.6; transform: translateY(0); }
  }

  .dark textarea,
  .dark .icon-btn,
  .dark .send-btn {
    background: #2d2d2d;
    border-color: #444;
    color: #fff;
  }
`;

export const listStyles = css`
  :host {
    display: flex;
    flex-direction: column;
    flex: 1 1 auto;
    min-height: 0;
    width: 100%;
  }

  .message-list {
    flex: 1 1 auto;
    overflow-y: auto;
    overflow-x: hidden;
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-height: 0;
    -webkit-overflow-scrolling: touch;
    box-sizing: border-box;
    scrollbar-width: thin;
    scrollbar-color: var(--scrollbar-thumb) var(--scrollbar-track);
  }

  .message-list::-webkit-scrollbar {
    width: 8px;
  }

  .message-list::-webkit-scrollbar-track {
    background: var(--scrollbar-track);
  }

  .message-list::-webkit-scrollbar-thumb {
    background: var(--scrollbar-thumb);
    border-radius: 999px;
  }

  .loading-spinner {
    text-align: center;
    padding: 20px;
    color: var(--secondary-color);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .loading-spinner i {
    font-size: 1.2em;
    color: currentColor;
  }

  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }

  .load-more-btn {
    background: var(--message-bg-incoming);
    color: var(--text-color);
    border: 1px solid var(--border-color);
    border-radius: var(--control-radius);
    padding: 8px 16px;
    cursor: pointer;
    font-size: 0.9em;
    margin: 0 auto 16px;
    transition: background 0.2s ease;
  }

  .load-more-btn:hover {
    background: var(--border-color);
  }

  .empty-state {
    text-align: center;
    padding: 40px 20px;
    color: var(--secondary-color);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }

  .empty-state-icon {
    font-size: 3em;
    margin-bottom: 8px;
    opacity: 0.5;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .empty-state-icon i {
    line-height: 1;
    color: currentColor;
  }
`;

export const previewStyles = css`
  .media-preview {
    background: var(--message-bg-incoming);
    border: 1px solid var(--border-color);
    border-radius: var(--control-radius);
    padding: 8px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .media-preview.audio {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .preview-thumbnail {
    width: 60px;
    height: 60px;
    object-fit: cover;
    border-radius: var(--media-radius);
  }

  .preview-thumbnail.icon {
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5em;
    background: var(--border-color);
    color: var(--text-color);
  }

  .preview-thumbnail.icon i {
    font-size: 1.2em;
    color: currentColor;
  }

  .preview-audio-container {
    width: 100%;
  }

  .preview-audio {
    width: 100%;
    display: block;
    border-radius: var(--control-radius);
    background: rgba(0, 0, 0, 0.05);
  }

  .dark .preview-audio {
    background: rgba(255, 255, 255, 0.1);
  }

  .preview-info {
    flex: 1;
    font-size: 0.9em;
  }

  .preview-filename {
    font-weight: 500;
    margin-bottom: 4px;
    color: var(--text-color);
  }

  .preview-filesize {
    color: var(--secondary-color);
    font-size: 0.85em;
  }

  .preview-remove {
    background: transparent;
    border: none;
    color: var(--secondary-color);
    cursor: pointer;
    font-size: 1.1em;
    padding: 4px 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .preview-remove i {
    color: currentColor;
  }

  .media-preview.audio .preview-remove {
    align-self: flex-end;
  }

  .preview-remove:hover {
    color: #dc3545;
  }
`;
