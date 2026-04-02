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
        returns_thresholds_file = 'data/returns_thresholds.json',
        volatilities_thresholds_file = 'data/volatilities_thresholds.json',
        stats_cache_file = 'data/system_data.json',
        data_api_key = os.getenv('ALPACA_API_KEY'),
        data_secret_key = os.getenv('ALPACA_SECRET_KEY'),
        ai_api_key = os.getenv('GEMINI_API_KEY'),
        min_market_cap = 10_000_000_000,
        lookback_years = 1,
        volatility_rolling_window = 21,
        drop_percentile = 0.0015,
        drop_percent = 0.10,
        volatility_percentile = 0.8,
        temperature = 0.1,
        prompt = '''
        For EACH ticker, use Google Search to find the most recent financial data and news and provide an answer to the following questions:
        1. Is the ticker cheap compared to itself historically?
        2. Is the ticker cheap compared to analyst price targets?
        3. Is the ticker cheap compared to other stocks in the same industry?
        4. Are the issues that led to this ticker being undervalued fixable?
        ''',
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