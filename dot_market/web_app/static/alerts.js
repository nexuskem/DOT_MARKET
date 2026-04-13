/**
 * alerts.js — DOT MARKET Price Alert System
 *
 * - Register a target price for any ticker
 * - Polls /price/<ticker> every 30 seconds
 * - Fires a browser Notification when price crosses target
 * - Alerts stored in localStorage under "dm_alerts"
 */

console.log('[alerts.js] Loaded ✓');

const ALERTS_KEY    = 'dm_alerts';
const ALERTS_POLL_MS = 30_000;   // 30 seconds
const TRIGGERED_KEY  = 'dm_alerts_triggered'; // avoid repeat triggers

let _alertsTimer = null;

// ──────────────────────────────────────────────────────────────────────────────
// Storage helpers
// ──────────────────────────────────────────────────────────────────────────────
function alertsLoad() {
  try { return JSON.parse(localStorage.getItem(ALERTS_KEY) || '[]'); }
  catch { return []; }
}

function alertsSave(list) {
  localStorage.setItem(ALERTS_KEY, JSON.stringify(list));
}

function triggeredLoad() {
  try { return JSON.parse(localStorage.getItem(TRIGGERED_KEY) || '{}'); }
  catch { return {}; }
}

function triggeredSave(map) {
  localStorage.setItem(TRIGGERED_KEY, JSON.stringify(map));
}

// ──────────────────────────────────────────────────────────────────────────────
// CRUD
// ──────────────────────────────────────────────────────────────────────────────
function alertAdd(ticker, targetPrice, direction) {
  ticker      = ticker.trim().toUpperCase();
  targetPrice = parseFloat(targetPrice);
  if (!ticker || isNaN(targetPrice)) {
    showToast('Please enter a valid ticker and target price.', 'error');
    return;
  }

  const list = alertsLoad();
  const id   = `${ticker}_${Date.now()}`;
  list.push({ id, ticker, targetPrice, direction, createdAt: new Date().toISOString() });
  alertsSave(list);
  console.log('[alerts] Added alert:', { ticker, targetPrice, direction });
  renderAlerts();
  showToast(`Alert set: ${ticker} ${direction === 'above' ? '≥' : '≤'} $${targetPrice.toFixed(2)}`, 'success');
}

function alertRemove(id) {
  const list = alertsLoad().filter(a => a.id !== id);
  alertsSave(list);
  const trig = triggeredLoad();
  delete trig[id];
  triggeredSave(trig);
  console.log('[alerts] Removed alert:', id);
  renderAlerts();
}

// ──────────────────────────────────────────────────────────────────────────────
// Render alert list inside the modal
// ──────────────────────────────────────────────────────────────────────────────
function renderAlerts() {
  const container = document.getElementById('alerts-list');
  const list      = alertsLoad();

  if (!container) return;

  if (list.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted);font-size:13px;">No active alerts.</p>';
    return;
  }

  container.innerHTML = list.map(a => `
    <div class="alert-item" id="alert-item-${a.id}">
      <div class="alert-item-info">
        <span class="text-blue text-mono">${a.ticker}</span>
        <span style="color:var(--text-secondary);margin:0 6px;">${a.direction === 'above' ? '≥' : '≤'}</span>
        <span class="text-mono">$${a.targetPrice.toFixed(2)}</span>
      </div>
      <span style="font-size:11px;color:var(--text-muted);">${new Date(a.createdAt).toLocaleDateString()}</span>
      <button class="watchlist-remove" onclick="alertRemove('${a.id}')" title="Delete alert">✕</button>
    </div>`).join('');
}

// ──────────────────────────────────────────────────────────────────────────────
// Notification permission
// ──────────────────────────────────────────────────────────────────────────────
async function requestNotificationPermission() {
  if (!('Notification' in window)) {
    console.warn('[alerts] Browser does not support notifications.');
    return false;
  }
  if (Notification.permission === 'granted') return true;
  if (Notification.permission === 'denied')  return false;

  const perm = await Notification.requestPermission();
  console.log('[alerts] Notification permission:', perm);
  return perm === 'granted';
}

function fireNotification(ticker, targetPrice, currentPrice, direction) {
  if (Notification.permission !== 'granted') return;
  const n = new Notification(`🚨 DOT MARKET Alert — ${ticker}`, {
    body: `Price ${direction === 'above' ? 'crossed above' : 'dropped below'} $${targetPrice.toFixed(2)}.\nCurrent: $${currentPrice.toFixed(2)}`,
    icon: '/static/favicon.png',
    tag:  `dm-alert-${ticker}`,
  });
  n.onclick = () => window.focus();
  console.log('[alerts] Notification fired for', ticker);
}

// ──────────────────────────────────────────────────────────────────────────────
// Polling loop
// ──────────────────────────────────────────────────────────────────────────────
async function pollAlerts() {
  const list    = alertsLoad();
  if (list.length === 0) return;

  const trig    = triggeredLoad();
  // Unique tickers
  const tickers = [...new Set(list.map(a => a.ticker))];

  for (const ticker of tickers) {
    try {
      const res  = await fetch(`/price/${ticker}`);
      const data = await res.json();
      if (data.error || !data.price) continue;

      const currentPrice = data.price;

      list.filter(a => a.ticker === ticker).forEach(alert => {
        if (trig[alert.id]) return;   // already triggered

        const crossed =
          (alert.direction === 'above' && currentPrice >= alert.targetPrice) ||
          (alert.direction === 'below' && currentPrice <= alert.targetPrice);

        if (crossed) {
          console.log(`[alerts] 🚨 Triggered: ${ticker} @ $${currentPrice} (target: $${alert.targetPrice})`);
          fireNotification(ticker, alert.targetPrice, currentPrice, alert.direction);
          showToast(
            `🚨 ${ticker} hit $${currentPrice.toFixed(2)} — alert triggered!`,
            'warning',
            8000
          );
          trig[alert.id] = true;
          triggeredSave(trig);
          // Visually mark the alert item
          const el = document.getElementById(`alert-item-${alert.id}`);
          if (el) el.style.borderColor = 'var(--accent-orange)';
        }
      });
    } catch (err) {
      console.warn('[alerts] Poll error for', ticker, err.message);
    }
  }
}

function startAlertsPolling() {
  if (_alertsTimer) clearInterval(_alertsTimer);
  _alertsTimer = setInterval(() => {
    console.log('[alerts] Polling tick');
    pollAlerts();
  }, ALERTS_POLL_MS);
  console.log('[alerts] Polling started (every 30s)');
}

// ──────────────────────────────────────────────────────────────────────────────
// Modal open / close
// ──────────────────────────────────────────────────────────────────────────────
function openAlertsModal() {
  document.getElementById('alerts-modal-overlay').classList.add('open');
  renderAlerts();
  console.log('[alerts] Modal opened');
}

function closeAlertsModal() {
  document.getElementById('alerts-modal-overlay').classList.remove('open');
}

// ──────────────────────────────────────────────────────────────────────────────
// Form submit handler
// ──────────────────────────────────────────────────────────────────────────────
function handleAlertFormSubmit() {
  const tickerEl = document.getElementById('alert-ticker-input');
  const priceEl  = document.getElementById('alert-price-input');
  const dirEl    = document.getElementById('alert-direction-select');

  const ticker    = tickerEl ? tickerEl.value : '';
  const price     = priceEl  ? priceEl.value  : '';
  const direction = dirEl    ? dirEl.value    : 'above';

  alertAdd(ticker, price, direction);

  if (tickerEl) tickerEl.value = '';
  if (priceEl)  priceEl.value  = '';
}

// ──────────────────────────────────────────────────────────────────────────────
// Init
// ──────────────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await requestNotificationPermission();
  startAlertsPolling();
  renderAlerts();

  // Close modal on overlay click
  const overlay = document.getElementById('alerts-modal-overlay');
  if (overlay) {
    overlay.addEventListener('click', e => {
      if (e.target === overlay) closeAlertsModal();
    });
  }

  console.log('[alerts] Initialised. Active alerts:', alertsLoad().length);
});
