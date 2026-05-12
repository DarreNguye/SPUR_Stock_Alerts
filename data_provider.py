import pandas as pd
import os
import time
import random
from datetime import datetime, timedelta
from tqdm import tqdm
import json
import warnings

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
import yfinance as yf
import wrds

warnings.simplefilter(action='ignore', category=FutureWarning)

class DataProvider:
    '''
    Data provider class
    '''

    def __init__(self, pe_percentile, analyst_discount, req_score, min_market_cap, lookback_years, db_user, db_pass, api_key, secret_key):
        self.universe_cache_file = 'data/universe.json'
        self.prices_cache_file = 'data/historical_prices.parquet'

        self.pe_percentile = pe_percentile
        self.analyst_discount = analyst_discount
        self.req_score = req_score
        
        self.min_market_cap = min_market_cap
        self.lookback_years = lookback_years

        self.db_user = db_user
        self.db_pass = db_pass

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
        if fundamentals_df.empty:
            print('Ticker screener returned no fundamental data.')
            return pd.DataFrame()
        print(f'{len(fundamentals_df)} tickers passed fundamental screening.')
        
        # Filter tradable
        print('Ensuring tradability...')
        ticker_list = fundamentals_df['Ticker'].tolist()
        tradable_tickers = self.filter_tradable_assets(ticker_list)
        fundamentals_df = fundamentals_df[fundamentals_df['Ticker'].isin(tradable_tickers)].copy()
        if fundamentals_df.empty:
            print('No tradable tickers found.')
            return pd.DataFrame()
            
        # Fetch insider trading
        print('Fetching insider trading...')
        insider_df = self.fetch_insider_trading(list(fundamentals_df.iterrows()))
        if insider_df is None or insider_df.empty:
            print('Insider trading fetch returned no data.')
            return pd.DataFrame()
        
        # Score calculation
        insider_df['Universe_Score'] = insider_df['Fundamentals_Score'] + insider_df['Insider_Score']

        # Filter based on final score
        final_universe_df = insider_df[insider_df['Universe_Score'] >= self.req_score - 2]

        # Fundamentals score is no longer needed
        if 'Fundamentals_Score' in final_universe_df.columns:
            final_universe_df = final_universe_df.drop(columns=['Fundamentals_Score'])

        # Check if the final universe successfuly created
        if final_universe_df is None or final_universe_df.empty:
            print('Error fetching universe data.')
            return pd.DataFrame()

        # Package universe data
        final_universe_df = final_universe_df.astype(object).where(pd.notna(final_universe_df), None)
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
        self.universe_df = pd.DataFrame(data['Universe_Data'])
        return True
    
    def clear_universe(self):
        '''Clears the universe'''
        if os.path.exists(self.universe_cache_file):
            os.remove(self.universe_cache_file) 

    def universe_query(self):
        '''
        Constructs an SQL query for TTM P/E, NTM P/E, Analyst Targets, and Industry P/E.

        Data sources by signal:
        - Current TTM P/E: live current_price (comp.secd) / sum of last 4 reported quarterly EPS
          from comp.fundq (epspxq). This is fresher than wrdsapps.firm_ratio, which is rebuilt
          on a monthly batch and can lag earnings by 4-8 weeks.
        - Historical TTM P/E percentile: wrdsapps.firm_ratio.pe_exi (kept for the historical
          threshold because its monthly cadence and consistent methodology are appropriate there).
        - Current NTM P/E: current_price / IBES FY1 mean EPS estimate (statsum_epsus, fpi='1').
          wrdsapps.firm_ratio has no forward P/E column.
        - Historical NTM P/E percentile: per-month IBES FY1 estimate paired with that month's
          last close from comp.secd.
        - Industry percentiles: restricted to the large-cap MarketCapScreen universe.
        - IBES recency filter is 120 days (statpers is monthly; 90d sat right at the boundary).
        Parameters:
            None
        Return:
            SQL query (str)
        '''
        start_date = (datetime.today() - timedelta(days=self.lookback_years * 365)).strftime('%Y-%m-%d')
        # IBES summary tables update monthly on the third Thursday — 120 days = 3-4 statpers periods
        ibes_recent_date = (datetime.today() - timedelta(days=120)).strftime('%Y-%m-%d')
        # 18 months back guarantees 4 reported quarters are visible even with reporting lag
        eighteen_months_ago = (datetime.today() - timedelta(days=545)).strftime('%Y-%m-%d')

        return f'''
            WITH LatestUSDate AS (
                SELECT MAX(datadate) as max_date
                FROM comp.secd
                WHERE fic = 'USA' AND tpci = '0'
                AND prccd IS NOT NULL AND cshoc IS NOT NULL
            ),
            MarketCapScreen AS (
                SELECT DISTINCT tic AS ticker, prccd AS current_price
                FROM comp.secd
                WHERE datadate = (SELECT max_date FROM LatestUSDate)
                AND fic = 'USA' AND tpci = '0'
                AND (prccd * cshoc) > {self.min_market_cap}
            ),
            IndustryMap AS (
                -- One industry per ticker; deduplicated when a tic maps to multiple gvkeys
                SELECT ticker, industry_code
                FROM (
                    SELECT s.tic AS ticker,
                           SUBSTRING(c.sic, 1, 2) AS industry_code,
                           ROW_NUMBER() OVER (PARTITION BY s.tic ORDER BY s.gvkey) as rn
                    FROM comp.secd s
                    JOIN comp.company c ON s.gvkey = c.gvkey
                    WHERE s.datadate = (SELECT max_date FROM LatestUSDate)
                    AND c.sic IS NOT NULL
                ) tmp
                WHERE rn = 1
            ),
            HistoricalTTMPE AS (
                SELECT ticker,
                       percentile_cont({self.pe_percentile}) WITHIN GROUP (ORDER BY pe_exi) as ttm_thresh
                FROM wrdsapps.firm_ratio
                WHERE public_date >= '{start_date}'
                AND pe_exi IS NOT NULL
                AND pe_exi > 0
                GROUP BY ticker
            ),
            LatestTTMEPS AS (
                -- Sum of last 4 reported quarters of diluted EPS (excl. extraordinary items)
                -- comp.fundq updates per filing (~1-2 weeks after a 10-Q), much fresher than firm_ratio's monthly batch.
                SELECT ticker, SUM(epspxq) AS ttm_eps
                FROM (
                    SELECT ticker, datadate, epspxq,
                           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY datadate DESC) AS qrn
                    FROM (
                        -- Dedupe rows when the same (ticker, datadate) appears under both INDL and FS
                        SELECT tic AS ticker, datadate, epspxq,
                               ROW_NUMBER() OVER (PARTITION BY tic, datadate ORDER BY indfmt) AS prn
                        FROM comp.fundq
                        WHERE datafmt = 'STD' AND popsrc = 'D' AND consol = 'C'
                          AND indfmt IN ('INDL', 'FS')
                          AND epspxq IS NOT NULL
                          AND datadate >= '{eighteen_months_ago}'
                    ) dedup
                    WHERE prn = 1
                ) ranked
                WHERE qrn <= 4
                GROUP BY ticker
                HAVING COUNT(*) = 4 AND SUM(epspxq) > 0
            ),
            LatestTTMPE AS (
                -- Fresh current TTM P/E using today's price + most-recent 4 quarters of reported EPS.
                -- Removes dependency on firm_ratio's monthly publication cadence for the latest snapshot.
                SELECT m.ticker, (m.current_price / NULLIF(e.ttm_eps, 0)) AS pe_exi
                FROM MarketCapScreen m
                JOIN LatestTTMEPS e ON m.ticker = e.ticker
                WHERE e.ttm_eps > 0
            ),
            LatestForwardEPS AS (
                -- IBES FY1 mean EPS estimate (used as forward EPS for NTM P/E)
                SELECT oftic as ticker, meanest as fwd_eps
                FROM (
                    SELECT oftic, meanest,
                           ROW_NUMBER() OVER (PARTITION BY oftic ORDER BY statpers DESC) as rn
                    FROM ibes.statsum_epsus
                    WHERE fpi = '1'
                    AND measure = 'EPS'
                    AND statpers >= '{ibes_recent_date}'
                    AND meanest IS NOT NULL
                    AND meanest > 0
                ) tmp
                WHERE rn = 1
            ),
            MonthEndPrices AS (
                -- Last trading day's close per ticker-month, used for historical NTM P/E reconstruction
                SELECT ticker, month_start, price
                FROM (
                    SELECT
                        tic AS ticker,
                        DATE_TRUNC('month', datadate)::date as month_start,
                        prccd as price,
                        ROW_NUMBER() OVER (
                            PARTITION BY tic, DATE_TRUNC('month', datadate)
                            ORDER BY datadate DESC
                        ) as rn
                    FROM comp.secd
                    WHERE datadate >= '{start_date}'
                    AND fic = 'USA' AND tpci = '0'
                    AND prccd IS NOT NULL
                ) tmp
                WHERE rn = 1
            ),
            HistoricalNTMPE AS (
                -- Per-ticker percentile of historical forward P/E = month_end_price / IBES FY1 mean EPS
                SELECT
                    s.oftic as ticker,
                    percentile_cont({self.pe_percentile}) WITHIN GROUP (
                        ORDER BY (mp.price / NULLIF(s.meanest, 0))
                    ) as ntm_thresh
                FROM ibes.statsum_epsus s
                JOIN MonthEndPrices mp
                    ON s.oftic = mp.ticker
                    AND DATE_TRUNC('month', s.statpers)::date = mp.month_start
                WHERE s.fpi = '1'
                AND s.measure = 'EPS'
                AND s.statpers >= '{start_date}'
                AND s.meanest > 0
                GROUP BY s.oftic
            ),
            IndustryTTMPE AS (
                -- Industry pe_percentile threshold computed across the large-cap universe only
                SELECT i.industry_code,
                       percentile_cont({self.pe_percentile}) WITHIN GROUP (ORDER BY l.pe_exi) as ind_ttm_thresh
                FROM LatestTTMPE l
                JOIN IndustryMap i ON l.ticker = i.ticker
                JOIN MarketCapScreen m ON l.ticker = m.ticker
                GROUP BY i.industry_code
            ),
            IndustryNTMPE AS (
                -- Industry pe_percentile threshold of current NTM P/E across the large-cap universe
                SELECT i.industry_code,
                       percentile_cont({self.pe_percentile}) WITHIN GROUP (
                           ORDER BY (m.current_price / NULLIF(f.fwd_eps, 0))
                       ) as ind_ntm_thresh
                FROM LatestForwardEPS f
                JOIN MarketCapScreen m ON f.ticker = m.ticker
                JOIN IndustryMap i ON f.ticker = i.ticker
                GROUP BY i.industry_code
            ),
            AnalystTargets AS (
                SELECT oftic AS ticker, meanptg
                FROM (
                    SELECT oftic, meanptg,
                           ROW_NUMBER() OVER (PARTITION BY oftic ORDER BY statpers DESC) as rn
                    FROM ibes.ptgsum
                    WHERE statpers >= '{ibes_recent_date}'
                    AND meanptg IS NOT NULL
                    AND meanptg > 0
                ) tmp
                WHERE rn = 1
            ),
            ScoredWRDS AS (
               SELECT m.ticker,
                       l.pe_exi as ttm_pe,
                       (m.current_price / NULLIF(f.fwd_eps, 0)) as ntm_pe,
                       h.ttm_thresh,
                       hn.ntm_thresh,
                       ind.ind_ttm_thresh,
                       indn.ind_ntm_thresh,
                       -- Upside relative to the current price (not the target)
                       ((a.meanptg - m.current_price) / NULLIF(m.current_price, 0)) as discount_pct,

                       CASE WHEN l.pe_exi <= h.ttm_thresh THEN 1 ELSE 0 END as ttm_score,
                       CASE WHEN (m.current_price / NULLIF(f.fwd_eps, 0)) <= hn.ntm_thresh THEN 1 ELSE 0 END as ntm_score,
                       CASE WHEN ((a.meanptg - m.current_price) / NULLIF(m.current_price, 0)) >= {self.analyst_discount} THEN 1 ELSE 0 END as analyst_score,
                       CASE WHEN l.pe_exi <= ind.ind_ttm_thresh THEN 1 ELSE 0 END as ind_ttm_score,
                       CASE WHEN (m.current_price / NULLIF(f.fwd_eps, 0)) <= indn.ind_ntm_thresh THEN 1 ELSE 0 END as ind_ntm_score

                FROM MarketCapScreen m
                LEFT JOIN HistoricalTTMPE h ON m.ticker = h.ticker
                LEFT JOIN HistoricalNTMPE hn ON m.ticker = hn.ticker
                LEFT JOIN LatestTTMPE l ON m.ticker = l.ticker
                LEFT JOIN LatestForwardEPS f ON m.ticker = f.ticker
                LEFT JOIN AnalystTargets a ON m.ticker = a.ticker
                LEFT JOIN IndustryMap imap ON m.ticker = imap.ticker
                LEFT JOIN IndustryTTMPE ind ON imap.industry_code = ind.industry_code
                LEFT JOIN IndustryNTMPE indn ON imap.industry_code = indn.industry_code
            )
            SELECT ticker as "Ticker",
                   (ttm_score + ntm_score + analyst_score + ind_ttm_score + ind_ntm_score) as "Fundamentals_Score",
                   ttm_score as "TTM_Score",
                   ntm_score as "NTM_Score",
                   ind_ttm_score as "Ind_TTM_Score",
                   ind_ntm_score as "Ind_NTM_Score",
                   analyst_score as "Analyst_Score",
                   ttm_pe as "Raw_TTM_PE",
                   ttm_thresh as "TTM_Threshold",
                   ind_ttm_thresh as "Ind_TTM_Threshold",
                   ntm_pe as "Raw_NTM_PE",
                   ntm_thresh as "NTM_Threshold",
                   ind_ntm_thresh as "Ind_NTM_Threshold",
                   discount_pct as "Raw_Discount_pct"
            FROM ScoredWRDS
            WHERE (ttm_score + ntm_score + analyst_score + ind_ttm_score + ind_ntm_score) >= {self.req_score - 3}
        '''

    def fetch_fundamental_tickers(self, sql_query):
        '''
        Executes the SQL query that pass the fundamental criteria
        Parameters:
            sql_query: An SQL query (str)
        Returns:
            Data on all passing tickers (pandas.DataFrame)
        '''

        db = None
        try:
            db = wrds.Connection(
                wrds_username = self.db_user, 
                wrds_password = self.db_pass
            )
            screened_data = db.raw_sql(sql_query)
            
            # Check if tickers exist
            if screened_data.empty:
                print('No valid tickers for the universe.')
                return pd.DataFrame()
            
            # Clean tickers (regex=False to treat '.' as a literal character, not a wildcard)
            screened_data.loc[:, 'Ticker'] = screened_data['Ticker'].str.replace('.', '-', regex=False)
            return screened_data
            
        except Exception as e:
            print(f'Error fetching universe: {e}')
            return pd.DataFrame()
        
        finally:
            # Cleanup
            if db is not None:
                db.close()

    def _fetch_insider_with_retry(self, ticker, max_attempts=4):
        '''
        Fetch yfinance insider_transactions with exponential backoff on Yahoo 429s.
        Returns the DataFrame on success (which may be empty), or None if every attempt failed.
        Distinguishing None from an empty DataFrame lets the caller retry only the failures.
        '''
        for attempt in range(max_attempts):
            try:
                data = yf.Ticker(ticker).insider_transactions
                # yfinance returns None for some tickers without raising; treat as a soft miss
                return data
            except Exception:
                if attempt == max_attempts - 1:
                    return None
                # Exponential backoff with jitter: ~2s, 4s, 8s
                time.sleep((2 ** (attempt + 1)) + random.random())
        return None

    def _score_insider_data(self, insider_data):
        '''
        Compute (net_shares, insider_score) from a yfinance insider_transactions DataFrame.
        Returns (0, 0) for None / empty / missing-columns inputs.
        '''
        if insider_data is None or insider_data.empty or 'Shares' not in insider_data.columns:
            return 0, 0

        shares = pd.to_numeric(insider_data['Shares'], errors='coerce').fillna(0)

        # Determine buy/sell direction from the Transaction column when available
        if 'Transaction' in insider_data.columns:
            txn = insider_data['Transaction'].astype(str).str.lower()
            buy_mask = txn.str.contains('purchase', na=False)
            sell_mask = txn.str.contains('sale', na=False) | txn.str.contains('sell', na=False)
            net_shares = int(shares[buy_mask].sum() - shares[sell_mask].sum())
        else:
            # Fallback: assume already signed
            net_shares = int(shares.sum())

        return net_shares, (1 if net_shares > 0 else 0)

    def fetch_insider_trading(self, tickers):
        '''
        Fetches insider trading data for tickers and computes NET share buying.
        yfinance's insider_transactions 'Shares' column is unsigned; direction is in 'Transaction'
        (e.g. "Purchase", "Sale"). Summing 'Shares' alone gives total volume, not net flow.

        Yahoo Finance rate-limits aggressively (HTTP 429). We pace requests with a small baseline
        sleep, retry each ticker up to 4x with exponential backoff, then do a second cooldown pass
        over any tickers that failed every retry on the first pass.

        Parameters:
            tickers: List of (index, pandas.Series) tuples from DataFrame.iterrows()
        Return:
            Net insider shares and a score (pandas.DataFrame)
        '''

        # Store
        rows = []
        # Track tickers whose every retry attempt failed (likely rate-limited) so we can revisit them
        failed_tickers = []

        # First pass — fetch every ticker with retry-on-429 and a baseline pace
        for _, row in tqdm(tickers, total=len(tickers), desc='Fetching Insider Activity'):
            ticker = row['Ticker']
            insider_data = self._fetch_insider_with_retry(ticker)
            net_shares, insider_score = self._score_insider_data(insider_data)

            row_dict = row.to_dict()
            row_dict['Net_Insider_Shares'] = net_shares
            row_dict['Insider_Score'] = insider_score
            rows.append(row_dict)

            if insider_data is None:
                failed_tickers.append(len(rows) - 1)  # index of this row in `rows`

            # Baseline pacing — keeps us comfortably under Yahoo's per-minute cap
            time.sleep(0.3)

        # Second pass — give Yahoo a long cooldown then retry only the rows that fully failed
        if failed_tickers:
            tqdm.write(f'Retrying {len(failed_tickers)} insider fetches after rate-limit cooldown...')
            time.sleep(30)
            for idx in tqdm(failed_tickers, desc='Retrying Insider Activity'):
                ticker = rows[idx]['Ticker']
                insider_data = self._fetch_insider_with_retry(ticker)
                net_shares, insider_score = self._score_insider_data(insider_data)
                rows[idx]['Net_Insider_Shares'] = net_shares
                rows[idx]['Insider_Score'] = insider_score
                time.sleep(0.5)

        return pd.DataFrame(rows)

    def filter_tradable_assets(self, tickers):
        '''
        Ensures tickers are tradable
        Parameters:
            tickers: Tickers to ensure are tradable (array str)
        Return:
            Tradable tickers (list str)
        '''

        # Check if tickers are passed
        if not tickers:
            return []
            
        try:
            search_params = GetAssetsRequest(
                asset_class=AssetClass.US_EQUITY,
                status='active',
            )
            assets = self.trading_client.get_all_assets(search_params)
            tradable_symbols = {asset.symbol for asset in assets if asset.tradable}
            
            return list(set(tickers) & tradable_symbols)
            
        except Exception as e:
            print(f'Error filtering tradable assets: {e}')
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

        # Keep only data within the lookback period (normalize to midnight to avoid time-of-day boundary drops)
        cutoff = pd.Timestamp(datetime.today().date()) - timedelta(days=self.lookback_years * 365)
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

        # Fetch updated data for existing tickers. Overlap by re-fetching the last cached day so any
        # corrections (or partial-day bars from a prior aborted run) are picked up; drop_duplicates
        # below dedupes on (Date, Ticker).
        if existing_tickers and last_cache_date.date() <= end_date.date():
            fetch_start = last_cache_date
            print(f"Updating {len(existing_tickers)} existing tickers from {fetch_start.strftime('%Y-%m-%d')}...")
            updated_existing_dfs = self.fetch_prices_data(existing_tickers, fetch_start, end_date)
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

        # Keep only data within the lookback period (normalize to midnight to avoid time-of-day boundary drops)
        cutoff = pd.Timestamp(datetime.today().date()) - timedelta(days=self.lookback_years * 365)
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
        formatted_df['Date'] = pd.to_datetime(formatted_df['Date']).dt.tz_convert(None)
        
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
            print('No tickers provided for live prices.')
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
        
    def fetch_live_volatilites(self, live_prices_df):
        '''
        Fetch live implied volatility data for a ATM call option expiring 30 days from now for a list of tickers
        Parameters:
            live_prices_df: Tickers and live price data (pandas.DataFrame)
        Return:
            Ticker and implied volsatility (pandas.DataFrame)
        '''

        # Check if there are drops
        if live_prices_df is None or live_prices_df.empty:
            print('No tickers provided for live IV.')
            return pd.DataFrame()
        
        # Store data
        final_rows = []

        # Iterate through rows and and fetch implied volatility
        for _, row in tqdm(live_prices_df.iterrows(), total=len(live_prices_df), desc = 'Fetching Implied Volatility', unit = ' ticker'):
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

            iv = atm_row['impliedVolatility']

            # Validate IV — yfinance returns 0.0 or NaN for illiquid strikes
            if iv is None or pd.isna(iv) or iv <= 0:
                tqdm.write(f'Invalid IV for {ticker} (got {iv}); skipping.')
                return None

            return {
                'Expiration': closest_date,
                'ATM_Strike': atm_row['strike'],
                'Implied_Volatility': iv
            }

        except Exception as e:
            tqdm.write(f'Error fetching options data for {ticker}: {e}')
            return None




        
    