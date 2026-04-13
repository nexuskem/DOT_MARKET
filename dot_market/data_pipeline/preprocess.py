"""
preprocess.py — Converts engineered features into LSTM-ready sequences.

• 60-day look-back window (sliding window)
• Features: Open, High, Low, Close, Volume, RSI, MACD, MACD_Signal,
            BB_upper, BB_lower, SMA50, SMA200, Volume_MA  (13 total)
• MinMaxScaler fitted on train data only — saved per ticker
• Split: 80 % train, 10 % val, 10 % test
"""

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SCALERS_DIR = Path(__file__).parent / "saved_scalers"
SCALERS_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK   = 60   # timesteps fed to LSTM
TRAIN_FRAC = 0.80
VAL_FRAC   = 0.10
# test = remaining 10 %

FEATURE_COLS = [
    "Open", "High", "Low", "Close", "Volume",
    "RSI", "MACD", "MACD_Signal",
    "BB_upper", "BB_lower",
    "SMA50", "SMA200",
    "Volume_MA",
]  # 13 features — must match model input shape (60, 13)


def _build_sequences(data: np.ndarray, lookback: int):
    """
    Create sliding-window sequences of shape (N, lookback, n_features)
    and corresponding targets y (next-day Close index = column 3).
    """
    X, y = [], []
    for i in range(lookback, len(data)):
        X.append(data[i - lookback : i, :])  # (lookback, 13)
        y.append(data[i, 3])                  # Close column index = 3
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def preprocess(df: pd.DataFrame, ticker: str):
    """
    Full preprocessing pipeline for *ticker*.

    Parameters
    ----------
    df     : Engineered-feature DataFrame (output of engineer_features)
    ticker : Used for naming the saved scaler file

    Returns
    -------
    X_train, X_val, X_test  : shape (N, 60, 13)
    y_train, y_val, y_test  : shape (N,)
    scaler                  : fitted MinMaxScaler (also persisted to disk)
    feature_cols            : list[str] — column order used
    """
    ticker = ticker.upper()

    # ── Validate columns ──────────────────────────────────────────────────────
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame is missing engineered columns: {missing}")

    data = df[FEATURE_COLS].values  # (T, 13)

    n = len(data)
    if n < LOOKBACK + 10:
        raise ValueError(
            f"Not enough rows ({n}) to build sequences with lookback={LOOKBACK}. "
            "Need at least lookback + 10 rows."
        )

    # ── Train / val / test split (on raw data before scaling) ────────────────
    train_end = int(n * TRAIN_FRAC)
    val_end   = int(n * (TRAIN_FRAC + VAL_FRAC))

    train_raw = data[:train_end]
    val_raw   = data[train_end : val_end]
    test_raw  = data[val_end:]

    # ── Fit scaler on train only ──────────────────────────────────────────────
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaler.fit(train_raw)

    train_scaled = scaler.transform(train_raw)
    val_scaled   = scaler.transform(val_raw)
    test_scaled  = scaler.transform(test_raw)

    # For sequences that span the train/val boundary we need a combined
    # scaled array so val sequences have proper historical context.
    trainval_scaled = scaler.transform(data[:val_end])
    test_full_scaled = scaler.transform(data[train_end:])

    # ── Build sequences ───────────────────────────────────────────────────────
    X_train, y_train = _build_sequences(train_scaled, LOOKBACK)

    # Val sequences need preceding context from train — use combined array
    X_tv, y_tv = _build_sequences(trainval_scaled, LOOKBACK)
    n_train_seq = len(X_train)
    X_val = X_tv[n_train_seq:]
    y_val = y_tv[n_train_seq:]

    # Test sequences need preceding context from val — use test_full_scaled
    X_tf, y_tf = _build_sequences(test_full_scaled, LOOKBACK)
    # The first n_val_seq sequences belong to val's extended range; slice to test only
    n_val_seq = int((val_end - train_end) * 1)
    X_test = X_tf[max(0, n_val_seq - LOOKBACK):]
    y_test = y_tf[max(0, n_val_seq - LOOKBACK):]

    logger.info(
        f"[{ticker}] Sequences — train: {X_train.shape}, val: {X_val.shape}, test: {X_test.shape}"
    )

    # ── Save scaler ───────────────────────────────────────────────────────────
    scaler_path = SCALERS_DIR / f"{ticker}_scaler.pkl"
    joblib.dump(scaler, scaler_path)
    logger.info(f"[{ticker}] Scaler saved → {scaler_path}")

    return X_train, X_val, X_test, y_train, y_val, y_test, scaler, FEATURE_COLS


def load_scaler(ticker: str) -> MinMaxScaler:
    """Load a previously saved scaler for *ticker*."""
    ticker = ticker.upper()
    path = SCALERS_DIR / f"{ticker}_scaler.pkl"
    if not path.exists():
        raise FileNotFoundError(f"No scaler found for '{ticker}' at {path}")
    return joblib.load(path)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from fetch_data import fetch_stock_data
    from engineer_features import engineer_features

    df_raw  = fetch_stock_data("AAPL")
    df_feat = engineer_features(df_raw)
    X_train, X_val, X_test, y_train, y_val, y_test, scaler, cols = preprocess(df_feat, "AAPL")
    print("X_train:", X_train.shape)
    print("X_val  :", X_val.shape)
    print("X_test :", X_test.shape)
    print("Features:", cols)
