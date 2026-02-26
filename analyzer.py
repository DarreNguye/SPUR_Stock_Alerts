import pandas as pd
import os
import json

class Analyzer:
    '''
    Ticker analysis class
    '''


    def __init__(self, thresholds_file, data, drop_percentile, drop_percentage):
        self.thresholds_file = thresholds_file
        self.data = data
        self.drop_percentile = drop_percentile
        self.drop_percentage = drop_percentage
        self.thresholds = {}
    
    def calculate_thresholds(self):
        '''
        Calculates and saves the 0.0015 percentile drop for every ticker
        Parameters:
            None
        Return:
            None
        '''
       
       # Check if there is data
        if self.data is None or self.data.empty:
            print('No historical data available to calculate thresholds.')
            return

        print(f'Calculating {self.drop_percentile} percentile thresholds...')
        historical_df = self.data.copy()

        # Sort by ticker and date
        historical_df.sort_values(by = ['Ticker', 'Date'], inplace = True)

        # Calculate thresholds
        historical_df['Return'] = historical_df.groupby('Ticker')['Close'].pct_change()
        thresholds = historical_df.groupby('Ticker')['Return'].quantile(self.drop_percentile).dropna().to_dict()

        # Save thresholds
        os.makedirs(os.path.dirname(self.thresholds_file), exist_ok = True)
        with open(self.thresholds_file, 'w') as f:
            json.dump(thresholds, f, indent = 4)
        
        # Set thresholds
        self.thresholds = thresholds
        print(f'Successfully saved {len(self.thresholds)} thresholds to {self.thresholds_file}.')

    def load_thresholds(self):
        '''
        Loads thresholds from a json file
        Parameters:
            None
        Return:
            None
        '''

        # Check if thresholds is already populated
        if self.thresholds:
            return

        # Calculate thresholds if the file does not exist
        if not os.path.exists(self.thresholds_file):
            print('Thresholds file not found. Calculating thresholds...')
            self.calculate_thresholds()
            return
            
        # Load thresholds from file
        with open(self.thresholds_file, 'r') as f:
            self.thresholds = json.load(f)
        print(f'Loaded {len(self.thresholds)} thresholds into memory.')
    
    def find_drops(self, live_df):
        '''
        Calculate live returns and compare with threshold
        Parameters:
            live_df: Ticker, Live_Price, Prev_Close (pandas.DataFrame)
        Return:
            Stocks that are below the threshold (pandas.DataFrame)
        '''

        # Check if live_df has data
        if live_df is None or live_df.empty:
            return pd.DataFrame()

        # Calculate live returns
        live_df['Live_Return'] = (live_df['Live_Price'] - live_df['Prev_Close']) / live_df['Prev_Close']

        # Map thresholds
        live_df['Percentile_Threshold'] = live_df['Ticker'].map(self.thresholds).fillna(-self.drop_percentage)

        # Filter for tickers based on set conditions
        alerts_df = live_df[
            (live_df['Live_Return'] <= live_df['Percentile_Threshold']) | 
            (live_df['Live_Return'] <= -self.drop_percentage)
        ].copy()

        return alerts_df