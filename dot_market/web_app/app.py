"""
app.py — DOT MARKET Flask backend.

All endpoints documented in the project spec are implemented here.
Run with: python web_app/app.py
"""

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import yfinance as yf
from flask import Flask, g, jsonify, render_template, request, send_file, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

# ── Project path setup ────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from data_pipeline.engineer_features import engineer_features
from data_pipeline.fetch_data import fetch_stock_data, get_company_name
from data_pipeline.preprocess import load_scaler, FEATURE_COLS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dot_market_dev_secret")

# ── Paths ─────────────────────────────────────────────────────────────────────
MODELS_DIR  = PROJECT_ROOT / "ml_model" / "saved_models"
EXPORTS_DIR = PROJECT_ROOT / "exports"
DB_PATH     = PROJECT_ROOT / "predictions.db"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TICKERS     = ["GOOGL", "MSFT", "AAPL", "AMZN", "NVDA", "TSLA", "META", "NFLX", "AMD", "INTC"]
PREDICT_COUNTER: dict[str, int] = {}   # counts how often a ticker has been predicted this session

N_FEATURES = len(FEATURE_COLS)  # 13

# ── Lazy-load Keras only when a prediction is needed ──────────────────────────
_keras = None

def _get_keras():
    global _keras
    if _keras is None:
        import keras as _k
        _keras = _k
    return _keras


# ══════════════════════════════════════════════════════════════════════════════
#  SQLite helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_db():
    if "db" not in g:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL,
            predicted_price REAL    NOT NULL,
            actual_price    REAL,
            prediction_date TEXT    NOT NULL,
            accuracy_pct    REAL,
            signal          TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info(f"SQLite DB initialised at {DB_PATH}")


# ══════════════════════════════════════════════════════════════════════════════
#  Prediction helpers
# ══════════════════════════════════════════════════════════════════════════════

def _signal(current: float, predicted: float) -> str:
    pct = (predicted - current) / current * 100
    if pct > 0.5:
        return "BUY"
    if pct < -0.5:
        return "SELL"
    return "HOLD"


def _mock_confidence(ticker: str) -> int:
    """Return a plausible mock confidence score (60-92%) seeded by ticker."""
    seed = sum(ord(c) for c in ticker)
    return 60 + (seed % 33)


def _inverse_close(scaler, scaled_vals: np.ndarray) -> np.ndarray:
    dummy = np.zeros((len(scaled_vals), N_FEATURES), dtype=np.float32)
    dummy[:, 3] = scaled_vals
    return scaler.inverse_transform(dummy)[:, 3]


def _sma_trend_fallback(df, ticker: str) -> float:
    """Fallback prediction when no model exists: last price nudged by SMA trend."""
    last_price = float(df["Close"].iloc[-1])
    if "SMA50" in df.columns and "SMA200" in df.columns:
        sma50  = float(df["SMA50"].iloc[-1])
        sma200 = float(df["SMA200"].iloc[-1])
        # Golden cross → slight bullish nudge; death cross → bearish
        trend_pct = 0.003 if sma50 > sma200 else -0.003
        return round(last_price * (1 + trend_pct), 2)
    return round(last_price * 1.001, 2)  # tiny up nudge by default


def _run_prediction(ticker: str) -> dict:
    """
    Full prediction pipeline.
    Falls back to SMA-trend method if no trained model exists.
    """
    ticker = ticker.upper()

    df_raw  = fetch_stock_data(ticker)
    df_feat = engineer_features(df_raw)

    current_price = float(df_feat["Close"].iloc[-1])
    model_path    = MODELS_DIR / f"{ticker}_model.keras"

    # ── Model-based prediction ────────────────────────────────────────────────
    if model_path.exists():
        try:
            keras_mod = _get_keras()
            model     = keras_mod.models.load_model(str(model_path))
            scaler    = load_scaler(ticker)

            data_scaled = scaler.transform(df_feat[FEATURE_COLS].values)
            lookback    = 60
            if len(data_scaled) < lookback:
                raise ValueError("Not enough data for look-back window.")

            seq    = data_scaled[-lookback:].reshape(1, lookback, N_FEATURES).astype(np.float32)
            raw    = model.predict(seq, verbose=0)[0][0]
            pred   = float(_inverse_close(scaler, np.array([raw]))[0])
        except Exception as exc:
            logger.warning(f"[{ticker}] Model prediction failed ({exc}), using fallback.")
            pred = _sma_trend_fallback(df_feat, ticker)
    else:
        logger.info(f"[{ticker}] No model found — using SMA-trend fallback.")
        pred = _sma_trend_fallback(df_feat, ticker)

    # ── Build response payload ─────────────────────────────────────────────────
    last_90 = df_feat.tail(90)
    last_30 = df_feat.tail(30)

    def _to_list(series):
        return [round(float(v), 4) for v in series.tolist()]

    def _to_dates(index):
        return [str(d)[:10] for d in index.tolist()]

    hist_dates  = _to_dates(last_90.index)
    hist_close  = _to_list(last_90["Close"])

    # predicted_series = last 30 actual closes + predicted point
    pred_series = _to_list(last_30["Close"]) + [round(pred, 2)]
    pred_dates  = _to_dates(last_30.index) + [
        str((datetime.now() + timedelta(days=1)).date())
    ]

    change_pct = round((pred - current_price) / current_price * 100, 2)
    signal     = _signal(current_price, pred)
    confidence = _mock_confidence(ticker)

    # Update prediction history
    PREDICT_COUNTER[ticker] = PREDICT_COUNTER.get(ticker, 0) + 1
    try:
        db = get_db()
        db.execute(
            "INSERT INTO predictions (ticker, predicted_price, prediction_date, signal) VALUES (?, ?, ?, ?)",
            (ticker, pred, datetime.now().strftime("%Y-%m-%d"), signal)
        )
        db.commit()
    except Exception as exc:
        logger.warning(f"DB insert failed: {exc}")

    return {
        "ticker":            ticker,
        "company_name":      get_company_name(ticker),
        "current_price":     round(current_price, 2),
        "predicted_price":   round(pred, 2),
        "change_pct":        change_pct,
        "signal":            signal,
        "confidence":        confidence,
        "historical_dates":  hist_dates,
        "historical_close":  hist_close,
        "predicted_series":  pred_series,
        "predicted_dates":   pred_dates,
        "rsi":               _to_list(last_90["RSI"]),
        "macd":              _to_list(last_90["MACD"]),
        "macd_signal":       _to_list(last_90["MACD_Signal"]),
        "bb_upper":          _to_list(last_90["BB_upper"]),
        "bb_lower":          _to_list(last_90["BB_lower"]),
        "sma50":             _to_list(last_90["SMA50"]),
        "sma200":            _to_list(last_90["SMA200"]),
        "volume":            _to_list(last_90["Volume"]),
        "open":              _to_list(last_90["Open"]),
        "high":              _to_list(last_90["High"]),
        "low":               _to_list(last_90["Low"]),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  DEMO mode mock data
# ══════════════════════════════════════════════════════════════════════════════

def _demo_data() -> dict:
    import random
    random.seed(42)
    dates  = [(datetime.now() - timedelta(days=90 - i)).strftime("%Y-%m-%d") for i in range(90)]
    close  = [150.0 + random.uniform(-5, 5) * i ** 0.5 for i in range(90)]
    volume = [int(50_000_000 + random.uniform(-2e7, 2e7)) for _ in range(90)]
    rsi    = [50 + random.uniform(-20, 20) for _ in range(90)]
    macd   = [random.uniform(-2, 2) for _ in range(90)]
    macd_s = [random.uniform(-1.5, 1.5) for _ in range(90)]
    bb_u   = [c + random.uniform(3, 6) for c in close]
    bb_l   = [c - random.uniform(3, 6) for c in close]
    sma50  = [sum(close[max(0, i - 50):i + 1]) / min(i + 1, 50) for i in range(90)]
    sma200 = [sum(close[max(0, i - 90):i + 1]) / min(i + 1, 90) for i in range(90)]

    cur_price  = round(close[-1], 2)
    pred_price = round(cur_price * 1.012, 2)

    return {
        "ticker":           "DEMO",
        "company_name":     "Demo Corp Ltd.",
        "current_price":    cur_price,
        "predicted_price":  pred_price,
        "change_pct":       1.20,
        "signal":           "BUY",
        "confidence":       82,
        "historical_dates": dates,
        "historical_close": [round(c, 2) for c in close],
        "predicted_series": [round(c, 2) for c in close[-30:]] + [pred_price],
        "predicted_dates":  dates[-30:] + [(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")],
        "rsi":              [round(r, 2) for r in rsi],
        "macd":             [round(m, 4) for m in macd],
        "macd_signal":      [round(s, 4) for s in macd_s],
        "bb_upper":         [round(b, 2) for b in bb_u],
        "bb_lower":         [round(b, 2) for b in bb_l],
        "sma50":            [round(s, 2) for s in sma50],
        "sma200":           [round(s, 2) for s in sma200],
        "volume":           volume,
        "open":             [round(c * 0.998, 2) for c in close],
        "high":             [round(c * 1.005, 2) for c in close],
        "low":              [round(c * 0.995, 2) for c in close],
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Routes
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        is_demo = request.form.get("demo") == "true"
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if is_demo:
            session["logged_in"] = True
            session["user"] = "demo"
            return redirect(url_for("index"))
        
        db = get_db()
        user_row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        
        if user_row and check_password_hash(user_row["password_hash"], password):
            session["logged_in"] = True
            session["user"] = username
            return redirect(url_for("index"))
        
        return render_template("login.html", error="Invalid username or password.")

    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm", "").strip()

        if not username or not password:
            return render_template("signup.html", error="Username and password are required.")
        if password != confirm:
            return render_template("signup.html", error="Passwords do not match.")

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            return render_template("signup.html", error="Username already exists.")

        try:
            pass_hash = generate_password_hash(password)
            db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pass_hash))
            db.commit()
        except Exception as e:
            return render_template("signup.html", error=f"Database error: {e}")

        session["logged_in"] = True
        session["user"] = username
        return redirect(url_for("index"))

    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/predict", methods=["POST"])
def predict():
    try:
        body   = request.get_json(force=True) or {}
        ticker = str(body.get("ticker", "AAPL")).strip().upper()

        if ticker == "DEMO":
            return jsonify(_demo_data())

        data = _run_prediction(ticker)
        return jsonify(data)

    except Exception as exc:
        logger.exception(f"/predict error: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/news/<ticker>")
def news(ticker: str):
    try:
        from textblob import TextBlob

        ticker  = ticker.upper().strip()
        stock   = yf.Ticker(ticker)
        raw_news = stock.news or []

        results = []
        now     = datetime.now()
        for item in raw_news[:5]:
            title = item.get("title", "No title")
            link  = item.get("link",  "#")
            published = item.get("providerPublishTime", None)

            blob  = TextBlob(title)
            score = round(blob.sentiment.polarity, 3)
            if score > 0.05:
                sentiment = "positive"
            elif score < -0.05:
                sentiment = "negative"
            else:
                sentiment = "neutral"

            if published:
                pub_dt = datetime.fromtimestamp(published)
                diff   = now - pub_dt
                if diff.total_seconds() < 3600:
                    time_str = f"{int(diff.total_seconds() // 60)}m ago"
                elif diff.total_seconds() < 86400:
                    time_str = f"{int(diff.total_seconds() // 3600)}h ago"
                else:
                    time_str = f"{diff.days}d ago"
            else:
                time_str = "Recently"

            results.append({
                "title":     title,
                "link":      link,
                "sentiment": sentiment,
                "score":     score,
                "time":      time_str,
            })

        return jsonify(results)

    except Exception as exc:
        logger.exception(f"/news error: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/watchlist/trending")
def trending():
    try:
        sorted_tickers = sorted(PREDICT_COUNTER, key=PREDICT_COUNTER.get, reverse=True)
        top5 = sorted_tickers[:5] or DEFAULT_TICKERS[:5]
        result = []
        for t in top5:
            try:
                df   = fetch_stock_data(t)
                feat = engineer_features(df)
                cur  = float(feat["Close"].iloc[-1])
                pred = _sma_trend_fallback(feat, t)
                sig  = _signal(cur, pred)
                chg  = round((pred - cur) / cur * 100, 2)
                result.append({"ticker": t, "signal": sig, "change_pct": chg, "price": round(cur, 2)})
            except Exception:
                result.append({"ticker": t, "signal": "HOLD", "change_pct": 0, "price": 0})
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/export/<ticker>", methods=["POST", "GET"])
def export_pdf(ticker: str):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        ticker = ticker.upper().strip()

        # Get latest prediction data
        try:
            data = _demo_data() if ticker == "DEMO" else _run_prediction(ticker)
        except Exception:
            data = {
                "company_name": ticker, "current_price": 0, "predicted_price": 0,
                "signal": "N/A", "change_pct": 0, "rsi": [50], "macd": [0], "confidence": 0,
            }

        pdf_path = EXPORTS_DIR / f"{ticker}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        doc    = SimpleDocTemplate(str(pdf_path), pagesize=letter)
        styles = getSampleStyleSheet()
        story  = []

        # Title
        title_style = styles["Title"]
        story.append(Paragraph(f"DOT MARKET — {ticker} Prediction Report", title_style))
        story.append(Spacer(1, 0.25 * inch))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
        story.append(Spacer(1, 0.5 * inch))

        # Data table
        table_data = [
            ["Field",             "Value"],
            ["Company",           data.get("company_name", ticker)],
            ["Current Price",     f"${data.get('current_price', 0):,.2f}"],
            ["Predicted Price",   f"${data.get('predicted_price', 0):,.2f}"],
            ["Expected Change",   f"{data.get('change_pct', 0):+.2f}%"],
            ["Signal",            data.get("signal", "N/A")],
            ["Confidence",        f"{data.get('confidence', 0)}%"],
            ["Latest RSI",        f"{data['rsi'][-1]:.2f}" if data.get("rsi") else "N/A"],
            ["Latest MACD",       f"{data['macd'][-1]:.4f}" if data.get("macd") else "N/A"],
            ["Report Date",       datetime.now().strftime("%Y-%m-%d")],
        ]

        table = Table(table_data, colWidths=[3 * inch, 3.5 * inch])
        table.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#0a0a0f")),
            ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
            ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("BACKGROUND",  (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("GRID",        (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME",    (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, -1), 11),
            ("PADDING",     (0, 0), (-1, -1), 8),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph(
            "Disclaimer: This report is generated by an AI model for educational purposes only. "
            "It does not constitute financial advice.",
            styles["Italic"]
        ))

        doc.build(story)
        return send_file(str(pdf_path), as_attachment=True, download_name=f"{ticker}_report.pdf")

    except Exception as exc:
        logger.exception(f"/export error: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/health")
def health():
    try:
        models_loaded = [
            t for t in DEFAULT_TICKERS
            if (MODELS_DIR / f"{t}_model.keras").exists()
        ]
        return jsonify({"status": "ok", "models_loaded": models_loaded})
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500


@app.route("/history/<ticker>")
def history(ticker: str):
    try:
        ticker = ticker.upper().strip()
        db     = get_db()
        rows   = db.execute(
            "SELECT * FROM predictions WHERE ticker = ? ORDER BY id DESC LIMIT 10",
            (ticker,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/earnings/<ticker>")
def earnings(ticker: str):
    try:
        ticker = ticker.upper().strip()
        stock  = yf.Ticker(ticker)
        cal    = stock.calendar
        if cal is None or (hasattr(cal, "empty") and cal.empty):
            return jsonify({"ticker": ticker, "earnings_date": "N/A", "eps_estimate": "N/A"})

        if isinstance(cal, dict):
            ed = cal.get("Earnings Date", ["N/A"])
            if isinstance(ed, list) and ed:
                ed = str(ed[0])[:10]
            eps = cal.get("EPS Estimate", "N/A")
        else:
            # DataFrame
            try:
                ed  = str(cal.iloc[0, 0])[:10]
                eps = cal.iloc[1, 0] if len(cal) > 1 else "N/A"
            except Exception:
                ed, eps = "N/A", "N/A"

        return jsonify({"ticker": ticker, "earnings_date": ed, "eps_estimate": eps})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/price/<ticker>")
def price(ticker: str):
    """Lightweight endpoint — returns current price only (used by watchlist refresh)."""
    try:
        ticker = ticker.upper()
        df     = fetch_stock_data(ticker)
        price  = float(df["Close"].iloc[-1])
        prev   = float(df["Close"].iloc[-2])
        chg    = round((price - prev) / prev * 100, 2)
        return jsonify({"ticker": ticker, "price": round(price, 2), "change_pct": chg})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    logger.info(f"DOT MARKET starting on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
