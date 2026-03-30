import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

class DailyStats:
    '''
    Daily scan statistics class
    '''
    def __init__(self, config):
        self.config = config
        self.data = []
    
    def save_stats(self, universe_count):
        '''
        Saves daily stats to a json file
        Parameters:
            universe_count: number of tickers in the universe (int)
        Returns:
            None
        '''

        # Check if there is stats
        today = datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d')
        if not self.data:
            print(f'Daily statistics are missing for {today}.')
            return

        os.makedirs(os.path.dirname(self.config.stats_cache_file), exist_ok = True)

        # Read existing data
        existing_stats = {}
        if os.path.exists(self.config.stats_cache_file):
                with open(self.config.stats_cache_file, 'r') as f:
                    existing_stats = json.load(f)

        # Check if today is in the existing data
        if today not in existing_stats:
            existing_stats[today] = {
                'Metadata': { 
                    'Min_Market_Cap': self.config.min_market_cap,
                    'Universe_Count': universe_count,
                    'Drop_Percent': self.config.drop_percent,
                    'Drop_Percentile': self.config.drop_percentile,
                    'Volatility_Percentile': self.config.volatility_percentile,
                    'Volatility_Window': self.config.volatility_rolling_window,
                },
                'Scans': []
            }

        # Append data from today
        existing_stats[today]['Scans'].extend(self.data)

        # Cache
        with open(self.config.stats_cache_file, 'w') as f:
            json.dump(existing_stats, f, indent = 4)

        print(f'Successfully saved daily statistics for {today}.')

