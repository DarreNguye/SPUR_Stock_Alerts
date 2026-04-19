import pandas as pd
import os
from datetime import datetime, timedelta
from tqdm import tqdm
import json

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
import yfinance as yf
import wrds

class DataProvider:
    '''
    Data provider class
    '''

    def __init__(self, pe_percentile, analyst_discount, req_score, min_market_cap, lookback_years, api_key, secret_key):
        self.universe_cache_file = 'data/universe.json'
        self.prices_cache_file = 'data/historical_prices.parquet'

        self.pe_percentile = pe_percentile
        self.analyst_discount = analyst_discount
        self.req_score = req_score
        
        self.min_market_cap = min_market_cap
        self.lookback_years = lookback_years

        self.trading_client = TradingClient(api_key, secret_key, paper = True)
        self.data_client = StockHistoricalDataClient(api_key, secret_key)

        self.universe_df = None
        self.prices_df = None

    # =============================================================================
    # UNIVERSE FUNCTIONS
    # =============================================================================

    def get_universe(self):
        '''
        Fetches a universe of a specified criteria
        Parameters:
            None
        Return:
            Universe data (pandas.DataFrame)
        '''

        # Load the universe if existing and current
        if self.load_universe():
            print('Loaded existing universe.')
            return self.universe_df
    
        print('Fetching new universe data...')
        
        # Build the query
        query = self.universe_query()
        
        # Fetch fundamentals
        fundamentals_df = self.fetch_fundamental_tickers(query)
        if fundamentals_df is None or fundamentals_df.empty:
            print('Ticker screener returned no fundamental data.')
            return pd.DataFrame()
        
        # Filter tradable
        ticker_list = fundamentals_df['tic'].tolist()
        tradable_tickers = self.filter_tradable_assets(ticker_list)
        fundamentals_df = fundamentals_df[fundamentals_df['tic'].isin(tradable_tickers)].copy()
            
        # Fetch insider trading
        insider_df = self.fetch_insider_trading(list(fundamentals_df.iterrows()))
        if insider_df is None or insider_df.empty:
            print('Insider trading fetch returned no data.')
            return pd.DataFrame()
        
        # Score calculation
        insider_df['score'] = insider_df['fundamentals_score'] + insider_df['insider_score']

        # Filter based on final score
        final_universe_df = insider_df[insider_df['score'] >= self.req_score]
        final_universe_df = final_universe_df.rename(columns={'tic': 'Ticker'})

        # Package universe data
        current_month = datetime.now().strftime('%Y-%m')
        universe_records = final_universe_df.to_dict(orient='records')
        data = {
            'Date': current_month,
            'Universe_Data': universe_records,
        }

        # Save
        os.makedirs(os.path.dirname(self.universe_cache_file), exist_ok=True)
        with open(self.universe_cache_file, 'w') as f:
            json.dump(data, f, indent=4)

        self.universe_df = pd.DataFrame(data['Universe_Data'])
        print(f'Successfuly fetched universe data for {len(self.universe_df)} tickers.')
        return self.universe_df
    
    def load_universe(self):
        '''
        Loads universe from a JSON file
        Parameters: 
            None
        Returns:
            Successful universe loading (bool)
        '''

        # Check if universe is already populated
        if self.universe_df is not None and not self.universe_df.empty:
            return True

        # Check if the file exists
        if not os.path.exists(self.universe_cache_file):
            return False
            
        # Read JSON file
        with open(self.universe_cache_file, 'r') as f:
            data = json.load(f)

        # Check if data is current
        current_month = datetime.now().strftime('%Y-%m')
        if data.get('Date') != current_month:
            return False

        # Set universe
        self.universe_df = pd.DataFrame(data['Tickers'])
        return True
    
    def clear_universe(self):
        '''Clears the universe'''
        if os.path.exists(self.universe_cache_file):
            os.remove(self.universe_cache_file) 

    def universe_query(self):
        '''
        Constructs an SQL query for TTM P/E, NTM P/E, and Analyst Targets
        Parameters:
            None
        Return:
            SQL query (str)
        '''
        start_date = (datetime.today() - timedelta(days=self.lookback_years * 365)).strftime('%Y-%m-%d')
        
        return f'''
            WITH MarketCapScreen AS (
                SELECT DISTINCT tic
                FROM comp.secd
                WHERE datadate = (SELECT MAX(datadate) FROM comp.secd)
                AND fic = 'USA' AND tpci = '0' 
                AND (prccd * csho * 1000000) > {self.min_market_cap}
            ),
            HistoricalPE AS (
                SELECT tic,
                       percentile_cont({self.pe_percentile}) WITHIN GROUP (ORDER BY pe_exi) as ttm_thresh,
                       percentile_cont({self.pe_percentile}) WITHIN GROUP (ORDER BY pe_inc) as ntm_thresh
                FROM wrdsapps.firm_ratio
                WHERE public_date >= '{start_date}'
                GROUP BY tic
            ),
            LatestPE AS (
                SELECT tic, pe_exi, pe_inc
                FROM (
                    SELECT tic, pe_exi, pe_inc,
                           ROW_NUMBER() OVER (PARTITION BY tic ORDER BY public_date DESC) as rn
                    FROM wrdsapps.firm_ratio
                ) tmp
                WHERE rn = 1
            ),
            AnalystTargets AS (
                SELECT ticker, ((mean_ptg - current_price) / mean_ptg) as discount_pct
                FROM ibes.summary
            ),
            ScoredWRDS AS (
               SELECT m.tic,
                       l.pe_exi, 
                       l.pe_inc, 
                       a.discount_pct,
                       (CASE WHEN l.pe_exi <= h.ttm_thresh THEN 1 ELSE 0 END) as ttm_score,
                       (CASE WHEN l.pe_inc <= h.ntm_thresh THEN 1 ELSE 0 END) as ntm_score,
                       (CASE WHEN a.upside_pct >= {self.analyst_discount} THEN 1 ELSE 0 END) as target_score
                FROM MarketCapScreen m
                LEFT JOIN HistoricalPE h ON m.tic = h.tic
                LEFT JOIN LatestPE l ON m.tic = l.tic
                LEFT JOIN AnalystTargets a ON m.tic = a.ticker
            )
            SELECT tic, 
                   (ttm_score + ntm_score + target_score) as fundamentals_score,
                   ttm_score,
                   ntm_score,
                   target_score,
                   pe_exi as raw_ttm_pe,
                   pe_inc as raw_ntm_pe,
                   discount_pct as raw_discount_pct
            FROM ScoredWRDS
            WHERE (ttm_score + ntm_score + target_score) >= {self.req_score - 3}
        '''

    def fetch_fundamental_tickers(self, sql_query):
        '''
        Executes the SQL query that pass the fundamental criteria
        Parameters:
            sql_query: An SQL query (str)
        Returns:
            Data on all passing tickers (pandas.DataFrame)
        '''

        print('Fetching new universe tickers...')
        db = None
        try:
            db = wrds.Connection()
            screened_data = db.raw_sql(sql_query)
            
            # Check if tickers exist
            if screened_data is None and screened_data.empty:
                print('No valid tickers for the universe.')
                return pd.DataFrame()
            
            # Clean tickers
            screened_data['tic'] = screened_data['tic'].str.replace('.', '-')
            return screened_data
            
        except Exception as e:
            print(f'Error fetching universe: {e}')
            return pd.DataFrame()
        
        finally:
            # Cleanup
            if db is not None:
                db.close()

    def fetch_insider_trading(self, tickers):
        '''
        Fetches insider trading data for tickers
        Parameters:
            tickers: Tickers to ensure are tradable (array str)
        Return:
            Net insider shares and a score (pandas.DataFrame)
        '''

        # Store
        rows = []
        
        # Fetch insider trading data
        for _, row in tqdm(tickers, total=len(tickers), desc = 'Fetching Insider Activity'):
            ticker = row['tic']
            insider_score = 0
            net_shares = 0 
            
            try:
                stock = yf.Ticker(ticker)
                insider_data = stock.insider_transactions
                
                # Check if there is insider trading data
                if insider_data is not None and not insider_data.empty:
                    net_shares = insider_data['Shares'].sum() 
                    if net_shares > 0:
                        insider_score = 1

            # Skip on excetion        
            except Exception:
                pass 
            
            # Convert row to dictionary
            row_dict = row.to_dict()
            row_dict['net_insider_shares'] = net_shares
            row_dict['insider_score'] = insider_score
            rows.append(row_dict)
                
        return pd.DataFrame(rows)

    def filter_tradable_assets(self, tickers):
        '''
        Ensures tickers are tradable
        Parameters:
            tickers: Tickers to ensure are tradable (array str)
        Return:
            Tradable tickers (list str)
        '''
        
        print('Ensuring tradability...')

        # Check if tickers are passed
        if not tickers:
            return []
            
        try:
            search_params = GetAssetsRequest(
                asset_class=AssetClass.US_EQUITY,
                status='active',
                feed=DataFeed.IEX
            )
            assets = self.trading_client.get_all_assets(search_params)
            tradable_symbols = {asset.symbol for asset in assets if asset.tradable}
            
            return list(set(tickers) & tradable_symbols)
            
        except Exception as e:
            print(f'Error filtering tradable assets via Alpaca: {e}')
            return []
    
    # =============================================================================
    # HISTORICAL PRICES FUNCTIONS
    # =============================================================================
        
    def initialize_prices_data(self):
        '''
        Initializes the cache of historical prices for a universe
        Parameters:
            None
        Return:
            None
        '''

        # Check if cache already exists 
        if os.path.exists(self.prices_cache_file):
            print(f'Cache already exists at {self.prices_cache_file}. Skipping cache initialization.')
            return
        
        # Check if the universe is empty
        if self.universe_df is None or self.universe_df.empty:
            print(f'Universe not defined.')
            return
        
        print(f'Fetching and caching {self.lookback_years}-years of historical prices for {len(self.universe_df)} tickers...')

        # Calculate historical prices time frame
        end_date = datetime.today() - timedelta(days=1) 
        start_date = end_date - timedelta(days = self.lookback_years * 365)

        # Fetch data
        tickers = self.universe_df['Ticker'].tolist()
        prices_dfs = self.fetch_prices_data(tickers, start_date, end_date)
        
        # Format data for caching
        if not prices_dfs:
            print('Failed to download historical prices.')
            return
        formatted_df = self.format_prices_data(prices_dfs)
        formatted_df.sort_values(['Ticker', 'Date'], inplace=True)

        # Keep only data within the lookback period 
        cutoff = datetime.today() - timedelta(days=self.lookback_years * 365)
        formatted_df = formatted_df[formatted_df['Date'] >= cutoff]
            
        # Cache data
        os.makedirs(os.path.dirname(self.prices_cache_file), exist_ok = True)
        formatted_df.to_parquet(self.prices_cache_file, engine = 'pyarrow', index = False)

        # Set prices_df
        self.prices_df = formatted_df

        print(f'Successfully cached historical prices with {len(formatted_df)} rows at {self.prices_cache_file}')

    def update_prices_data(self):
        '''
        Updates the cache of prices with new data
        Parameters:
            None
        Return:
            None
        '''

        # Check if the cache file exists
        if not os.path.exists(self.prices_cache_file):
            print('Cache not found. Starting historical prices download...')
            self.initialize_prices_data()
            return
        
        # Check if the universe is empty
        if self.universe_df is None or self.universe_df.empty:
            print('Universe not defined.')
            return

        # Load the existing cache
        history_df = pd.read_parquet(self.prices_cache_file)
        history_df['Date'] = pd.to_datetime(history_df['Date'])
        
        # Identify tickers in cache and new tickers
        cached_tickers = set(history_df['Ticker'].unique())
        current_tickers = set(self.universe_df['Ticker'].tolist())
        
        new_tickers = list(current_tickers - cached_tickers)
        existing_tickers = list(current_tickers & cached_tickers)

        # Calculate dates to pull
        end_date = datetime.today() - timedelta(days=1)
        last_cache_date = history_df['Date'].max()
        start_date = end_date - timedelta(days=self.lookback_years * 365)
        
        new_dfs = []

        # Fetch updated data for existing tickers
        if existing_tickers and last_cache_date.date() < end_date.date():
            print(f"Updating {len(existing_tickers)} existing tickers from {last_cache_date.strftime('%Y-%m-%d')}...")
            updated_existing_dfs = self.fetch_prices_data(existing_tickers, last_cache_date, end_date)
            new_dfs.extend(updated_existing_dfs)

        # Fetch full history for new tickers
        if new_tickers:
            print(f'Found {len(new_tickers)} new tickers. Fetching full {self.lookback_years}-year history...')
            new_tickers_dfs = self.fetch_prices_data(new_tickers, start_date, end_date)
            new_dfs.extend(new_tickers_dfs)

        # Format data
        if not new_dfs:
            print('Cache is already up to date. No new data downloaded.')
            return
        formatted_new_df = self.format_prices_data(new_dfs)
        
        # Merge old and new data
        updated_df = pd.concat([history_df, formatted_new_df])
        updated_df.drop_duplicates(subset = ['Date', 'Ticker'], keep = 'last', inplace = True)
        updated_df = updated_df[updated_df['Ticker'].isin(current_tickers)]
        updated_df.sort_values(['Ticker', 'Date'], inplace=True)

        # Keep only data within the lookback period
        cutoff = datetime.today() - timedelta(days=self.lookback_years * 365)
        updated_df = updated_df[updated_df['Date'] >= cutoff]
        updated_df.to_parquet(self.prices_cache_file, engine = 'pyarrow', index = False)

        # Set prices_df
        self.prices_df = updated_df

        print(f'Cache successfully updated at {self.prices_cache_file}. Total rows: {len(updated_df)}')
            

    def fetch_prices_data(self, tickers, start_date, end_date):
        '''
        Helper function to fetch data in chunks
        Parameters:
            tickers: Tickers to fetch data of (array str)
            start_date: First date of data (str)
            end_date: Last date of data (str)
        Return:
            Prices data (list pandas.DataFrame)
        '''

        # Chunk tickers
        chunks = [tickers[i : i + 500] for i in range(0, len(tickers), 500)]
        
        # Fetch data for each chunk
        prices_dfs = []
        for chunk in tqdm(chunks, desc = 'Downloading History', unit= 'chunk'):
            try:
                request_params = StockBarsRequest(
                    symbol_or_symbols = chunk,
                    timeframe = TimeFrame.Day,
                    start = start_date,
                    end = end_date,
                    feed = DataFeed.IEX
                )
                
                # Fetch bars and convert to a DataFrame
                chunk_df = self.data_client.get_stock_bars(request_params).df

                # Add the chunk if it is not empty
                if chunk_df is not None and not chunk_df.empty:
                    prices_dfs.append(chunk_df)

            except Exception as e:
                tqdm.write(f'Error fetching chunk: {e}')
                
        return prices_dfs
    
    def format_prices_data(self, prices_dfs):
        '''
        Formats and cleans historical prices
        Parameters:
            prices_dfs: Data to process (list pandas.DataFrame)
        Return:
            Processed data (pandas.DataFrame)
        '''
           
        # Concat all data
        raw_df = pd.concat(prices_dfs)
        raw_df.reset_index(inplace=True)
        
        # Format data
        raw_df.rename(columns={
            'symbol': 'Ticker',
            'timestamp': 'Date',
            'close': 'Close'
        }, inplace=True)

        formatted_df = raw_df[['Ticker', 'Date', 'Close']].copy()
        formatted_df['Close'] = pd.to_numeric(formatted_df['Close'], errors = 'coerce')
        formatted_df.dropna(subset = ['Close'], inplace = True)
        formatted_df['Date'] = pd.to_datetime(formatted_df['Date']).dt.tz_localize(None)
        
        return formatted_df
    
    def load_prices_data(self):
        '''
        Loads data from a parquet file
        Parameters: 
            None
        Returns:
            None
        '''

        # Check if prices_df is already populated
        if self.prices_df is not None and not self.prices_df.empty:
            return

        # Check if the file exists
        if not os.path.exists(self.prices_cache_file):
            print('Prices cache file not found.')
            return
            
        # Read parquet file
        self.prices_df = pd.read_parquet(self.prices_cache_file)
        print('Loaded historical prices from a parquet file.')

    # =============================================================================
    # LIVE PRICE FUNCTIONS
    # =============================================================================

    def fetch_live_prices(self, tickers):
        '''
        Fetch live intraday price data and the previous closing price for a list of tickers
        Parameters:
            tickers: Tickers to fetch prices of (list str)
        Return:
            Ticker, live price, and previous closing price (pandas.DataFrame)
        '''

        # Check if tickers are provided
        if not tickers:
            print('No tickers provided.')
            return pd.DataFrame()

        # Chunk tickers
        chunks = [tickers[i:i + 1000] for i in range(0, len(tickers), 1000)]
        live_rows = []

        # Fetch data for chunks
        for chunk in tqdm(chunks, desc = 'Fetching Live Prices', unit = 'chunk'):
            try:
                # Get live data
                request_params = StockSnapshotRequest(symbol_or_symbols = chunk, feed = DataFeed.IEX)
                snapshots = self.data_client.get_stock_snapshot(request_params)
                
                # Format
                for symbol, snapshot in snapshots.items():
                    if snapshot and snapshot.latest_trade and snapshot.previous_daily_bar:
                        live_rows.append({
                            'Ticker': symbol,
                            'Live_Price': snapshot.latest_trade.price,
                            'Prev_Close': snapshot.previous_daily_bar.close        
                        })

            except Exception as e:
                tqdm.write(f'Error fetching live pricing chunk: {e}')

        # Check if data is empty
        if not live_rows:
            print("Failed to fetch live pricing for all chunks.")
            return pd.DataFrame()

        # Format data
        live_df = pd.DataFrame(live_rows)
        live_df['Live_Price'] = pd.to_numeric(live_df['Live_Price'], errors='coerce')
        live_df['Prev_Close'] = pd.to_numeric(live_df['Prev_Close'], errors='coerce')
        live_df.dropna(subset=['Live_Price', 'Prev_Close'], inplace=True)

        return live_df

    # =============================================================================
    # LIVE IV FUNCTIONS
    # =============================================================================
        
    def fetch_live_volatilites(self, drops_df):
        '''
        Fetch live implied volatility data for a ATM call option expiring 30 days from now for a list of tickers
        Parameters:
            drops_df: Tickers and live price data from analyzer.find_drops (pandas.DataFrame)
        Return:
            Ticker and implied volsatility (pandas.DataFrame)
        '''

        # Check if there are drops
        if drops_df is None or drops_df.empty:
            print('No drops provided.')
            return pd.DataFrame()
        
        # Store data
        final_rows = []

        # Iterate through rows and and fetch implied volatility
        for _, row in tqdm(drops_df.iterrows(), desc = 'Fetching Implied Volatility', unit = ' ticker'):
            iv = self.fetch_live_volatility(row['Ticker'], row['Live_Price'])
            row_dict = row.to_dict()

            # Check if there implied volatility exists
            if iv:
                row_dict.update(iv)
            else:
                row_dict.update({
                    'Expiration': None,
                    'ATM_Strike': None,
                    'Implied_Volatility': None
                })
            
            final_rows.append(row_dict)
        
        return pd.DataFrame(final_rows)

    def fetch_live_volatility(self, ticker, live_price):
        '''
        Helper function to fetch live implied volatility data for a ATM call option expiring 30 days from now for a ticker
        Parameters:
           ticker: Ticker to pull data for (str)
           live_price: Live price (float)
        Return:
            Options data with Expiration, ATM_Strike, Implied Volatility (dict)
        '''
        # Search for options expiries
        symbol = yf.Ticker(ticker)
        expirations = symbol.options

        # Check if there are options
        if not expirations:
            tqdm.write(f'No options available for {ticker}')
            return None
        
        # Find the option with an expiration date closest to 30 days from now
        today = datetime.today()
        closest_date = expirations[0]
        min_diff = float('inf')
        for date_str in expirations:
            expiration_date = datetime.strptime(date_str, '%Y-%m-%d')
            days_diff = abs((expiration_date - today).days - 30)

            if days_diff < min_diff:
                min_diff = days_diff
                closest_date = date_str
        
        # Pull options data
        try:
            calls = symbol.option_chain(closest_date).calls
            calls['distance_from_price'] = abs(calls['strike'] - live_price)
            atm_row = calls.loc[calls['distance_from_price'].idxmin()]

            return {
                'Expiration': closest_date,
                'ATM_Strike': atm_row['strike'],
                'Implied_Volatility': atm_row['impliedVolatility']
            }

        except Exception as e:
            tqdm.write(f'Error fetching options data for {ticker}: {e}')
            return None




        
    