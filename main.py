from data import Data
from analyzer import Analyzer
from alert_manager import AlertManager
from tqdm import tqdm
import lseg.data as ld
import pandas as pd

class AlertSystem:
    def __init__(self, cache_file):
        self.data = Data(cache_file)
        self.analyzer = Analyzer(self.data)
        self.alert_manager = AlertManager()

    def run_scan(self):
        # Get universe
        
        # Iterate across universe
        for ticker in universe:
            try:
                # Check if the stock satisfies the condition
                if not self.ta.check_price_drop_condition(ticker):

                    # Send an alert
                    continue

                
            except Exception as e:
                # Log error and continue to next ticker
                pass

if __name__ == "__main__":

    pd.set_option('future.no_silent_downcasting', True)

    # Settings
    CACHE_FILE = 'data/historical_prices.parquet'
    MIN_MARKET_CAP = 5_000_000_000
    LOOKBACK_YEARS = 1
    
    # alert_system = AlertSystem(CACHE_FILE)

    try: 
        ld.open_session()
        print('Session Opened.')

        data = Data(CACHE_FILE, MIN_MARKET_CAP, LOOKBACK_YEARS)
        data.get_universe()
        data.get_historical_data()

    except Exception as e:
        print(f'Error occurred: {e}')

    finally:
        ld.close_session()
        print('Session Closed.')