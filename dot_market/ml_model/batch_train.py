"""
batch_train.py — Train LSTM models for all 10 default tickers sequentially.

Usage:
    python ml_model/batch_train.py
    python ml_model/batch_train.py --tickers AAPL MSFT NVDA
"""

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ml_model.train_model import train

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_TICKERS = ["GOOGL", "MSFT", "AAPL", "AMZN", "NVDA", "TSLA", "META", "NFLX", "AMD", "INTC"]


def batch_train(tickers: list[str], epochs: int = 100, batch_size: int = 32) -> list[dict]:
    results = []
    total   = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"Training [{i}/{total}]: {ticker}")
        logger.info(f"{'='*60}")
        t0 = time.time()
        try:
            result = train(ticker, epochs=epochs, batch_size=batch_size)
            result["status"] = "OK"
            result["elapsed_s"] = round(time.time() - t0, 1)
        except Exception as exc:
            logger.error(f"[{ticker}] FAILED: {exc}")
            result = {"ticker": ticker, "status": "FAILED", "error": str(exc), "rmse": None, "mae": None}
        results.append(result)

    return results


def print_summary(results: list[dict]) -> None:
    print("\n" + "="*70)
    print(f"{'TICKER':<8} {'STATUS':<8} {'RMSE':>10} {'MAE':>10} {'TIME (s)':>10}")
    print("-"*70)
    for r in results:
        rmse_str = f"${r['rmse']:.4f}" if r.get("rmse") is not None else "N/A"
        mae_str  = f"${r['mae']:.4f}"  if r.get("mae")  is not None else "N/A"
        time_str = str(r.get("elapsed_s", "N/A"))
        print(f"{r['ticker']:<8} {r['status']:<8} {rmse_str:>10} {mae_str:>10} {time_str:>10}")
    print("="*70)

    passed = sum(1 for r in results if r["status"] == "OK")
    print(f"\nCompleted: {passed}/{len(results)} models trained successfully.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch-train LSTM models for multiple tickers.")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS, help="Tickers to train")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    results = batch_train(args.tickers, epochs=args.epochs, batch_size=args.batch_size)
    print_summary(results)
