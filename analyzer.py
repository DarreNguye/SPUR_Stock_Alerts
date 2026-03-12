import pandas as pd
import os
import json

class Analyzer:
    '''
    Ticker analysis class
    '''


    def __init__(self, returns_thresholds_file, price_data, drop_percentile, drop_percentage):
        self.returns_thresholds_file = returns_thresholds_file
        self.price_data = price_data
        self.drop_percentile = drop_percentile
        self.drop_percentage = drop_percentage
        self.returns_thresholds = {}
    
    def calculate_returns_thresholds(self):
        '''
        Calculates and saves the 0.0015 percentile drop for every ticker
        Parameters:
            None
        Return:
            None
        '''
       
       # Check if there is data
        if self.price_data is None or self.price_data.empty:
            print('No historical prices available to calculate thresholds.')
            return

        print(f'Calculating {self.drop_percentile} percentile thresholds...')
        prices_df = self.price_data.copy()

        # Sort by ticker and date
        prices_df.sort_values(by = ['Ticker', 'Date'], inplace = True)

        # Calculate thresholds
        prices_df['Return'] = prices_df.groupby('Ticker')['Close'].pct_change()
        thresholds = prices_df.groupby('Ticker')['Return'].quantile(self.drop_percentile).dropna().to_dict()

        # Save thresholds
        os.makedirs(os.path.dirname(self.returns_thresholds_file), exist_ok = True)
        with open(self.returns_thresholds_file, 'w') as f:
            json.dump(thresholds, f, indent = 4)
        
        # Set thresholds
        self.returns_thresholds = thresholds
        print(f'Successfully saved {len(self.returns_thresholds)} thresholds to {self.returns_thresholds_file}.')

    def load_returns_thresholds(self):
        '''
        Loads thresholds from a json file
        Parameters:
            None
        Return:
            None
        '''

        # Check if thresholds is already populated
        if self.returns_thresholds:
            return

        # Calculate thresholds if the file does not exist
        if not os.path.exists(self.returns_thresholds_file):
            print('Thresholds file not found. Calculating thresholds...')
            self.calculate_returns_thresholds()
            return
            
        # Load thresholds from file
        with open(self.returns_thresholds_file, 'r') as f:
            self.returns_thresholds = json.load(f)
        print(f'Loaded {len(self.returns_thresholds)} thresholds into memory.')
    
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
        live_df['Percentile_Threshold'] = live_df['Ticker'].map(self.returns_thresholds).fillna(-self.drop_percentage)

        # Filter for tickers based on set conditions
        alerts_df = live_df[
            (live_df['Live_Return'] <= live_df['Percentile_Threshold']) & 
            (live_df['Live_Return'] <= -self.drop_percentage)
        ].copy()

        return alerts_df
    
    def calculate_rolling_volatility(self, rolling_window):
        '''
        Calculates rolling historical volatility
        Parameters:
            rolling_window: Period of historical prices to use to calculate volatility (int)
        Return:
            None
        '''
        
        # Check if there is historical price data
        if self.price_data is None or self.price_data.empty:
            print('No historical prices available to calculate thresholds.')
            return