from data_provider import DataProvider
from analyzer import Analyzer
from alert_manager import AlertManager
from tqdm import tqdm
import lseg.data as ld
import pandas as pd

class AlertSystem:
    def __init__(self, cache_file, thresholds_file, min_market_cap, lookback_years, drop_percentile, drop_percent):
        self.data = DataProvider(cache_file, min_market_cap, lookback_years)
        self.analyzer = Analyzer(thresholds_file, self.data.historical_df, drop_percentile, drop_percent)
        self.alert_manager = AlertManager()

    def run_scan(self):
        pass

if __name__ == "__main__":

    # Settings
    CACHE_FILE = 'data/historical_prices.parquet'
    THRESHOLDS_FILE = 'data/thresholds.json'
    INSTRUMENT_BLACKLIST = '''
    BONDFUT,BONDSPREAD,CEF,ETF,ETFA,ETFB,ETFC,ETFE,ETFM,ETFO,ETFX,ETMF,
    FU&N,GROWUNT,HDG,INS,OPF,OPTRTS,PAIDSUBRTS,PREFERRED,PRF,RTS,SUBSRTS
    '''
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

        # Initialize the Data Provider
        data = DataProvider(CACHE_FILE, INSTRUMENT_BLACKLIST, MIN_MARKET_CAP, LOOKBACK_YEARS)
        data.get_universe()
        data.update_historical_data()
        data.load_historical_data()

        # Initialize the Analyzer
        analyzer = Analyzer(THRESHOLDS_FILE, data.historical_df, DROP_PERCENTILE, DROP_PERCENT)
        analyzer.calculate_thresholds()

    except Exception as e:
        print(f'Error occurred: {e}')

    finally:
        ld.close_session()
        print('Session Closed.')