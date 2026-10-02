(function () {
  const CARD_SELECTOR = '.comm-status-card';

  function initCharts() {
    const charts = document.querySelectorAll(CARD_SELECTOR);
    if (!charts.length) {
      return;
    }

    charts.forEach((wrapper) => {
      try {
        renderChart(wrapper);
      } catch (err) {
        // Fallback: do nothing if chart rendering fails
        if (window.console && console.error) {
          console.error('Failed to render communication chart', err);
        }
      }
    });
  }

  function renderChart(wrapper) {
    const raw = wrapper.dataset.chart;
    if (!raw) {
      return;
    }

    let data;
    try {
      data = JSON.parse(raw);
    } catch (err) {
      return;
    }

    const pie = wrapper.querySelector('.comm-status-card__pie');
    const legend = wrapper.querySelector('.comm-status-card__legend');
    if (!pie || !legend || !Array.isArray(data)) {
      return;
    }

    legend.innerHTML = '';

    const total = data.reduce((sum, item) => sum + (item.count || 0), 0);
    if (total > 0) {
      pie.style.backgroundImage = buildGradient(data, total);
    } else {
      pie.style.backgroundImage = 'none';
      const message = document.createElement('div');
      message.className = 'comm-status-card__no-data';
      message.textContent = wrapper.dataset.emptyLabel || 'No deliveries yet';
      legend.appendChild(message);
    }

    data.forEach((item) => {
      legend.appendChild(createLegendEntry(item, total));
    });
  }

  function buildGradient(data, total) {
    let cumulative = 0;
    const segments = [];

    data.forEach((item) => {
      const count = item.count || 0;
      if (!count) {
        return;
      }
      const color = item.color || '#2563eb';
      const start = (cumulative / total) * 360;
      cumulative += count;
      const end = (cumulative / total) * 360;
      segments.push(`${color} ${start.toFixed(2)}deg ${end.toFixed(2)}deg`);
    });

    if (!segments.length) {
      return 'none';
    }

    return `conic-gradient(from -90deg, ${segments.join(', ')})`;
  }

  function createLegendEntry(item, total) {
    const li = document.createElement('li');
    const isLink = Boolean(item.url);
    const elementName = isLink ? 'a' : 'span';
    const entry = document.createElement(elementName);
    entry.className = 'comm-status-card__legend-entry';
    if (isLink) {
      entry.classList.add('is-link');
      entry.href = item.url;
    }

    const count = item.count || 0;
    if (count === 0) {
      entry.classList.add('is-zero');
    }

    const swatch = document.createElement('span');
    swatch.className = 'comm-status-card__swatch';
    swatch.style.backgroundColor = item.color || '#2563eb';
    entry.appendChild(swatch);

    const label = document.createElement('span');
    label.textContent = item.label || '';
    entry.appendChild(label);

    const value = document.createElement('span');
    value.className = 'comm-status-card__legend-value';
    value.textContent = `${count} (${formatPercentage(count, total)})`;
    entry.appendChild(value);

    if (isLink) {
      entry.setAttribute('aria-label', `${item.label}: ${value.textContent}`);
    }

    li.appendChild(entry);
    return li;
  }

  function formatPercentage(count, total) {
    if (!total) {
      return '0%';
    }
    const raw = (count / total) * 100;
    if (raw === 0) {
      return '0%';
    }
    if (raw >= 10) {
      return `${Math.round(raw)}%`;
    }
    return `${raw.toFixed(1)}%`;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCharts);
  } else {
    initCharts();
  }
})();
