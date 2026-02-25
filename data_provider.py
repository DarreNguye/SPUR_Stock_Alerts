import pandas as pd
import lseg.data as ld
from lseg.data.discovery import Screener
import os
from datetime import datetime, timedelta
from tqdm import tqdm

class DataProvider:
    '''
    Data provider class using LSEG API
    '''

    def __init__(self, cache_file, instrument_blacklist, min_market_cap, lookback_years):
        self.cache_file = cache_file
        self.instrument_blacklist = instrument_blacklist
        self.min_market_cap = min_market_cap
        self.lookback_years = lookback_years

        self.universe_df = None
        self.historical_df = None

    def get_universe(self):
        '''
        Fetches a universe of a specified market cap
        Parameters:
            None
        Return:
            Universe data (pandas.DataFrame)
        '''

        try:
            print("Fetching universe data...")

            min_cap_millions = int(self.min_market_cap / 1_000_000)

            # Define conditions for the universe
            universe = Screener(
                f'''
                U(IN(Equity(active,public,primary))/*UNV:Public*/), 
                TR.CompanyMarketCap(Scale=6)>={min_cap_millions}, 
                NOT_IN(TR.InstrumentTypeCode,{self.instrument_blacklist}),
                CURN=USD
                '''
            )

            # Fetch data
            self.universe_df = ld.get_data(universe, fields = ['TR.CommonName'])
            print("Successfuly fetched universe data.")
            return self.universe_df
        
        except Exception as e:
            print(f'Error fetching universe: {e}')
            return pd.DataFrame()
        
    def initialize_historical_data(self):
        '''
        Initializes the cache of historical prices for a universe
        Parameters:
            lookback_years: Years of historical data pulled (int)
        Return:
            None
        '''

        # Check if cache already exists 
        if os.path.exists(self.cache_file):
            print(f'Cache already exists at {self.cache_file}. Skipping cache initialization.')
            return
        
        # Check if the universe is empty
        if self.universe_df is None or self.universe_df.empty:
            print(f'Universe not defined.')
            return
        
        print(f'Fetching and caching {self.lookback_years}-years of historical data for {len(self.universe_df)} tickers...')

        # Calculate historical data time frame
        end_date = datetime.today()
        start_date = end_date - timedelta(days = self.lookback_years * 365)

        # Fetch data
        tickers = self.universe_df['Instrument'].tolist()
        historical_dfs = self.fetch_historical_data(tickers, start_date, end_date)
        
        # Format data for caching
        if not historical_dfs:
            print('Failed to download historical data.')
            return
        formatted_df = self.format_historical_data(historical_dfs)
            
        # Cache data
        os.makedirs(os.path.dirname(self.cache_file), exist_ok = True)
        formatted_df.to_parquet(self.cache_file, engine='pyarrow', index = False)

        # Set historical_df
        self.historical_df = formatted_df

        print(f'Successfully cached historical data with {len(formatted_df)} rows at {self.cache_file}')

    def update_historical_data(self):
        '''
        Updates the cache of historical data with new data
        Parameters:
            None
        Return:
            None
        '''

        # Check if the cache file exists
        if not os.path.exists(self.cache_file):
            print('Cache not found. Starting historical data download...')
            self.initialize_historical_data()
            return
        
        # Check if the universe is empty
        if self.universe_df is None or self.universe_df.empty:
            print('Universe not defined.')
            return

        # Load the existing cache
        history_df = pd.read_parquet(self.cache_file)
        history_df['Date'] = pd.to_datetime(history_df['Date'])
        
        # Identify tickers in cache and new tickers
        cached_tickers = set(history_df['Ticker'].unique())
        current_tickers = set(self.universe_df['Instrument'].tolist())
        
        new_tickers = list(current_tickers - cached_tickers)
        existing_tickers = list(current_tickers & cached_tickers)

        # Calculate dates to pull
        end_date = datetime.today()
        last_cache_date = history_df['Date'].max()
        start_date = end_date - timedelta(days=self.lookback_years * 365)
        
        new_dfs = []

        # Fetch updated data for existing tickers
        if existing_tickers and last_cache_date.date() < end_date.date():
            print(f"Updating {len(existing_tickers)} existing tickers from {last_cache_date.strftime('%Y-%m-%d')}...")
            updated_existing_dfs = self.fetch_historical_data(existing_tickers, last_cache_date, end_date)
            new_dfs.extend(updated_existing_dfs)

        # Fetch full history for new tickers
        if new_tickers:
            print(f'Found {len(new_tickers)} new tickers. Fetching full {self.lookback_years}-year history...')
            new_tickers_dfs = self.fetch_historical_data(new_tickers, start_date, end_date)
            new_dfs.extend(new_tickers_dfs)

        # Format data
        if not new_dfs:
            print('Cache is already up to date. No new data downloaded.')
            return
        formatted_new_df = self.format_historical_data(new_dfs)
        
        # Merge old and new data
        updated_df = pd.concat([history_df, formatted_new_df])
        updated_df.drop_duplicates(subset = ['Date', 'Ticker'], keep = 'last', inplace = True)
        updated_df.to_parquet(self.cache_file, engine = 'pyarrow', index = False)

        # Set historical_df
        self.historical_df = updated_df

        print(f'Cache successfully updated at {self.cache_file}. Total rows: {len(updated_df)}')
            

    def fetch_historical_data(self, tickers, start_date, end_date):
        '''
        Helper function to fetch data in chunks
        Parameters:
            tickers: Tickers to fetch data of (array str)
            start_date: First date of data (str)
            end_date: Last date of data (str)
        Return:
            Historical data (list pandas.DataFrame)
        '''

        # Chunk tickers
        chunks = [tickers[i : i + 50] for i in range(0, len(tickers), 50)]
        
        # Fetch data for each chunk
        historical_dfs = []
        for chunk in tqdm(chunks, desc = 'Downloading History', unit= 'chunk'):
            try:
                chunk_df = ld.get_history(
                    universe = chunk,
                    fields = ['TR.PriceClose'],
                    start = start_date.strftime('%Y-%m-%d'),
                    end = end_date.strftime('%Y-%m-%d')
                )

                # Add the chunk if it is not empty
                if chunk_df is not None and not chunk_df.empty:
                    historical_dfs.append(chunk_df)

            except Exception as e:
                tqdm.write(f'Error fetching chunk: {e}')
                
        return historical_dfs
    
    def format_historical_data(self, historical_dfs):
        '''
        Formats and cleans historical data
        Parameters:
            historical_dfs: Data to process (list pandas.DataFrame)
        Return:
            Processed data (pandas.DataFrame)
        '''
           
        # Concat all data
        raw_df = pd.concat(historical_dfs, axis=1).reset_index()
        
        # Format data
        formatted_df = pd.melt(
            raw_df, 
            id_vars=['Date'],  
            var_name='Ticker', 
            value_name='Close'
        )

        formatted_df['Close'] = pd.to_numeric(formatted_df['Close'], errors='coerce')
        formatted_df.dropna(subset=['Close'], inplace=True)
        formatted_df['Date'] = pd.to_datetime(formatted_df['Date'])
        
        return formatted_df
    
    def load_historical_data(self):
        '''
        Loads data from a parquet file
        Parameters: 
            None
        Returns:
            None
        '''

        # Check if historical_df is already populated
        if self.historical_df is not None and not self.historical_df.empty:
            return

        # Check if the file exists
        if not os.path.exists(self.cache_file):
            print('Cache file not found.')
            return
            
        # Read parquet file
        self.historical_df = pd.read_parquet(self.cache_file)
        print('Loaded historical data from a parquet file.')
            




        
    