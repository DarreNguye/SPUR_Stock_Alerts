from data_provider import DataProvider
from analyzer import Analyzer
from alert_manager import AlertManager
from daily_stats import DailyStats
from valuation_agent import ValuationAgent

from datetime import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo
import time
import pandas as pd
import pandas_market_calendars as mcal

@dataclass
class AlertConfig:

    # Keys
    db_user: str
    db_pass: str
    data_api_key: str
    data_secret_key: str
    ai_api_key: str

    # Data configs
    min_market_cap: int
    lookback_years: int
    volatility_rolling_window: int

    # Score config
    req_score: int

    # Universe configs
    pe_percentile: float
    analyst_discount: float

    # Analysis configs
    drop_percentile: float
    drop_percent: float
    volatility_percentile: float

    # Valuation configs
    temperature: float
    prompt: str

    # Email configs
    sender_email: str
    sender_password: str
    to_emails: str
    

class AlertSystem:
    def __init__(self, config: AlertConfig):

        # Save settings
        self.config = config

        # Initialize classes
        self.data = DataProvider(
            pe_percentile = config.pe_percentile,
            analyst_discount = config.analyst_discount,
            req_score = config.req_score,
            db_user = config.db_user,
            db_pass = config.db_pass,
            api_key = config.data_api_key, 
            secret_key = config.data_secret_key, 
            min_market_cap = config.min_market_cap, 
            lookback_years = config.lookback_years
            )
    
    def monthly_prep_system(self):
        '''
        Creates universe data
        Parameters: 
            None
        Returns:
            None
        '''
        try: 
            # Rewrite the universe
            self.data.universe_df = None  
            self.data.clear_universe()
            self.data.get_universe()

            # Run daily prep on the new universe
            print('Universe updated. Running daily prep...')
            self.daily_prep_system()

        except Exception as e:
            print(f'Error during monthly prep: {e}')

    def daily_prep_system(self):
        '''
        Fetches and caches returns and IVs and calculates and stores thresholds
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

            # Initialize components
            analyzer = Analyzer(
                price_data = self.data.prices_df, 
                drop_percentile = self.config.drop_percentile, 
                drop_percentage = self.config.drop_percent,
                volatility_percentile = self.config.volatility_percentile,
                volatility_rolling_window = self.config.volatility_rolling_window
                )
            analyzer.calculate_returns_thresholds()
            analyzer.calculate_volatilities_thresholds()

        except Exception as e:
            print(f'Error during daily prep: {e}')

    def run_system(self):
        '''
        Alerts any tickers that drop below set thresholds
        Parameters:
            None
        Return:
            None
        '''
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting live market scan...")

        try:

            # Check if the market is open
            now = datetime.now(ZoneInfo('America/New_York'))
            calendar = mcal.get_calendar('NYSE')
            if not self.is_market_open(calendar):
                print(f"[{now.strftime('%H:%M:%S')}] Market is not open.")
                return

            # Load prices data
            self.data.load_prices_data()

            # Initialize components
            analyzer = Analyzer(
                price_data = self.data.prices_df,
                drop_percentile = self.config.drop_percentile, 
                drop_percentage = self.config.drop_percent,
                volatility_percentile = self.config.volatility_percentile,
                volatility_rolling_window = self.config.volatility_rolling_window
                )
            
            self.alert_manager = AlertManager(
                sender_email = self.config.sender_email, 
                sender_password = self.config.sender_password, 
                to_emails = self.config.to_emails
                )
            
            daily_stats = DailyStats(self.config)
            valuation_agent = ValuationAgent(self.config.ai_api_key)
            
            # Load thresholds
            analyzer.load_returns_thresholds()
            analyzer.load_volatilities_thresholds()

            # Define tickers
            tickers = list(analyzer.returns_thresholds.keys())

            # Check if tickers is populated
            if not tickers:
                print('No tickers found.')
                return
            
            # Store already alerted tickers
            old_alerts = []

            # While the market is open
            while self.is_market_open(calendar):
                now = datetime.now(ZoneInfo('America/New_York'))
                print(f"[{now.strftime('%H:%M:%S')}] Market Open: Scanning {len(tickers)} tickers...")
                
                # Fetch live prices
                live_prices_df = self.data.fetch_live_prices(tickers)

                # Check for returns drops
                drops_df = analyzer.find_drops(live_prices_df)
                
                # Fetch IV
                implied_volatilities_df = self.data.fetch_live_volatilites(drops_df)

                # Check for high IV
                high_iv_df = analyzer.find_high_iv(implied_volatilities_df)

                # Filter for new alerts
                new_alerts_df = self.filter_new_alerts(high_iv_df, old_alerts)

                # Add in valuation analysis
                enriched_df = valuation_agent.analyze_tickers(self.config.prompt, self.config.temperature, new_alerts_df)
                
                # Send alerts
                self.alert_manager.process_alerts(enriched_df)

                # Update stats if there is meaningful information
                if not drops_df.empty or not high_iv_df.empty or not new_alerts_df.empty:
                    daily_stats.data.append({
                        'Time': now.strftime('%Y-%m-%d %H:%M:%S'),
                        'Drop_Tickers': drops_df['Ticker'].tolist() if not drops_df.empty else [],
                        'High_IV_Tickers': high_iv_df['Ticker'].tolist() if not high_iv_df.empty else [],
                        'Alerts': enriched_df.to_dict(orient='records') if not new_alerts_df.empty else []
                    })
                
                # Add delay
                time.sleep(60) 
            
            now = datetime.now(ZoneInfo('America/New_York'))

            # Save statistics and run prep at market close
            if now.hour >= 16:
                print(f"[{now.strftime('%H:%M:%S')}] Market now closed. Running cleanup...")
                daily_stats.save_stats(len(tickers))
                self.daily_prep_system()
            else:
                print(f"[{now.strftime('%H:%M:%S')}] Market is not open.")

        except Exception as e:
            print(f'Error during live scan: {e}')

    def is_market_open(self, calendar):
        '''
        Helper function to determine if the market is open
        Parameters:
            None
        Return:
            Is the market open (boolean)
        '''
        curr = datetime.now(ZoneInfo('America/New_York'))
        schedule = calendar.schedule(
            start_date=curr.strftime('%Y-%m-%d'),
            end_date=curr.strftime('%Y-%m-%d')
        )
        if schedule.empty:
            return False
        market_open = schedule.iloc[0]['market_open'].to_pydatetime()
        market_close = schedule.iloc[0]['market_close'].to_pydatetime()
        return market_open <= curr <= market_close
    
    def filter_new_alerts(self, alerts_in, old_alerts):
        '''
        Helper function to filter for only new alerts
        Parameters:
            alerts_in: Alerts to be filtered (pandas.DataFrame)
            old_alerts: Tickers already alerted (list of str)
        Return:
            New alerts (pandas.DataFrame)
        '''

        # Check if there are alerts in
        if alerts_in.empty:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan complete: No tickers detected.")
            return pd.DataFrame()
                
        # Filter for new alerts
        new_alerts_df = alerts_in[~alerts_in['Ticker'].isin(old_alerts)]

        # Update old alerts or 
        if not new_alerts_df.empty:
            old_alerts.extend(new_alerts_df['Ticker'].tolist())
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan complete: Tickers detected, but already alerted today.")

        return new_alerts_df