# DOT MARKET 🔵
### *Predict the market. Own the future.*

> An AI-powered stock price prediction dashboard built with LSTM neural networks, Flask, and Plotly.js.

---

## 1. Project Overview

DOT MARKET is a full-stack web application that predicts next-day stock closing prices using a deep LSTM neural network trained on 5 years of historical OHLCV data enriched with technical indicators (RSI, MACD, Bollinger Bands, SMAs, Volume MA).

The dashboard provides a Bloomberg-terminal-style dark-theme UI with:
- **Real-time candlestick charts** with overlay indicators
- **Buy / Hold / Sell signals** generated from LSTM predictions
- **News headlines** with TextBlob sentiment analysis
- **Watchlist** with mini sparklines (localStorage-persisted)
- **Price alerts** via browser Notification API
- **PDF report export** via ReportLab
- **Prediction history leaderboard** backed by SQLite
- **Earnings calendar** for watchlisted stocks

---

## 2. Team Roles

| Role | Responsibility |
|------|---------------|
| **Developer 1** | Data Pipeline (`data_pipeline/`) — data fetching, feature engineering, preprocessing |
| **Developer 2** | ML Model (`ml_model/`) — LSTM architecture, training, evaluation, batch training |
| **Developer 3** | Full-Stack Web App (`web_app/`) — Flask API, HTML dashboard, CSS, JS charts |

---

## 3. Setup Instructions

### Prerequisites
- Python 3.10 or 3.11 (TensorFlow 2.15 requires ≤ 3.11)
- pip

### Step 1 — Clone and enter the project
```bash
cd dot_market
```

### Step 2 — Create a virtual environment
```bash
python3.11 -m venv .venv
source .venv/bin/activate      # Linux / macOS
# .venv\Scripts\activate       # Windows
```

### Step 3 — Install dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4 — Download TextBlob corpora
```bash
python -m textblob.download_corpora
```

### Step 5 — (Optional) Train models
Training all 10 models takes 30–90 minutes depending on hardware:
```bash
python ml_model/batch_train.py
```

Or train a single ticker:
```bash
python ml_model/train_model.py AAPL
```

> **Note:** If no model is trained for a ticker, the app automatically falls back to an SMA-trend heuristic prediction. You can test the full UI immediately using the built-in **DEMO** mode.

### Step 6 — Run the app
```bash
python web_app/app.py
```

Open your browser at **http://localhost:5000**

---

## 4. How to Use the Dashboard

1. **Search** — Type a stock ticker (e.g. `AAPL`) in the search bar and press **PREDICT**
2. **DEMO mode** — Type `DEMO` to see the UI with mock data (no model required)
3. **Charts** — Use time-range buttons (1W → 1Y) and overlay checkboxes to customise the view
4. **Compare** — Enter up to 3 tickers in the Compare panel to see normalised performance
5. **Watchlist** — Click ♡ on any prediction to save a ticker; the sidebar shows live prices
6. **Alerts** — Click 🔔 Alerts to set price threshold notifications
7. **PDF Report** — Click **📄 PDF Report** to download a formatted prediction summary
8. **Earnings** — Add stocks to your watchlist to populate the Earnings Calendar

---

## 5. API Endpoints Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/` | Main dashboard |
| `POST` | `/predict` | Run LSTM prediction for a ticker |
| `GET`  | `/news/<ticker>` | Latest 5 news headlines with sentiment |
| `GET`  | `/watchlist/trending` | Top 5 most-predicted tickers |
| `POST` | `/export/<ticker>` | Download PDF report |
| `GET`  | `/health` | Server health + list of loaded models |
| `GET`  | `/history/<ticker>` | Last 10 prediction records from SQLite |
| `GET`  | `/earnings/<ticker>` | Next earnings date from yfinance |
| `GET`  | `/price/<ticker>` | Current price + daily change % |

### POST `/predict` — Request Body
```json
{ "ticker": "AAPL", "days": 1 }
```

### POST `/predict` — Response
```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "current_price": 182.50,
  "predicted_price": 185.20,
  "change_pct": 1.48,
  "signal": "BUY",
  "confidence": 78,
  "historical_dates": ["2024-01-01", "..."],
  "historical_close": [150.0, "..."],
  "rsi": [55.2, "..."],
  "macd": [0.34, "..."],
  "macd_signal": [0.28, "..."],
  "bb_upper": [188.0, "..."],
  "bb_lower": [175.0, "..."],
  "sma50": [180.0, "..."],
  "sma200": [165.0, "..."],
  "volume": [75000000, "..."]
}
```

---

## 6. Features List

- ✅ LSTM neural network (128→64→32 units) with dropout
- ✅ 13 engineered features: OHLCV + RSI + MACD + BB + SMA50/200 + Volume MA
- ✅ 60-day look-back sliding window sequences
- ✅ MinMaxScaler per feature, saved per ticker
- ✅ EarlyStopping + ModelCheckpoint callbacks
- ✅ SMA-trend fallback when no model is trained
- ✅ DEMO mode with mock data
- ✅ Dark / Light mode toggle (CSS variables)
- ✅ Candlestick chart with BB / SMA overlays and forecast star marker
- ✅ RSI, MACD, Volume sub-charts via Plotly.js
- ✅ Compare up to 3 stocks (normalised chart + signal pills)
- ✅ News sentiment via TextBlob
- ✅ Watchlist with localStorage persistence + mini sparklines
- ✅ Price alerts with browser Notification API
- ✅ PDF report generation via ReportLab
- ✅ SQLite prediction history
- ✅ Earnings calendar from yfinance
- ✅ Fully responsive (mobile, tablet, desktop)
- ✅ Zero npm / Node.js dependencies

---

## 7. School Project Notes

- This project was built as a full-stack AI engineering exercise demonstrating the complete ML lifecycle: data → features → model → API → UI.
- The LSTM model is trained purely for educational purposes and **should not be used for real financial decisions**.
- All data is sourced from Yahoo Finance via the `yfinance` library.
- Sentiment analysis uses `TextBlob`, a simple NLP library suitable for headline-level sentiment.
- Architecture decisions prioritise clarity and learnability over maximum prediction accuracy.

---

## Project Structure

```
dot_market/
├── data_pipeline/
│   ├── fetch_data.py          # yfinance download + CSV cache
│   ├── engineer_features.py   # RSI, MACD, BB, SMA, Volume MA
│   ├── preprocess.py          # 60-day sequences + MinMaxScaler
│   ├── cache/                 # Auto-created CSV cache
│   └── saved_scalers/         # Auto-created per-ticker scalers
├── ml_model/
│   ├── train_model.py         # Single-ticker LSTM training
│   ├── evaluate_model.py      # RMSE, MAE, directional accuracy
│   ├── batch_train.py         # Train all 10 tickers at once
│   └── saved_models/          # Auto-created .keras model files
├── web_app/
│   ├── app.py                 # Flask application
│   ├── templates/
│   │   └── index.html         # Full dashboard (single-page)
│   └── static/
│       ├── style.css          # Dark/light theme CSS
│       ├── charts.js          # Plotly.js chart functions
│       ├── watchlist.js       # Watchlist sidebar logic
│       └── alerts.js          # Price alert system
├── exports/                   # PDF reports saved here
├── predictions.db             # SQLite prediction history (auto-created)
├── requirements.txt
├── .env.example
└── README.md
```

---

*DOT MARKET — Built with ❤️ using Python, TensorFlow, Flask, and Plotly.js*
