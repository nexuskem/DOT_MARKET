"""
train_model.py — Builds and trains the LSTM model for a single ticker.

Architecture (60 timesteps × 13 features → 1 price output):
  LSTM(128, return_sequences=True) → Dropout(0.2)
  LSTM(64,  return_sequences=True) → Dropout(0.2)
  LSTM(32,  return_sequences=False) → Dropout(0.2)
  Dense(16, relu) → Dense(1)
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

# ── Keras 3 / TF 2.16+ — use keras directly ──────────────────────────────────
import tensorflow as tf
import keras
from keras.callbacks import EarlyStopping, ModelCheckpoint
from keras.layers import Dense, Dropout, LSTM, Input
from keras.models import Sequential
from keras.optimizers import Adam

# ── Project imports ───────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from data_pipeline.fetch_data import fetch_stock_data
from data_pipeline.engineer_features import engineer_features
from data_pipeline.preprocess import preprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "saved_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

N_TIMESTEPS = 60
N_FEATURES  = 13


def build_model(timesteps: int = N_TIMESTEPS, n_features: int = N_FEATURES) -> keras.Model:
    inputs = Input(shape=(timesteps, n_features), name="seq_input")
    x = LSTM(128, return_sequences=True)(inputs)
    x = Dropout(0.2)(x)
    x = LSTM(64, return_sequences=True)(x)
    x = Dropout(0.2)(x)
    x = LSTM(32, return_sequences=False)(x)
    x = Dropout(0.2)(x)
    x = Dense(16, activation="relu")(x)
    outputs = Dense(1, name="price_output")(x)

    model = keras.Model(inputs=inputs, outputs=outputs, name="dot_market_lstm")
    model.compile(
        optimizer=Adam(learning_rate=0.001),
        loss="mean_squared_error",
        metrics=["mae"],
    )
    logger.info(f"Model built — params: {model.count_params():,}")
    return model


def train(ticker: str, epochs: int = 100, batch_size: int = 32) -> dict:
    """
    Full train pipeline for *ticker*.

    Returns
    -------
    dict with keys: ticker, rmse, mae, model_path
    """
    ticker = ticker.upper()
    logger.info(f"[{ticker}] ── Starting training pipeline ──")

    # 1. Data
    df_raw  = fetch_stock_data(ticker)
    df_feat = engineer_features(df_raw)
    X_train, X_val, X_test, y_train, y_val, y_test, scaler, _ = preprocess(df_feat, ticker)

    logger.info(
        f"[{ticker}] Train {X_train.shape}, Val {X_val.shape}, Test {X_test.shape}"
    )

    # 2. Model
    model = build_model(X_train.shape[1], X_train.shape[2])

    # 3. Callbacks
    model_path = MODELS_DIR / f"{ticker}_model.keras"
    callbacks = [
        EarlyStopping(
            monitor="val_loss",
            patience=10,
            restore_best_weights=True,
            verbose=1,
        ),
        ModelCheckpoint(
            filepath=str(model_path),
            monitor="val_loss",
            save_best_only=True,
            verbose=1,
        ),
    ]

    # 4. Train
    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=epochs,
        batch_size=batch_size,
        callbacks=callbacks,
        verbose=1,
    )

    # 5. Evaluate on test set
    y_pred_scaled = model.predict(X_test, verbose=0).flatten()

    # Inverse-transform Close price only (column 3)
    def inverse_close(scaled_vals: np.ndarray) -> np.ndarray:
        dummy = np.zeros((len(scaled_vals), N_FEATURES), dtype=np.float32)
        dummy[:, 3] = scaled_vals
        return scaler.inverse_transform(dummy)[:, 3]

    y_test_real = inverse_close(y_test)
    y_pred_real = inverse_close(y_pred_scaled)

    rmse = float(np.sqrt(np.mean((y_test_real - y_pred_real) ** 2)))
    mae  = float(np.mean(np.abs(y_test_real - y_pred_real)))

    logger.info(f"[{ticker}] ✓ Test RMSE: ${rmse:.4f}  MAE: ${mae:.4f}")
    logger.info(f"[{ticker}] Model saved → {model_path}")

    return {"ticker": ticker, "rmse": rmse, "mae": mae, "model_path": str(model_path)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train LSTM model for a single ticker.")
    parser.add_argument("ticker", nargs="?", default="AAPL", help="Stock ticker, e.g. AAPL")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    result = train(args.ticker, epochs=args.epochs, batch_size=args.batch_size)
    print(f"\nTraining complete: {result}")
