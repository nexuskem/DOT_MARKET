"""
fetch_data.py — Downloads OHLCV stock data via yfinance with local CSV caching.
Cache is invalidated if older than 1 day.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_MAX_AGE_HOURS = 24  # hours before cache is considered stale


def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker.upper()}.csv"


def _is_cache_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    modified_time = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - modified_time < timedelta(hours=CACHE_MAX_AGE_HOURS)


def fetch_stock_data(ticker: str, period: str = "5y", retries: int = 3, timeout: int = 10) -> pd.DataFrame:
    """
    Fetch OHLCV data for *ticker* covering the last *period*.

    Parameters
    ----------
    ticker  : Stock symbol, e.g. "AAPL"
    period  : yfinance period string, default "5y"
    retries : Number of download retries on transient errors
    timeout : Per-attempt timeout in seconds

    Returns
    -------
    pd.DataFrame with columns: Open, High, Low, Close, Volume
    """
    ticker = ticker.upper().strip()
    cache_file = _cache_path(ticker)

    # ── Load from cache if fresh ──────────────────────────────────────────────
    if _is_cache_fresh(cache_file):
        logger.info(f"[{ticker}] Loading from cache: {cache_file}")
        try:
            df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            if not df.empty:
                return df
            logger.warning(f"[{ticker}] Cache file is empty, re-downloading.")
        except Exception as exc:
            logger.warning(f"[{ticker}] Failed to read cache ({exc}), re-downloading.")

    # ── Download from yfinance ────────────────────────────────────────────────
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"[{ticker}] Downloading data (attempt {attempt}/{retries}) …")
            raw = yf.Ticker(ticker)
            df = raw.history(period=period, timeout=timeout)

            if df is None or df.empty:
                raise ValueError(f"yfinance returned empty DataFrame for '{ticker}'.")

            # Keep only OHLCV columns; drop extra yfinance columns
            ohlcv_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df = df[ohlcv_cols].copy()

            # Remove timezone info so downstream code stays simple
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            df.index.name = "Date"
            df.to_csv(cache_file)
            logger.info(f"[{ticker}] Saved {len(df)} rows to cache.")
            return df

        except Exception as exc:
            last_exc = exc
            logger.warning(f"[{ticker}] Attempt {attempt} failed: {exc}")
            if attempt < retries:
                time.sleep(2 ** attempt)  # exponential back-off

    raise RuntimeError(
        f"Failed to fetch data for '{ticker}' after {retries} attempts. "
        f"Last error: {last_exc}"
    )


def get_company_name(ticker: str) -> str:
    """Return the long company name for *ticker*, or ticker itself on failure."""
    known = {
        "GOOGL": "Alphabet Inc.",
        "MSFT": "Microsoft Corporation",
        "AAPL": "Apple Inc.",
        "AMZN": "Amazon.com Inc.",
        "NVDA": "NVIDIA Corporation",
        "TSLA": "Tesla Inc.",
        "META": "Meta Platforms Inc.",
        "NFLX": "Netflix Inc.",
        "AMD": "Advanced Micro Devices",
        "INTC": "Intel Corporation",
    }
    ticker = ticker.upper()
    if ticker in known:
        return known[ticker]
    try:
        info = yf.Ticker(ticker).info
        return info.get("longName") or info.get("shortName") or ticker
    except Exception:
        return ticker


if __name__ == "__main__":
    df = fetch_stock_data("AAPL")
    print(df.tail())
    print("Rows:", len(df))
