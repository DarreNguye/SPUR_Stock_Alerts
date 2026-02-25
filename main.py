from data import Data
from analyzer import Analyzer
from alert_manager import AlertManager
from tqdm import tqdm
import lseg.data as ld
import pandas as pd

class AlertSystem:
    def __init__(self, cache_file, min_market_cap, lookback_years, drop_percentile, drop_percent):
        self.data = Data(cache_file, min_market_cap, lookback_years)
        self.analyzer = Analyzer(self.data, drop_percentile, drop_percent)
        self.alert_manager = AlertManager()

    def run_scan(self):
        pass

if __name__ == "__main__":

    # Settings
    CACHE_FILE = 'data/historical_prices.parquet'
    MIN_MARKET_CAP = 5_000_000_000
    LOOKBACK_YEARS = 1
    DROP_PERCENTILE = 0.0015
    DROP_PERCENT = 0.20

    # Handle Warnings
    pd.set_option('future.no_silent_downcasting', True)
    
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