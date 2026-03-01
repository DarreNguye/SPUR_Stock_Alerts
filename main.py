from alert_system import AlertSystem, AlertConfig

import pandas as pd
import os

if __name__ == "__main__":

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

    # Handle Warnings
    pd.set_option('future.no_silent_downcasting', True)
    
    # Initialize the alert system
    alert_system = AlertSystem(settings)

    # Run at the end of the day
    # alert_system.prep_system()

    # Run during market hours
    # alert_system.run_system()