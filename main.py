from data_provider import DataProvider
from analyzer import Analyzer
from alert_manager import AlertManager

from tqdm import tqdm
import lseg.data as ld
import pandas as pd
from datetime import datetime

class AlertSystem:
    def __init__(self, cache_file, thresholds_file, instrument_blacklist, min_market_cap, lookback_years, drop_percentile, drop_percent):

        # Save parameters
        self.thresholds_file = thresholds_file
        self.drop_percentile = drop_percentile
        self.drop_percent = drop_percent

        # Initialize classes
        self.data = DataProvider(cache_file, instrument_blacklist, min_market_cap, lookback_years)
        self.analyzer = None
        self.alert_manager = AlertManager()

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

    # Files
    CACHE_FILE = 'data/historical_prices.parquet'
    THRESHOLDS_FILE = 'data/thresholds.json'

    # Universe Settings
    INSTRUMENT_BLACKLIST = '''
    BONDFUT,BONDSPREAD,CEF,ETF,ETFA,ETFB,ETFC,ETFE,ETFM,ETFO,ETFX,ETMF,
    FU&N,GROWUNT,HDG,INS,OPF,OPTRTS,PAIDSUBRTS,PREFERRED,PRF,RTS,SUBSRTS
    '''
    MIN_MARKET_CAP = 5_000_000_000
    LOOKBACK_YEARS = 1

    # Analysis Settings
    DROP_PERCENTILE = 0.0015
    DROP_PERCENT = 0.20

    # Handle Warnings
    pd.set_option('future.no_silent_downcasting', True)
    
    # Initialize the alert system
    alert_system = AlertSystem(CACHE_FILE, THRESHOLDS_FILE, INSTRUMENT_BLACKLIST, MIN_MARKET_CAP, LOOKBACK_YEARS, DROP_PERCENTILE, DROP_PERCENT)
    # alert_system.prep_system()
    alert_system.run_system()