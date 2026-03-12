from alert_system import AlertSystem, AlertConfig

import pandas as pd
import os
import argparse
from dotenv import load_dotenv

def main():
    pd.set_option('future.no_silent_downcasting', True)

    # Load env variables
    load_dotenv()

    # Grab emails
    raw_emails = os.getenv('TO_EMAILS')
    if raw_emails:
        to_emails = raw_emails.split(',')
    else:
        to_emails = []

    # Config settings
    settings = AlertConfig(
        prices_cache_file = 'data/historical_prices.parquet',
        volatilities_cache_file = 'data/historical_volatility.parquet',
        returns_thresholds_file = 'data/thresholds.json',
        api_key = os.getenv('ALPACA_API_KEY'),
        secret_key = os.getenv('ALPACA_SECRET_KEY'),
        min_market_cap = 10_000_000_000,
        lookback_years = 1,
        drop_percentile = 0.0015,
        drop_percent = 0.20,
        sender_email = os.getenv('SENDER_EMAIL'),
        sender_password = os.getenv('SENDER_PASSWORD'),
        to_emails = to_emails,
    )

    # Initialize the system
    alert_system = AlertSystem(settings)

    # Choose to prep or scan
    parser = argparse.ArgumentParser(description= 'SPUR Alert System')
    parser.add_argument('--mode', choices = ['prep', 'scan'], required = True)
    args = parser.parse_args()

    # Execute prep procedure
    if args.mode == 'prep':
        print('=== Initiating Prep ===')
        alert_system.prep_system()
        print('=== Finished Prep ===')
    
    # Execute scan procedure
    elif args.mode == 'scan':
        print('=== Initiating Scan ===')
        alert_system.run_system()
        print('=== Finished Scan ===')

if __name__ == '__main__':
    main()