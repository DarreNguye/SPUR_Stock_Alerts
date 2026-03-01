# SPUR Stock Alert

A program that connects to the LSEG data provider and alerts the user of significant drops in tickers.

This system operates in two phases:
1. **Prep:** Downloads and caches historical data for a universe, calculating a percentile returns threshold.
2. **Scan:** Sends an email when a ticker drops below its percentile returns threshold or drops a significant amount.

---

## Prerequisites

* **Python 3.9+**
* **LSEG Workspace Desktop** running in the background (or valid Machine ID credentials).
* A **Gmail Account** with an App Password generated for sending SMTP alerts.

---

## Installation

1. Clone or download this repository.
2. Install the required dependencies using `pip`:
   ```bash
   pip install -r requirements.txt

---

## Configurations

Configurations can be made in the `main.py` file within the `AlertConfig` variables:
* `min_market_cap`: The minimum market cap to screen (default: 5,000,000,000).
* `lookback_years`: Years of historical data (default: 1).
* `drop_percentile`: The percentile threshold to trigger an alert (default: 0.0015).
* `drop_percent`: The significant drop in returns to trigger an alert (default: 0.20).

---

## Usage

1. **Prep: (Runs at market close)**
Downloads and caches historical data for a universe, calculating a percentile returns threshold.
```bash
python main.py --mode prep
```


3. **Scan: (Runs during market open)**
Sends an email when a ticker drops below its percentile returns threshold or drops a significant amount.
```bash
python main.py --mode scan
```





