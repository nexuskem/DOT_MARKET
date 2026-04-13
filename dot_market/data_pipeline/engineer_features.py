"""
engineer_features.py — Technical indicator feature engineering.

Adds:
  RSI(14), MACD(12,26,9), Bollinger Bands(20), SMA50, SMA200,
  daily % price change, Volume MA(20)
"""

import logging
import pandas as pd
import pandas_ta as ta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute technical indicators and attach them as new columns.

    Parameters
    ----------
    df : DataFrame with at least Open, High, Low, Close, Volume columns
         and a DatetimeIndex.

    Returns
    -------
    pd.DataFrame — original columns + indicator columns, NaN rows dropped.
    """
    df = df.copy()

    if df.empty:
        raise ValueError("Input DataFrame is empty — cannot engineer features.")

    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # ── RSI (14-period) ───────────────────────────────────────────────────────
    rsi = ta.rsi(df["Close"], length=14)
    df["RSI"] = rsi

    # ── MACD (12, 26, 9) ─────────────────────────────────────────────────────
    macd_df = ta.macd(df["Close"], fast=12, slow=26, signal=9)
    if macd_df is not None and not macd_df.empty:
        # pandas_ta names vary; normalise to our names
        macd_cols = macd_df.columns.tolist()
        # Typical output: MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
        macd_line_col   = [c for c in macd_cols if c.startswith("MACD_")][0]
        signal_line_col = [c for c in macd_cols if c.startswith("MACDs")][0]
        df["MACD"]        = macd_df[macd_line_col]
        df["MACD_Signal"] = macd_df[signal_line_col]
    else:
        logger.warning("MACD calculation returned None — filling with NaN.")
        df["MACD"]        = float("nan")
        df["MACD_Signal"] = float("nan")

    # ── Bollinger Bands (20-period, 2 std) ────────────────────────────────────
    bb_df = ta.bbands(df["Close"], length=20, std=2)
    if bb_df is not None and not bb_df.empty:
        bb_cols = bb_df.columns.tolist()
        upper_col = [c for c in bb_cols if "BBU" in c][0]
        lower_col = [c for c in bb_cols if "BBL" in c][0]
        df["BB_upper"] = bb_df[upper_col]
        df["BB_lower"] = bb_df[lower_col]
    else:
        logger.warning("Bollinger Bands calculation returned None — filling with NaN.")
        df["BB_upper"] = float("nan")
        df["BB_lower"] = float("nan")

    # ── Simple Moving Averages ────────────────────────────────────────────────
    df["SMA50"]  = df["Close"].rolling(window=50).mean()
    df["SMA200"] = df["Close"].rolling(window=200).mean()

    # ── Daily % Price Change ──────────────────────────────────────────────────
    df["Price_Change_Pct"] = df["Close"].pct_change() * 100

    # ── Volume Moving Average (20-day) ────────────────────────────────────────
    df["Volume_MA"] = df["Volume"].rolling(window=20).mean()

    # ── Drop NaN rows produced by rolling windows ─────────────────────────────
    before = len(df)
    df.dropna(inplace=True)
    after = len(df)
    logger.info(f"Feature engineering complete. Rows: {before} → {after} (dropped {before - after} NaN rows).")

    if df.empty:
        raise ValueError(
            "All rows were dropped after feature engineering — "
            "the input data likely has too few rows."
        )

    return df


if __name__ == "__main__":
    from fetch_data import fetch_stock_data

    raw = fetch_stock_data("AAPL")
    featured = engineer_features(raw)
    print(featured[["Close", "RSI", "MACD", "MACD_Signal", "BB_upper", "BB_lower",
                     "SMA50", "SMA200", "Volume_MA"]].tail(10))
    print("Shape:", featured.shape)
