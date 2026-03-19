import pandas as pd
import os
import json
import numpy as np

class Analyzer:
    '''
    Ticker analysis class
    '''

    def __init__(self, returns_thresholds_file, volatilities_thresholds_file, price_data, drop_percentile, drop_percentage, volatility_percentile, volatility_rolling_window):
        self.returns_thresholds_file = returns_thresholds_file
        self.volatilities_thresholds_file = volatilities_thresholds_file

        self.price_data = price_data
        self.drop_percentile = drop_percentile
        self.drop_percentage = drop_percentage
        self.volatility_percentile = volatility_percentile
        self.volatility_rolling_window = volatility_rolling_window

        self.returns_thresholds = {}
        self.volatilities_thresholds = None
    
    def calculate_returns_thresholds(self):
        '''
        Calculates and saves the bottom percentile for every ticker
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
        Loads returns thresholds from a json file
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
            print('Returns thresholds file not found. Calculating thresholds...')
            self.calculate_returns_thresholds()
            return
            
        # Load thresholds from file
        with open(self.returns_thresholds_file, 'r') as f:
            self.returns_thresholds = json.load(f)
        print(f'Loaded {len(self.returns_thresholds)} thresholds into memory.')
    
    def find_drops(self, live_prices_df):
        '''
        Calculate live returns and compare with threshold
        Parameters:
            live_prices_df: Ticker, Live_Price, Prev_Close (pandas.DataFrame)
        Return:
            Tickers that are below the threshold (pandas.DataFrame)
        '''

        # Check if live_df has data
        if live_prices_df is None or live_prices_df.empty:
            print('No live prices available.')
            return pd.DataFrame()
        
        # Check if price_data has data
        if self.price_data is None or self.price_data.empty:
            print('No historical prices available.')
            return pd.DataFrame()
        
        # Get previous closes
        prev_closes = self.price_data.groupby('Ticker')['Close'].last()
        live_prices_df['Prev_Close'] = live_prices_df['Ticker'].map(prev_closes)
        live_prices_df.dropna(subset=['Prev_Close'], inplace=True)

        # Calculate live returns
        live_prices_df['Live_Return'] = (live_prices_df['Live_Price'] - live_prices_df['Prev_Close']) / live_prices_df['Prev_Close']
        live_prices_df['Returns_Threshold'] = live_prices_df['Ticker'].map(self.returns_thresholds).fillna(-self.drop_percentage)

        # Filter for tickers based on set conditions
        drops_df = live_prices_df[
            (live_prices_df['Live_Return'] <= live_prices_df['Returns_Threshold']) & 
            (live_prices_df['Live_Return'] <= -self.drop_percentage)
        ].copy()

        print(f'Identified {len(drops_df)} drops.')
        return drops_df
    
    def calculate_historical_volatilities(self, volatility_rolling_window):
        '''
        Calculates rolling historical volatility
        Parameters:
            rolling_window: Period of historical prices to use to calculate volatility (int)
        Return:
            Historical volatilities (pandas.DataFrame)
        '''
        
        # Check if there is historical price data
        if self.price_data is None or self.price_data.empty:
            print('No historical prices available to calculate volatilities.')
            return
        
        print(f'Calculating historical volatilities...')
        volatilities_df = self.price_data.copy()

        # Sort by ticker and date
        volatilities_df.sort_values(by = ['Ticker', 'Date'], inplace = True)

        # Calculate historical volatility
        volatilities_df['Log_Return'] = np.log(volatilities_df['Close'] / volatilities_df.groupby('Ticker')['Close'].shift(1))
        volatilities_df['Historical_Volatility'] = (
            volatilities_df.groupby('Ticker')['Log_Return']
            .rolling(window = volatility_rolling_window)
            .std()
            .reset_index(level = 0, drop = True) * np.sqrt(252)
        )

        # Format
        volatilities_df.dropna(subset = ['Historical_Volatility'], inplace = True)
        volatilities_df = volatilities_df[['Ticker', 'Date', 'Historical_Volatility']]

        print(f'Successfully calculated volatilities.')
        return volatilities_df
    
    def calculate_volatilities_thresholds(self):
        '''
        Calculates and saves the top volatility percentile for every ticker
        Parameters:
            None
        Return:
            None
        '''
       
        # Calculate historical volatilities
        volatilities_df = self.calculate_historical_volatilities(self.volatility_rolling_window)
        if volatilities_df is None or volatilities_df.empty:
            print('Volatilities could not be calculated.')
            return 

        print(f'Calculating {self.volatility_percentile} percentile thresholds...')

        # Calculate thresholds
        thresholds = volatilities_df.groupby('Ticker')['Historical_Volatility'].quantile(self.volatility_percentile).dropna().to_dict()

        # Save thresholds
        os.makedirs(os.path.dirname(self.volatilities_thresholds_file), exist_ok = True)
        with open(self.volatilities_thresholds_file, 'w') as f:
            json.dump(thresholds, f, indent = 4)
        
        # Set thresholds
        self.volatilities_thresholds = thresholds
        print(f'Successfully saved {len(self.volatilities_thresholds)} thresholds to {self.volatilities_thresholds_file}.')

    def load_volatilities_thresholds(self):
        '''
        Loads volatilities thresholds from a json file
        Parameters:
            None
        Return:
            None
        '''

        # Check if thresholds is already populated
        if self.volatilities_thresholds:
            return

        # Calculate thresholds if the file does not exist
        if not os.path.exists(self.volatilities_thresholds_file):
            print('Volatilities thresholds file not found. Calculating thresholds...')
            self.calculate_volatilities_thresholds()
            return
        
        # Load thresholds from file
        with open(self.volatilities_thresholds_file, 'r') as f:
            self.volatilities_thresholds = json.load(f)
        print(f'Loaded {len(self.volatilities_thresholds)} thresholds into memory.')

    def find_high_iv(self, drops_df):
        '''
        Compare live implied volatility with threshold
        Parameters:
            drops_df: Data including Ticker, Volatility Threshold, Implied Volatility (pandas.DataFrame)
        Return:
            Tickers that are above the threshold (pandas.DataFrame)
        '''

        # Check if live_df has data
        if drops_df is None or drops_df.empty:
            return pd.DataFrame()

        # Map thresholds
        drops_df['Volatility_Threshold'] = drops_df['Ticker'].map(self.volatilities_thresholds)

        # Drop NaN
        drops_df.dropna(subset = ['Volatility_Threshold', 'Implied_Volatility'], inplace = True)

        # Filter for tickers based on set conditions
        high_iv_df = drops_df[drops_df['Implied_Volatility'] >= drops_df['Volatility_Threshold']].copy()

        print(f'Identified {len(high_iv_df)} high IVs.')
        return high_iv_df


