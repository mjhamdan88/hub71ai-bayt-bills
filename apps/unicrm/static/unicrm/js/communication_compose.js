(function (global) {
  'use strict';

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  function formatRelativeTime(dateString) {
    if (!dateString) {
      return 'Send Now';
    }
    const scheduledDate = new Date(dateString);
    if (isNaN(scheduledDate.getTime())) {
      return 'Send Now';
    }

    const now = new Date();
    if (scheduledDate < now) {
      return 'Send Now';
    }

    const scheduledDay = new Date(scheduledDate).setHours(0, 0, 0, 0);
    const today = new Date(now).setHours(0, 0, 0, 0);
    const diffDays = Math.floor((scheduledDay - today) / (1000 * 60 * 60 * 24));

    const timeStr = scheduledDate.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });

    if (diffDays === 0) {
      return `Send Today at ${timeStr}`;
    }
    if (diffDays === 1) {
      return `Send Tomorrow at ${timeStr}`;
    }
    if (diffDays > 1 && diffDays < 7) {
      const dayName = scheduledDate.toLocaleDateString('en-US', { weekday: 'long' });
      return `Send ${dayName} at ${timeStr}`;
    }
    const dateStr = scheduledDate.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
    return `Send on ${dateStr} at ${timeStr}`;
  }

  ready(function () {
    const form = document.getElementById('communication-compose-form');
    if (!form) {
      return;
    }

    const timezoneInput = document.getElementById('compose-timezone');
    const channelSelect = document.getElementById('id_channel');
    const subjectInput = document.getElementById('id_subject_template');
    const sendAtInput = document.getElementById('id_send_at');
    const submitButton = document.getElementById('compose-submit');
    const advancedSection = document.getElementById('advanced-options');

    if (timezoneInput && !timezoneInput.value && global.Intl && global.Intl.DateTimeFormat) {
      timezoneInput.value = global.Intl.DateTimeFormat().resolvedOptions().timeZone;
    }

    let editorInstance = null;

    function initEditor(channelId) {
      if (!global.UnicomTinyMCE || !global.UnicomTinyMCE.init) {
        return;
      }
      global.UnicomTinyMCE.init('#id_content', {
        channel_id: channelId || null,
        setup: function (editor) {
          editorInstance = editor;
        }
      });
    }

    function teardownEditor() {
      if (!global.tinymce || !editorInstance) {
        return;
      }
      editorInstance.remove();
      editorInstance = null;
    }

    function getCurrentChannelId() {
      return channelSelect && channelSelect.value ? channelSelect.value : null;
    }

    function updateButtonLabel() {
    if (!submitButton) {
      return;
    }
      const scheduleValue = sendAtInput ? sendAtInput.value : '';
      submitButton.textContent = formatRelativeTime(scheduleValue);
  }

  function ensureDeliveryMode() {
    updateButtonLabel();
    }

    if (sendAtInput) {
      ['change', 'input'].forEach(function (evt) {
        sendAtInput.addEventListener(evt, updateButtonLabel);
      });
    }

    function maybeToggleAdvancedOnErrors() {
      if (!advancedSection) {
        return;
      }
      const hasValue = sendAtInput && sendAtInput.value;
      const hasSubject = subjectInput && subjectInput.value;
      const errorsPresent = advancedSection.querySelector('.field-errors');
      if (hasValue || hasSubject || errorsPresent) {
        advancedSection.classList.add('active');
      }
    }

    function onChannelChange() {
      teardownEditor();
      initEditor(getCurrentChannelId());
    }

    if (channelSelect) {
      channelSelect.addEventListener('change', onChannelChange);
    }

    maybeToggleAdvancedOnErrors();
    initEditor(getCurrentChannelId());
    ensureDeliveryMode();
    updateButtonLabel();
  });
})(window);
