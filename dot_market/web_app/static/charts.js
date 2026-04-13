/**
 * charts.js — DOT MARKET chart rendering layer using Plotly.js
 * All functions are pure: they receive data and a DOM element ID.
 */

console.log('[charts.js] Loaded ✓');

// ──────────────────────────────────────────────────────────────────────────────
// Theme helpers
// ──────────────────────────────────────────────────────────────────────────────
function isDarkMode() {
  return !document.body.classList.contains('light-mode');
}

function getTheme() {
  const dark = isDarkMode();
  return {
    paper_bgcolor: dark ? '#0a0a0f'  : '#f0f4ff',
    plot_bgcolor:  dark ? '#0d0d1a'  : '#f8faff',
    font_color:    dark ? '#8892b0'  : '#344563',
    grid_color:    dark ? 'rgba(30,30,58,0.8)' : 'rgba(200,210,235,0.8)',
    line_color:    dark ? '#1e1e3a'  : '#dde4f0',
    accent_blue:   '#00d4ff',
    accent_green:  '#00ff88',
    accent_red:    '#ff4757',
    accent_orange: '#ff9f43',
    accent_purple: '#a855f7',
  };
}

const BASE_LAYOUT_DEFAULTS = {
  margin:    { t: 20, r: 20, b: 40, l: 60 },
  showlegend: true,
  legend: { orientation: 'h', y: 1.05, x: 0, bgcolor: 'transparent', font: { size: 11 } },
  xaxis: { showgrid: true, zeroline: false, tickfont: { size: 11 } },
  yaxis: { showgrid: true, zeroline: false, tickfont: { size: 11 } },
  hovermode: 'x unified',
  hoverlabel: { bgcolor: '#13131f', bordercolor: '#1e1e3a', font: { family: 'JetBrains Mono', size: 12 } },
  dragmode: 'zoom',
  autosize: true,
};

function buildLayout(overrides = {}) {
  const t = getTheme();
  return Object.assign({}, BASE_LAYOUT_DEFAULTS, {
    paper_bgcolor: t.paper_bgcolor,
    plot_bgcolor:  t.plot_bgcolor,
    font:          { color: t.font_color, family: 'Inter, sans-serif' },
    xaxis: Object.assign({}, BASE_LAYOUT_DEFAULTS.xaxis, {
      gridcolor:  t.grid_color,
      linecolor:  t.line_color,
      tickcolor:  t.grid_color,
    }),
    yaxis: Object.assign({}, BASE_LAYOUT_DEFAULTS.yaxis, {
      gridcolor:  t.grid_color,
      linecolor:  t.line_color,
      tickcolor:  t.grid_color,
    }),
  }, overrides);
}

const PLOTLY_CONFIG = {
  responsive: true,
  displayModeBar: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['sendDataToCloud', 'lasso2d'],
  toImageButtonOptions: { format: 'png', filename: 'dotmarket_chart' },
};

// ──────────────────────────────────────────────────────────────────────────────
// 1. Candlestick chart (main chart)
// ──────────────────────────────────────────────────────────────────────────────
/**
 * renderCandlestick
 * @param {string}   elId        - DOM element ID
 * @param {object}   data        - API /predict response
 * @param {string[]} overlayFlags - which overlays to show: 'sma50','sma200','bb','pred'
 */
function renderCandlestick(elId, data, overlayFlags = ['sma50', 'sma200', 'bb', 'pred']) {
  console.log('[charts.js] renderCandlestick →', elId);
  const t     = getTheme();
  const dates = data.historical_dates;

  const traces = [];

  // Candlestick
  traces.push({
    type:       'candlestick',
    name:       data.ticker,
    x:          dates,
    open:       data.open,
    high:       data.high,
    low:        data.low,
    close:      data.historical_close,
    increasing: { line: { color: t.accent_green }, fillcolor: 'rgba(0,255,136,0.5)' },
    decreasing: { line: { color: t.accent_red },   fillcolor: 'rgba(255,71,87,0.5)' },
    showlegend: false,
  });

  // Bollinger Bands (shaded area)
  if (overlayFlags.includes('bb') && data.bb_upper) {
    traces.push({
      name:       'BB Upper',
      x:          dates,
      y:          data.bb_upper,
      mode:       'lines',
      line:       { color: 'rgba(168,85,247,0.4)', width: 1, dash: 'dot' },
      showlegend: true,
    });
    traces.push({
      name:       'BB Lower',
      x:          dates,
      y:          data.bb_lower,
      mode:       'lines',
      line:       { color: 'rgba(168,85,247,0.4)', width: 1, dash: 'dot' },
      fill:       'tonexty',
      fillcolor:  'rgba(168,85,247,0.05)',
      showlegend: false,
    });
  }

  // SMA50
  if (overlayFlags.includes('sma50') && data.sma50) {
    traces.push({
      name:  'SMA 50',
      x:     dates,
      y:     data.sma50,
      mode:  'lines',
      line:  { color: t.accent_orange, width: 1.5 },
    });
  }

  // SMA200
  if (overlayFlags.includes('sma200') && data.sma200) {
    traces.push({
      name:  'SMA 200',
      x:     dates,
      y:     data.sma200,
      mode:  'lines',
      line:  { color: t.accent_blue, width: 1.5 },
    });
  }

  // Predicted point (glowing star)
  if (overlayFlags.includes('pred') && data.predicted_dates) {
    const lastDate = data.predicted_dates[data.predicted_dates.length - 1];
    traces.push({
      name:   '📌 Predicted',
      x:      [lastDate],
      y:      [data.predicted_price],
      mode:   'markers',
      marker: {
        symbol: 'star',
        size:   18,
        color:  t.accent_green,
        line:   { color: '#fff', width: 1 },
      },
    });
    // Connect last actual to prediction
    const lastActualDate  = data.historical_dates[data.historical_dates.length - 1];
    const lastActualClose = data.historical_close[data.historical_close.length - 1];
    traces.push({
      name:      'Forecast',
      x:         [lastActualDate, lastDate],
      y:         [lastActualClose, data.predicted_price],
      mode:      'lines',
      line:      { color: t.accent_green, width: 2, dash: 'dash' },
      showlegend: false,
    });
  }

  const layout = buildLayout({
    title: { text: '', font: { size: 13 } },
    yaxis: {
      title:      { text: 'Price (USD)', font: { size: 11 } },
      gridcolor:  t.grid_color,
      tickprefix: '$',
    },
    xaxis: {
      rangeslider: { visible: false },
      gridcolor: t.grid_color,
    },
  });

  Plotly.react(elId, traces, layout, PLOTLY_CONFIG);
}

// ──────────────────────────────────────────────────────────────────────────────
// 2. RSI chart
// ──────────────────────────────────────────────────────────────────────────────
function renderRSI(elId, dates, rsiValues) {
  console.log('[charts.js] renderRSI →', elId);
  const t = getTheme();
  const n = dates.length;

  const traces = [
    {
      name:  'RSI (14)',
      x:     dates,
      y:     rsiValues,
      mode:  'lines',
      line:  { color: t.accent_purple, width: 2 },
      fill:  'tozeroy',
      fillcolor: 'rgba(168,85,247,0.08)',
    },
    {
      name:      'Overbought (70)',
      x:         [dates[0], dates[n - 1]],
      y:         [70, 70],
      mode:      'lines',
      line:      { color: t.accent_red, width: 1, dash: 'dot' },
      showlegend: true,
    },
    {
      name:      'Oversold (30)',
      x:         [dates[0], dates[n - 1]],
      y:         [30, 30],
      mode:      'lines',
      line:      { color: t.accent_green, width: 1, dash: 'dot' },
      showlegend: true,
    },
  ];

  const layout = buildLayout({
    yaxis: { range: [0, 100], gridcolor: t.grid_color, title: { text: 'RSI', font: { size: 11 } } },
    xaxis: { gridcolor: t.grid_color },
    margin: { t: 16, r: 16, b: 36, l: 48 },
  });

  Plotly.react(elId, traces, layout, PLOTLY_CONFIG);
}

// ──────────────────────────────────────────────────────────────────────────────
// 3. MACD chart
// ──────────────────────────────────────────────────────────────────────────────
function renderMACD(elId, dates, macdValues, signalValues) {
  console.log('[charts.js] renderMACD →', elId);
  const t = getTheme();

  const histogram = macdValues.map((v, i) => v - (signalValues[i] || 0));

  const traces = [
    {
      name:      'MACD',
      x:         dates,
      y:         macdValues,
      mode:      'lines',
      line:      { color: t.accent_blue, width: 2 },
    },
    {
      name:      'Signal',
      x:         dates,
      y:         signalValues,
      mode:      'lines',
      line:      { color: t.accent_orange, width: 1.5 },
    },
    {
      name:      'Histogram',
      x:         dates,
      y:         histogram,
      type:      'bar',
      marker:    {
        color: histogram.map(v => v >= 0 ? 'rgba(0,255,136,0.5)' : 'rgba(255,71,87,0.5)'),
      },
    },
  ];

  const layout = buildLayout({
    yaxis:  { gridcolor: t.grid_color, title: { text: 'MACD', font: { size: 11 } } },
    xaxis:  { gridcolor: t.grid_color },
    margin: { t: 16, r: 16, b: 36, l: 56 },
    barmode: 'overlay',
  });

  Plotly.react(elId, traces, layout, PLOTLY_CONFIG);
}

// ──────────────────────────────────────────────────────────────────────────────
// 4. Volume chart
// ──────────────────────────────────────────────────────────────────────────────
function renderVolume(elId, dates, volumeValues) {
  console.log('[charts.js] renderVolume →', elId);
  const t = getTheme();

  // 20-day simple moving average of volume
  const ma20 = volumeValues.map((_, i) => {
    const slice = volumeValues.slice(Math.max(0, i - 19), i + 1);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });

  const traces = [
    {
      name:    'Volume',
      x:       dates,
      y:       volumeValues,
      type:    'bar',
      marker:  { color: 'rgba(0,212,255,0.4)', line: { color: 'rgba(0,212,255,0.6)', width: 0.5 } },
    },
    {
      name:  'Vol MA20',
      x:     dates,
      y:     ma20,
      mode:  'lines',
      line:  { color: t.accent_orange, width: 2 },
    },
  ];

  const layout = buildLayout({
    yaxis: {
      gridcolor: t.grid_color,
      title:     { text: 'Volume', font: { size: 11 } },
      tickformat: '.2s',
    },
    xaxis:  { gridcolor: t.grid_color },
    margin: { t: 16, r: 16, b: 36, l: 60 },
    barmode: 'overlay',
  });

  Plotly.react(elId, traces, layout, PLOTLY_CONFIG);
}

// ──────────────────────────────────────────────────────────────────────────────
// 5. Compare chart (normalised to 100)
// ──────────────────────────────────────────────────────────────────────────────
/**
 * @param {string}   elId
 * @param {Array}    datasets  - [{ ticker, dates, prices }, ...]
 */
function renderCompare(elId, datasets) {
  console.log('[charts.js] renderCompare →', elId, datasets.map(d => d.ticker));
  const t      = getTheme();
  const colors = [t.accent_blue, t.accent_green, t.accent_orange, t.accent_purple, t.accent_red];

  const traces = datasets.map((ds, idx) => {
    const base    = ds.prices[0] || 1;
    const normalised = ds.prices.map(p => parseFloat(((p / base) * 100).toFixed(2)));
    return {
      name:  ds.ticker,
      x:     ds.dates,
      y:     normalised,
      mode:  'lines',
      line:  { color: colors[idx % colors.length], width: 2 },
    };
  });

  const layout = buildLayout({
    yaxis: {
      gridcolor:  t.grid_color,
      title:      { text: 'Normalised (base=100)', font: { size: 11 } },
      ticksuffix: '',
    },
    xaxis:  { gridcolor: t.grid_color },
    margin: { t: 20, r: 20, b: 40, l: 64 },
  });

  Plotly.react(elId, traces, layout, PLOTLY_CONFIG);
}

// ──────────────────────────────────────────────────────────────────────────────
// 6. Watchlist sparkline (tiny inline chart)
// ──────────────────────────────────────────────────────────────────────────────
function renderSparkline(elId, prices, changeUp) {
  const color = changeUp ? '#00ff88' : '#ff4757';
  Plotly.react(elId, [{
    y:    prices,
    mode: 'lines',
    line: { color, width: 1.5 },
    fill: 'tozeroy',
    fillcolor: changeUp ? 'rgba(0,255,136,0.1)' : 'rgba(255,71,87,0.1)',
  }], {
    paper_bgcolor: 'transparent',
    plot_bgcolor:  'transparent',
    margin:        { t: 0, r: 0, b: 0, l: 0 },
    xaxis:         { visible: false },
    yaxis:         { visible: false },
    showlegend:    false,
    hovermode:     false,
  }, { staticPlot: true, responsive: true, displayModeBar: false });
}

// ──────────────────────────────────────────────────────────────────────────────
// Time-range filter
// ──────────────────────────────────────────────────────────────────────────────
const RANGE_DAYS = { '1W': 7, '1M': 30, '3M': 90, '6M': 180, '1Y': 365 };

/**
 * Slice a data object to the last N days and re-render the main chart.
 * @param {string} range  - '1W' | '1M' | '3M' | '6M' | '1Y'
 * @param {object} data   - full /predict response
 */
function applyTimeRange(range, data) {
  console.log('[charts.js] applyTimeRange →', range);
  const days  = RANGE_DAYS[range] || 90;
  const sliced = sliceData(data, days);
  renderCandlestick('main-chart', sliced, getCurrentOverlays());
}

function sliceData(data, days) {
  const n = data.historical_dates.length;
  const s = Math.max(0, n - days);
  const sliced = Object.assign({}, data);
  const keys = ['historical_dates','historical_close','rsi','macd','macd_signal',
                 'bb_upper','bb_lower','sma50','sma200','volume','open','high','low'];
  keys.forEach(k => { if (Array.isArray(data[k])) sliced[k] = data[k].slice(s); });
  return sliced;
}

// Track which overlays are enabled
let _activeOverlays = ['sma50', 'sma200', 'bb', 'pred'];

function getCurrentOverlays()  { return [..._activeOverlays]; }
function setOverlay(key, on)   {
  if (on)  _activeOverlays = [...new Set([..._activeOverlays, key])];
  else     _activeOverlays = _activeOverlays.filter(o => o !== key);
}

// ──────────────────────────────────────────────────────────────────────────────
// Re-render everything when theme changes
// ──────────────────────────────────────────────────────────────────────────────
function refreshAllCharts(data) {
  if (!data) return;
  console.log('[charts.js] refreshAllCharts — theme:', isDarkMode() ? 'dark' : 'light');
  renderCandlestick('main-chart', data, getCurrentOverlays());
  renderRSI('rsi-chart', data.historical_dates, data.rsi);
  renderMACD('macd-chart', data.historical_dates, data.macd, data.macd_signal);
  renderVolume('volume-chart', data.historical_dates, data.volume);
}

// ──────────────────────────────────────────────────────────────────────────────
// Auto-resize on window resize (Plotly is already responsive but re-fire)
// ──────────────────────────────────────────────────────────────────────────────
window.addEventListener('resize', () => {
  ['main-chart', 'rsi-chart', 'macd-chart', 'volume-chart', 'compare-chart'].forEach(id => {
    const el = document.getElementById(id);
    if (el && el._fullLayout) Plotly.relayout(id, { autosize: true });
  });
});
