import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

class DailyStats:
    '''
    Daily scan statistics
    '''
    def __init__(self):
        self.data = []
    
    def save_stats(self, file):
        '''
        Saves daily stats to a json file
        Parameters:
            file: File to save to (str)
        Returns:
            None
        '''

        # Check if there is stats
        today = datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d')
        if not self.data:
            print(f'Daily statistics are missing for {today}.')
            return

        os.makedirs(os.path.dirname(file), exist_ok = True)

        # Read existing data
        existing_stats = {}
        if os.path.exists(file):
            try:   
                with open(file, 'r') as f:
                    existing_stats = json.load(f)
            except Exception as e:
                print(f'Error opening file: {file}. Starting with a blank file.')

        # Ensure today is not already in the file then add stats
        if today in existing_stats:
            existing_stats[today].extend(self.data)
        else:  
            existing_stats[today] = self.data

        # Cache
        with open(file, 'w') as f:
            json.dump(existing_stats, f, indent = 4)

        print(f'Successfully saved daily statistics for {today}.')

