from alert_system import AlertSystem, AlertConfig

import pandas as pd
import os
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import lseg.data as ld

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
        cache_file = 'data/historical_prices.parquet',
        thresholds_file = 'data/thresholds.json',
        alert_log_file = 'data/alert_log.json', 
        instrument_blacklist = 'BONDFUT,BONDSPREAD,CEF,ETF,ETFA,ETFB,ETFC,ETFE,ETFM,ETFO,ETFX,ETMF,GROWUNT,HDG,INS,OPF,OPTRTS,PAIDSUBRTS,PREFERRED,PRF,RTS,SUBSRTS',
        min_market_cap = 10_000_000_000,
        lookback_years = 1,
        drop_percentile = 0.0015,
        drop_percent = 0.20,
        sender_email = os.getenv('SENDER_EMAIL'),
        sender_password = os.getenv('SENDER_PASSWORD'),
        to_emails =  to_emails,
    )

    # Initialize data session
    session = ld.session.platform.Definition(
        app_key = os.getenv('LSEG_APP_KEY'), 
        grant = ld.session.platform.GrantPassword(
            username = os.getenv('LSEG_USER_ID') ,
            password = os.getenv('LSEG_PASSWORD')
        )
    ).get_session()
    ld.session.set_default(session)

    # Initialize the system
    alert_system = AlertSystem(settings)

    # Choose to prep or scan
    parser = argparse.ArgumentParser(description= 'SPUR Alert System')
    parser.add_argument('--mode', choices = ['prep', 'scan'], required = True)
    args = parser.parse_args()

    try:
        # Open data session
        session.open()
        print('Session Opened.')

        # Execute prep procedure
        if args.mode == 'prep':
            print('=== Initiating Prep ===')
            alert_system.prep_system()
        
        # Execute scan procedure
        elif args.mode == 'scan':

            print('=== Initiating Scan ===')
            now = datetime.now(ZoneInfo('America/New_York'))

            # Check if the market is open 
            if now.weekday() >= 5 or (now.hour < 9 or (now.hour == 9 and now.minute < 30)):
                print(f"[{now.strftime('%H:%M:%S')}] The market is not opened. Closing program.")
                return

            # End scan on market close and run prep for the next day
            if now.hour >= 16:
                print(f"[{now.strftime('%H:%M:%S')}] The market is now closed. Running prep...")
                alert_system.prep_system()
                return
            
            # Execute scan
            alert_system.run_system()
    
    except Exception as e:
        print(f'Error: {e}')

    finally:
        # Close data session
        session.close()
        print('Session Closed.')

if __name__ == '__main__':
    main()