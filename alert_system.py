from alpaca_data_provider import DataProvider
from analyzer import Analyzer
from alert_manager import AlertManager

from datetime import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo
import time

@dataclass
class AlertConfig:

    # File configs
    prices_cache_file: str
    volatilities_cache_file : str
    returns_thresholds_file: str

    # Keys
    api_key: str
    secret_key: str

    # Data configs
    min_market_cap: int
    lookback_years: int

    # Analysis configs
    drop_percentile: float
    drop_percent: float

    # Email configs
    sender_email: str
    sender_password: str
    to_emails: str
    

class AlertSystem:
    def __init__(self, config: AlertConfig):

        self.config = config

        # Save parameters
        self.volatilities_cache_file = config.volatilities_cache_file
        self.returns_thresholds_file = config.returns_thresholds_file
        self.drop_percentile = config.drop_percentile
        self.drop_percent = config.drop_percent

        # Initialize classes
        self.data = DataProvider(
            prices_cache_file = config.prices_cache_file, 
            api_key = config.api_key, 
            secret_key = config.secret_key, 
            min_market_cap = config.min_market_cap, 
            lookback_years = config.lookback_years
            )
        
        self.analyzer = None

        self.alert_manager = AlertManager(
            sender_email = config.sender_email, 
            sender_password = config.sender_password, 
            to_emails = config.to_emails
            )

    def prep_system(self):
        '''
        Fetches and caches historical prices and calculates and stores thresholds
        Parameters: 
            None
        Returns:
            None
        '''
        try: 
            # Fetch the universe and update/initialize prices data
            self.data.get_universe()
            self.data.update_prices_data()
            self.data.load_prices_data()

            # Initialize analyzer and calculate thresholds
            self.analyzer = Analyzer(
                volatilities_cache_file = self.volatilities_cache_file, 
                returns_thresholds_file = self.returns_thresholds_file, 
                price_data = self.data.prices_df, 
                drop_percentile = self.drop_percentile, 
                drop_percentage = self.drop_percent
                )
            self.analyzer.calculate_returns_thresholds()

        except Exception as e:
            print(f'Error occurred: {e}')

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
            # Initialize analyzer
            self.analyzer = Analyzer(
                volatilities_cache_file = self.volatilities_cache_file, 
                returns_thresholds_file = self.returns_thresholds_file, 
                price_data = None,
                drop_percentile = self.drop_percentile, 
                drop_percentage = self.drop_percent
                )
            
            # Load thresholds
            self.analyzer.load_returns_thresholds()

            # Define tickers
            tickers = list(self.analyzer.returns_thresholds.keys())

            # Check if tickers is populated
            if not tickers:
                print('No tickers found.')
                return

            # While the market is open
            while self.is_market_open():
                now = datetime.now(ZoneInfo('America/New_York'))
                print(f"[{now.strftime('%H:%M:%S')}] Market Open: Scanning {len(tickers)} tickers...")
                
                # Execute scan
                live_df = self.data.fetch_live_data(tickers)
                drops_df = self.analyzer.find_drops(live_df)
                self.alert_manager.process_alerts(drops_df)
                
                # Add delay
                time.sleep(60) 
            
            now = datetime.now(ZoneInfo('America/New_York'))

            # Run prep at market close
            if now.hour >= 16:
                print(f"[{now.strftime('%H:%M:%S')}] Market now closed. Running daily prep...")
                self.prep_system()
            else:
                print(f"[{now.strftime('%H:%M:%S')}] Market is not open.")

        except Exception as e:
            print(f'Error during live scan: {e}')

    def is_market_open(self):
        '''
        Helper function to determine if the market is open
        Parameters:
            None
        Return:
            Is the market open (boolean)
        '''
        curr = datetime.now(ZoneInfo('America/New_York'))
        return (curr.weekday() < 5) and (
            (curr.hour == 9 and curr.minute >= 30) or (10 <= curr.hour < 16)
        )