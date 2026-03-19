import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

class DailyStats:
    '''
    Daily scan statistics class
    '''
    def __init__(self):
        self.data = []
    
    def save_stats(self, file_name):
        '''
        Saves daily stats to a json file
        Parameters:
            file_name: File to save to (str)
        Returns:
            None
        '''

        # Check if there is stats
        today = datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d')
        if not self.data:
            print(f'Daily statistics are missing for {today}.')
            return

        os.makedirs(os.path.dirname(file_name), exist_ok = True)

        # Read existing data
        existing_stats = {}
        if os.path.exists(file_name):
                with open(file_name, 'r') as f:
                    existing_stats = json.load(f)

        # Ensure today is not already in the file then add stats
        if today in existing_stats:
            existing_stats[today].extend(self.data)
        else:  
            existing_stats[today] = self.data

        # Cache
        with open(file_name, 'w') as f:
            json.dump(existing_stats, f, indent = 4)

        print(f'Successfully saved daily statistics for {today}.')

