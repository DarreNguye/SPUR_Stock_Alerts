import pandas as pd
import lseg.data as ld
from lseg.data.discovery import Screener
import os
from datetime import datetime, timedelta
from tqdm import tqdm

class Data:

    def __init__(self, cache_file, min_market_cap, lookback_years):
        self.universe_df = pd.DataFrame()
        self.cache_file = cache_file
        self.min_market_cap = min_market_cap
        self.lookback_years = lookback_years

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
        
    def get_historical_data(self):
        '''
        Fetches historical prices for a universe and caches it
        Parameters:
            lookback_years: Years of historical data pulled (int)
        Return:
            None
        '''

        # Check if cache already exists or if the universe is empty
        if os.path.exists(self.cache_file):
            print(f'Cache already exists at {self.cache_file}. Skipping cache initialization.')
            return
        elif self.universe_df is None or self.universe_df.empty:
            print(f'Universe not defined.')
            return
        else:
            print(f'Caching {self.lookback_years}-years of historical data for {len(self.universe_df)} tickers...')

            # Calculate historical data time frame
            end_date = datetime.today()
            start_date = end_date - timedelta(days = self.lookback_years * 365)

            # Chunk tickers
            tickers = self.universe_df['Instrument'].tolist()
            chunks = [tickers[i : i + 50] for i in range(0, len(tickers), 50)]
            
            # Fetch data for each chunk
            historical_dfs = []
            for chunk in tqdm(chunks, desc="Downloading History", unit="chunk"):
                try:
                    # Fetch data
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
                    tqdm.write(f"Error fetching a chunk: {e}")

            if historical_dfs:
                historical_df = pd.concat(historical_dfs, axis=1)
                
                # Format data for caching
                historical_df = historical_df.reset_index()
            
                historical_formatted_df = pd.melt(
                    historical_df, 
                    id_vars=['Date'],  
                    var_name='Ticker', 
                    value_name='Close'
                )

                # Clean data
                historical_formatted_df['Close'] = pd.to_numeric(historical_formatted_df['Close'], errors='coerce')
                historical_formatted_df.dropna(subset=['Close'], inplace = True)
                historical_formatted_df['Date'] = pd.to_datetime(historical_formatted_df['Date'])
                    
                # Cache data
                os.makedirs(os.path.dirname(self.cache_file), exist_ok = True)
                historical_formatted_df.to_parquet(self.cache_file, engine='pyarrow', index = False)
                print(f'Cached historical data with {len(historical_formatted_df)} rows at {self.cache_file}.')
            else:
                print('Failed to download historical data.')




        
    