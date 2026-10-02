/**
 * DateTime formatting utilities
 */

/**
 * Format timestamp for message display
 * @param {string} timestamp - ISO 8601 timestamp
 * @returns {string} Formatted time string
 */
export function formatTimestamp(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  // Same day - show time
  if (diffDays === 0) {
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  }

  // Yesterday
  if (diffDays === 1) {
    return 'Yesterday ' + date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  }

  // Within a week - show day name
  if (diffDays < 7) {
    return date.toLocaleDateString('en-US', { weekday: 'short' }) + ' ' +
           date.toLocaleTimeString('en-US', {
             hour: 'numeric',
             minute: '2-digit',
             hour12: true
           });
  }

  // Older - show date
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric'
  }) + ' ' + date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  });
}

/**
 * Format relative time (e.g., "2 minutes ago")
 * @param {string} timestamp - ISO 8601 timestamp
 * @returns {string} Relative time string
 */
export function formatRelativeTime(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffSecs < 60) return 'just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
  });
}
