from datetime import datetime


class AlertManager:

    def process_alerts(self, alerts_df):
        '''
        Alerts users of tickers that drop below the set thresholds
        Parameters:
            alerts_df: Tickers to alert the user of (pandas.DataFrame)
        Return:
            None
        '''

        # Check if there are tickers to alerts
        if alerts_df is None or alerts_df.empty:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan complete: No extreme drops detected.")
            return

        # Format header
        print('\n' + '='*55)
        print(f'PRICE DROP ALERT')
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print('='*55)

        # Format the output
        for _, row in alerts_df.iterrows():
            ticker = row['Ticker']
            live_price = row['Live_Price']
            prev_close = row['Prev_Close']
            
            # Format decimals into percentages
            live_return_pct = row['Live_Return'] * 100
            threshold_pct = row['Percentile_Threshold'] * 100
            
            print(f'{ticker:<10} | Drop: {live_return_pct:>6.2f}% | Limit: {threshold_pct:>6.2f}%')
            print(f'   Live Price: ${live_price:.2f}  (Prev Close: ${prev_close:.2f})')
            print('-' * 55)