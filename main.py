from alert_system import AlertSystem, AlertConfig

import pandas as pd
import os
import argparse
import time
import datetime
from zoneinfo import ZoneInfo

def main():
    pd.set_option('future.no_silent_downcasting', True)

    # Config settings
    settings = AlertConfig(
        cache_file = 'data/historical_prices.parquet',
        thresholds_file = 'data/thresholds.json',
        instrument_blacklist = '''
        BONDFUT,BONDSPREAD,CEF,ETF,ETFA,ETFB,ETFC,ETFE,ETFM,ETFO,ETFX,ETMF,
        FU&N,GROWUNT,HDG,INS,OPF,OPTRTS,PAIDSUBRTS,PREFERRED,PRF,RTS,SUBSRTS
        ''',
        min_market_cap = 5_000_000_000,
        lookback_years = 1,
        drop_percentile = 0.0015,
        drop_percent = 0.20,
        sender_email = os.getenv('SENDER_EMAIL'),
        sender_password = os.getenv('SENDER_PASSWORD'),
        to_email =  os.getenv('TO_EMAIL'),
    )

    # Initialize the system
    alert_system = AlertSystem(settings)

    # Choose to prep or scan
    parser = argparse.ArgumentParser(description= 'SPUR Alert System')
    parser.add_argument('--mode', choices = ['prep', 'scan'], required = True)
    args = parser.parse_args()

    # Execute prep procedure
    if args.mode == 'prep':
        print('=== Initiating End-of-Day Batch Prep ===')
        alert_system.prep_system()
    
    # Execute scan procedure
    elif args.mode == 'scan':

        print('=== Initiating Intraday Live Scanner ===')

        while True:
            now = datetime.now(ZoneInfo('America/New_York'))

            # End scan on market hours
            if now.hour >= 16:
                print(f"[{now.strftime('%H:%M:%S')}] Market closed. Shutting down scanner.")
                break
            
            # Execute scan
            alert_system.run_system()

            # Delay
            time.sleep(3600)

if __name__ == "__main__":
    main()