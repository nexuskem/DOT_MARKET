"""
evaluate_model.py — Loads a saved model + scaler and evaluates on test data.

Outputs:
  • RMSE, MAE, Directional Accuracy printed to console
  • saved_models/{ticker}_evaluation.png  — actual vs predicted chart
"""

import argparse
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

import keras

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from data_pipeline.fetch_data import fetch_stock_data
from data_pipeline.engineer_features import engineer_features
from data_pipeline.preprocess import preprocess, load_scaler, FEATURE_COLS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "saved_models"
N_FEATURES  = 13


def evaluate(ticker: str) -> dict:
    ticker = ticker.upper()

    # ── Load model ────────────────────────────────────────────────────────────
    model_path = MODELS_DIR / f"{ticker}_model.keras"
    if not model_path.exists():
        raise FileNotFoundError(f"No model found for '{ticker}' at {model_path}")

    model = keras.models.load_model(str(model_path))
    logger.info(f"[{ticker}] Model loaded from {model_path}")

    # ── Reload scaler and data ────────────────────────────────────────────────
    scaler = load_scaler(ticker)
    df_raw  = fetch_stock_data(ticker)
    df_feat = engineer_features(df_raw)
    _, _, X_test, _, _, y_test, _, _ = preprocess(df_feat, ticker)

    # ── Predict ───────────────────────────────────────────────────────────────
    y_pred_scaled = model.predict(X_test, verbose=0).flatten()

    def inverse_close(scaled_vals: np.ndarray) -> np.ndarray:
        dummy = np.zeros((len(scaled_vals), N_FEATURES), dtype=np.float32)
        dummy[:, 3] = scaled_vals
        return scaler.inverse_transform(dummy)[:, 3]

    y_test_real = inverse_close(y_test)
    y_pred_real = inverse_close(y_pred_scaled)

    # ── Metrics ───────────────────────────────────────────────────────────────
    rmse = float(np.sqrt(np.mean((y_test_real - y_pred_real) ** 2)))
    mae  = float(np.mean(np.abs(y_test_real - y_pred_real)))

    # Directional accuracy: did prediction move in same direction as actual?
    actual_direction = np.sign(np.diff(y_test_real))
    pred_direction   = np.sign(np.diff(y_pred_real))
    dir_accuracy = float(np.mean(actual_direction == pred_direction)) * 100

    logger.info(f"[{ticker}] RMSE: ${rmse:.4f}  MAE: ${mae:.4f}  Directional Accuracy: {dir_accuracy:.2f}%")

    # ── Plot ──────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(y_test_real, label="Actual Price", color="#00d4ff", linewidth=1.5)
    ax.plot(y_pred_real, label="Predicted Price", color="#00ff88", linewidth=1.5, linestyle="--")
    ax.set_title(f"{ticker} — Actual vs Predicted (Test Set)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Time Step")
    ax.set_ylabel("Price (USD)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    out_path = MODELS_DIR / f"{ticker}_evaluation.png"
    fig.savefig(str(out_path), dpi=150)
    plt.close(fig)
    logger.info(f"[{ticker}] Evaluation chart saved → {out_path}")

    return {
        "ticker": ticker,
        "rmse": rmse,
        "mae": mae,
        "directional_accuracy_pct": dir_accuracy,
        "chart_path": str(out_path),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate saved LSTM model.")
    parser.add_argument("ticker", nargs="?", default="AAPL")
    args = parser.parse_args()

    metrics = evaluate(args.ticker)
    print(f"\nEvaluation Results for {metrics['ticker']}:")
    print(f"  RMSE               : ${metrics['rmse']:.4f}")
    print(f"  MAE                : ${metrics['mae']:.4f}")
    print(f"  Directional Acc.   : {metrics['directional_accuracy_pct']:.2f}%")
    print(f"  Chart saved to     : {metrics['chart_path']}")
