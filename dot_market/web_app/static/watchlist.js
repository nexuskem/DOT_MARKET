/**
 * watchlist.js — DOT MARKET Watchlist management
 *
 * - Persists tickers in localStorage under key "dm_watchlist"
 * - Renders mini sparklines via Plotly (renderSparkline from charts.js)
 * - Auto-refreshes prices every 60 seconds
 * - Updates the navbar badge count
 */

console.log('[watchlist.js] Loaded ✓');

const WL_KEY        = 'dm_watchlist';         // localStorage key
const WL_REFRESH_MS = 60_000;                  // 60 seconds

let _watchlistRefreshTimer = null;

// ──────────────────────────────────────────────────────────────────────────────
// Storage helpers
// ──────────────────────────────────────────────────────────────────────────────
function wlLoad() {
  try {
    const raw = localStorage.getItem(WL_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    console.warn('[watchlist] Failed to parse localStorage:', e);
    return [];
  }
}

function wlSave(tickers) {
  localStorage.setItem(WL_KEY, JSON.stringify(tickers));
  console.log('[watchlist] Saved:', tickers);
}

function wlAdd(ticker) {
  ticker = ticker.trim().toUpperCase();
  if (!ticker) return;
  const list = wlLoad();
  if (!list.includes(ticker)) {
    list.push(ticker);
    wlSave(list);
    console.log('[watchlist] Added:', ticker);
  }
  renderWatchlist();
  updateWatchlistBadge();
}

function wlRemove(ticker) {
  ticker = ticker.trim().toUpperCase();
  const list = wlLoad().filter(t => t !== ticker);
  wlSave(list);
  console.log('[watchlist] Removed:', ticker);
  renderWatchlist();
  updateWatchlistBadge();
}

function wlHas(ticker) {
  return wlLoad().includes(ticker.trim().toUpperCase());
}

// ──────────────────────────────────────────────────────────────────────────────
// Badge
// ──────────────────────────────────────────────────────────────────────────────
function updateWatchlistBadge() {
  const badge = document.getElementById('wl-badge');
  if (badge) badge.textContent = wlLoad().length;
}

// ──────────────────────────────────────────────────────────────────────────────
// Sidebar open / close
// ──────────────────────────────────────────────────────────────────────────────
function openWatchlistSidebar() {
  document.getElementById('watchlist-overlay').classList.add('open');
  document.getElementById('watchlist-sidebar').classList.add('open');
  renderWatchlist();
  console.log('[watchlist] Sidebar opened');
}

function closeWatchlistSidebar() {
  document.getElementById('watchlist-overlay').classList.remove('open');
  document.getElementById('watchlist-sidebar').classList.remove('open');
  console.log('[watchlist] Sidebar closed');
}

// ──────────────────────────────────────────────────────────────────────────────
// Render
// ──────────────────────────────────────────────────────────────────────────────
async function renderWatchlist() {
  const container = document.getElementById('wl-items');
  const tickers   = wlLoad();

  if (!container) return;

  if (tickers.length === 0) {
    container.innerHTML = `
      <div class="watchlist-empty">
        <div class="empty-icon">📋</div>
        <p>Your watchlist is empty.</p>
        <p style="margin-top:8px;font-size:12px;">Click ♡ on any prediction to add a stock.</p>
      </div>`;
    return;
  }

  // Render skeleton placeholders immediately
  container.innerHTML = tickers.map(t => `
    <div class="watchlist-item" id="wl-item-${t}" onclick="handleWatchlistItemClick('${t}')">
      <div class="watchlist-item-info">
        <div class="watchlist-item-ticker">${t}</div>
        <div class="watchlist-item-price skeleton" style="width:80px;height:14px;border-radius:4px;"></div>
        <div class="watchlist-item-chg text-muted" style="margin-top:4px;">Loading…</div>
      </div>
      <div class="watchlist-sparkline" id="spark-${t}"></div>
      <button class="watchlist-remove" onclick="event.stopPropagation();wlRemove('${t}')" title="Remove">✕</button>
    </div>`).join('');

  // Fetch prices for each ticker
  for (const ticker of tickers) {
    fetchWatchlistItem(ticker);
  }
}

async function fetchWatchlistItem(ticker) {
  try {
    console.log('[watchlist] Fetching price for', ticker);
    const res  = await fetch(`/price/${ticker}`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    const itemEl = document.getElementById(`wl-item-${ticker}`);
    if (!itemEl) return;

    const priceEl = itemEl.querySelector('.watchlist-item-price');
    const chgEl   = itemEl.querySelector('.watchlist-item-chg');

    if (priceEl) {
      priceEl.classList.remove('skeleton');
      priceEl.style.cssText = '';
      priceEl.textContent   = `$${data.price.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
    }

    if (chgEl) {
      const up = data.change_pct >= 0;
      chgEl.textContent  = `${up ? '▲' : '▼'} ${Math.abs(data.change_pct).toFixed(2)}%`;
      chgEl.className    = `watchlist-item-chg ${up ? 'up' : 'down'}`;
    }

    // Mini sparkline — try to get last 30 days from cached prediction data
    const sparkEl = document.getElementById(`spark-${ticker}`);
    if (sparkEl && window._lastPredictions && window._lastPredictions[ticker]) {
      const pd = window._lastPredictions[ticker];
      renderSparkline(`spark-${ticker}`, pd.historical_close.slice(-30), data.change_pct >= 0);
    }
  } catch (err) {
    console.warn(`[watchlist] Failed to fetch ${ticker}:`, err.message);
  }
}

// Store last prediction data per ticker for sparklines
window._lastPredictions = window._lastPredictions || {};

function cacheForSparkline(ticker, data) {
  window._lastPredictions[ticker] = data;
}

// ──────────────────────────────────────────────────────────────────────────────
// Click a watchlist item → run prediction
// ──────────────────────────────────────────────────────────────────────────────
function handleWatchlistItemClick(ticker) {
  console.log('[watchlist] Item clicked:', ticker);
  closeWatchlistSidebar();
  // Trigger main prediction flow
  if (typeof runPrediction === 'function') {
    runPrediction(ticker);
  } else {
    document.getElementById('ticker-input').value = ticker;
    document.getElementById('predict-btn').click();
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Heart button toggle
// ──────────────────────────────────────────────────────────────────────────────
function toggleWatchlistHeart(ticker) {
  const btn = document.getElementById('wl-heart-btn');
  if (wlHas(ticker)) {
    wlRemove(ticker);
    if (btn) { btn.textContent = '♡'; btn.classList.remove('active'); }
    showToast(`${ticker} removed from watchlist`, 'info');
  } else {
    wlAdd(ticker);
    if (btn) { btn.textContent = '♥'; btn.classList.add('active'); }
    showToast(`${ticker} added to watchlist`, 'success');
  }
}

function syncHeartButton(ticker) {
  const btn = document.getElementById('wl-heart-btn');
  if (!btn) return;
  if (wlHas(ticker)) {
    btn.textContent = '♥';
    btn.classList.add('active');
  } else {
    btn.textContent = '♡';
    btn.classList.remove('active');
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Auto-refresh every 60 s
// ──────────────────────────────────────────────────────────────────────────────
function startWatchlistRefresh() {
  if (_watchlistRefreshTimer) clearInterval(_watchlistRefreshTimer);
  _watchlistRefreshTimer = setInterval(() => {
    console.log('[watchlist] Auto-refresh tick');
    const sidebar = document.getElementById('watchlist-sidebar');
    if (sidebar && sidebar.classList.contains('open')) {
      renderWatchlist();
    }
    updateWatchlistBadge();
  }, WL_REFRESH_MS);
  console.log('[watchlist] Auto-refresh started (every 60s)');
}

// ──────────────────────────────────────────────────────────────────────────────
// Init
// ──────────────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  updateWatchlistBadge();
  startWatchlistRefresh();

  // Wire overlay click to close
  const overlay = document.getElementById('watchlist-overlay');
  if (overlay) overlay.addEventListener('click', closeWatchlistSidebar);

  console.log('[watchlist] Initialised. Items:', wlLoad());
});
