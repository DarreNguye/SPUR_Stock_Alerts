# SPUR Stock Alert System

A quantitative stock alert system that identifies statistically unusual intraday price drops in fundamentally strong, undervalued equities. When a qualifying ticker is detected, an email alert is sent in real time.

---

## How It Works

The system runs in three phases:

### 1. Monthly Prep (`mprep`)
Builds the **universe** of candidate tickers using WRDS/Compustat data. A ticker enters the universe only if it passes a multi-factor fundamental screen:

| Signal | Description |
|---|---|
| TTM P/E | Current trailing P/E is below its own historical percentile |
| NTM P/E | Current forward P/E is below its own historical percentile |
| Industry TTM P/E | Current trailing P/E is below the industry median |
| Industry NTM P/E | Current forward P/E is below the industry median |
| Analyst Discount | Analyst consensus price target implies ≥5% upside |
| Insider Buying | Net insider share purchases are positive (yfinance) |

The universe is cached to `data/universe.json` and is valid for the calendar month.

### 2. Daily Prep (`dprep`)
Runs at market close each day (automatically triggered by `scan`, or manually).

- Downloads/updates historical price data for universe tickers into `data/historical_prices.parquet`
- Calculates a **returns threshold** for each ticker: the bottom `drop_percentile` of its historical daily returns
- Calculates a **volatility threshold** for each ticker: the top `volatility_percentile` of its rolling 21-day annualised historical volatility

Both thresholds are saved to `data/returns_thresholds.json` and `data/volatilities_thresholds.json`.

### 3. Live Scan (`scan`)
Runs continuously during market hours, polling every 60 seconds.

Each cycle:
1. Fetches live snapshots for all universe tickers via Alpaca (IEX feed)
2. Calculates the live intraday return vs. the previous close
3. Flags tickers where `live_return ≤ returns_threshold` **and** `live_return ≤ -drop_percent`
4. Fetches the nearest 30-day ATM call implied volatility (yfinance) for flagged tickers
5. Flags tickers where `live_IV ≥ volatility_threshold`
6. Calculates a composite score: `Universe_Score + Returns_Score + IV_Score`
7. Sends an email alert for any ticker whose composite score meets `req_score` and where both `Returns_Score = 1` and `IV_Score = 1`

At market close, daily prep runs automatically to update cached data.

---

## Prerequisites

- **Python 3.9+**
- **WRDS account** (Wharton Research Data Services) — for Compustat/IBES fundamental data
- **Alpaca account** — for historical bar data and live snapshots (paper trading account is fine)
- **Gmail account** — with an [App Password](https://support.google.com/accounts/answer/185833) configured for SMTP

---

## Installation

1. Clone or download this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the project root (see [Configuration](#configuration)).

---

## Configuration

### `.env` file

Create a `.env` file in the project root with the following variables:

```env
# WRDS credentials
WRDS_USER=your_wrds_username
WRDS_PASS=your_wrds_password

# Alpaca API keys
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_SECRET_KEY=your_alpaca_secret_key

# Gemini API key (optional — used by the valuation agent, currently disabled)
GEMINI_API_KEY=your_gemini_api_key

# Gmail SMTP
SENDER_EMAIL=your_gmail_address@gmail.com
SENDER_PASSWORD=your_gmail_app_password

# Comma-separated list of recipient email addresses
TO_EMAILS=recipient1@example.com,recipient2@example.com
```

### Parameters (`main.py`)

| Parameter | Default | Description |
|---|---|---|
| `req_score` | `6` | Minimum composite score to trigger an alert (max possible is 8) |
| `pe_percentile` | `0.10` | Historical P/E percentile used as the "cheap" threshold (10th percentile) |
| `analyst_discount` | `0.05` | Minimum analyst upside required to score the analyst signal (5%) |
| `min_market_cap` | `10,000,000,000` | Minimum market cap for universe inclusion ($10B) |
| `lookback_years` | `1` | Years of historical price data to use for threshold calculation |
| `volatility_rolling_window` | `21` | Rolling window (trading days) for historical volatility calculation |
| `drop_percentile` | `0.0015` | Bottom percentile of a ticker's historical returns used as the drop threshold |
| `drop_percent` | `0.10` | Minimum absolute intraday drop required to flag a ticker (10%) |
| `volatility_percentile` | `0.80` | Top percentile of a ticker's historical volatility used as the IV threshold |

---

## Usage

Run all commands from the project root.

### Monthly Prep
Run once at the start of each month to rebuild the universe. Takes several minutes due to WRDS queries and yfinance calls.

```bash
python main.py --mode mprep
```

### Daily Prep
Run at market close to update the historical price cache and recalculate thresholds. This is also triggered automatically at the end of a `scan` session.

```bash
python main.py --mode dprep
```

### Live Scan
Run during market hours. Polls every 60 seconds and sends email alerts when a ticker meets all conditions.

```bash
python main.py --mode scan
```

### Dashboard
View historical scan and alert data in a Streamlit web dashboard.

```bash
streamlit run dashboard.py
```

---

## Recommended Schedule

| Time | Action |
|---|---|
| 1st of the month (pre-market) | `python main.py --mode mprep` |
| Each trading day (pre-market) | `python main.py --mode dprep` (optional — `scan` runs it at close) |
| Market open → close | `python main.py --mode scan` |

---

## Data Files

All cached data lives in the `data/` directory (excluded from version control via `.gitignore`):

| File | Description |
|---|---|
| `data/universe.json` | Universe tickers and fundamental scores (refreshed monthly) |
| `data/historical_prices.parquet` | Daily OHLCV price cache for universe tickers |
| `data/returns_thresholds.json` | Per-ticker drop threshold (bottom percentile of historical returns) |
| `data/volatilities_thresholds.json` | Per-ticker IV threshold (top percentile of historical volatility) |
| `data/system_data.json` | Historical scan and alert log (used by the dashboard) |

---

## Project Structure

```
.
├── main.py               # Entry point and configuration
├── alert_system.py       # Orchestrates prep and scan; AlertConfig dataclass
├── data_provider.py      # Alpaca, WRDS, and yfinance data fetching
├── analyzer.py           # Threshold calculation and scoring logic
├── alert_manager.py      # Email formatting and delivery
├── daily_stats.py        # Scan statistics persistence
├── dashboard.py          # Streamlit dashboard (run separately)
├── valuation_agent.py    # Gemini AI valuation context (currently disabled)
├── requirements.txt      # Python dependencies
└── .env                  # Credentials (not committed)
```
