from data_provider import DataProvider
from analyzer import Analyzer
from alert_manager import AlertManager

import lseg.data as ld
import pandas as pd
from datetime import datetime
import os

from dataclasses import dataclass

@dataclass
class AlertConfig:

    # File configs
    cache_file: str
    thresholds_file: str

    # Data configs
    instrument_blacklist: str
    min_market_cap: int
    lookback_years: int

    # Analysis configs
    drop_percentile: float
    drop_percent: float

    # Email configs
    sender_email: str
    sender_password: str
    to_email: str
    

class AlertSystem:
    def __init__(self, config: AlertConfig):

        self.config = config

        # Save parameters
        self.thresholds_file = config.thresholds_file
        self.drop_percentile = config.drop_percentile
        self.drop_percent = config.drop_percent

        # Initialize classes
        self.data = DataProvider(config.cache_file, config.instrument_blacklist, config.min_market_cap, config.lookback_years)
        self.analyzer = None
        self.alert_manager = AlertManager(config.sender_email, config.sender_password, config.to_email)

    def prep_system(self):
        '''
        Fetches and caches historical data and calculates and stores thresholds
        Parameters: 
            None
        Returns:
            None
        '''
        try: 
            # Connect to data provider
            ld.open_session()
            print('Session Opened.')

            # Fetch the universe and update/initialize historical data
            self.data.get_universe()
            self.data.update_historical_data()
            self.data.load_historical_data()

            # Initialize analyzer and calculate thresholds
            self.analyzer = Analyzer(self.thresholds_file, self.data.historical_df, self.drop_percentile, self.drop_percent)
            self.analyzer.calculate_thresholds()

        except Exception as e:
            print(f'Error occurred: {e}')

        finally:
            # Close connection to data provider
            ld.close_session()
            print('Session Closed.')

    def run_system(self):
        '''
        Alerts any tickers that drop below set thresholds
        Parameters:
            None
        Return:
            None
        '''
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting live market scan...")

        try:
            # Connect to data provider
            ld.open_session()
            print('Session Opened.')

            # Initialize analyzer
            if self.analyzer is None:
                self.analyzer = Analyzer(
                        self.thresholds_file, 
                        None, 
                        self.drop_percentile, 
                        self.drop_percent
                )
            
            # Load thresholds
            self.analyzer.load_thresholds()

            # Define tickers
            tickers = list(self.analyzer.thresholds.keys())

            # Check if tickers is populated
            if not tickers:
                print('No tickers found.')
                return

            # Get live prices
            live_df = self.data.fetch_live_data(tickers)
            
            # Filter for tickers that are below the set thresholds
            drops_df = self.analyzer.find_drops(live_df)
            
            # Alert user
            self.alert_manager.process_alerts(drops_df)

        except Exception as e:
            print(f'Error during live scan: {e}')
            
        finally:
            # Close connection to data provider
            ld.close_session()
            print('Session Closed.')

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