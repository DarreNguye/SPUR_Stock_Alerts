import pandas as pd
import streamlit as st
import os
import json
from datetime import datetime

class SystemStats:
    '''
    System stats viewer and analyzer class
    '''

    def __init__(self, stats_cache_file):
        self.scans_df = pd.DataFrame()
        self.alerts_df = pd.DataFrame()

        # Load data
        self.scans_df = self.load_scans(stats_cache_file)
        if not self.scans_df.empty:
            self.alerts_df = self.unpack_alerts()

    def load_scans(self, file_name):
        '''
        Loads in data from json
        Parameters:
            file_name: File to save to (str)
        Returns:
            None
        '''

        # Check if the file exists
        if not os.path.exists(file_name):
            print(f'File not found at {file_name}')
            return pd.DataFrame()
            
        # Load data from file
        with open(file_name, 'r') as f:
            raw_data = json.load(f)

        # Flatten data
        rows = []
        for _, daily_stats in raw_data.items():
            if 'Scans' in daily_stats:
                rows.extend(daily_stats['Scans'])

        # Convert and format into a DataFrame
        scans_df = pd.DataFrame(rows)
        if not scans_df.empty:
            scans_df['Time'] = pd.to_datetime(scans_df['Time'])

        print(f'Loaded {len(scans_df)} data points.')
        return scans_df
    
    def unpack_alerts(self):
        '''
        Unpacks alerts from the data and flattens them into a single DataFrame
        Parameters:
            None
        Returns:
            Alerts (pandas.DataFrame)
        '''

        # Check if there is data
        if self.scans_df.empty:
            print('No system stats to unpack.')
            return pd.DataFrame()

        # Store
        alerts_data = []

        # Iterate and pull data
        for time, alerts in zip(self.scans_df['Time'], self.scans_df['Alerts']):

            # Check if there are alerts and process
            if len(alerts) > 0:
                for alert in alerts:
                    alert = alert.copy()
                    alert['Time'] = time
                    alerts_data.append(alert)

        # Convert and format
        alerts_df = pd.DataFrame(alerts_data)
        if not alerts_df.empty:
            cols = ['Time', 'Ticker'] + [c for c in alerts_df.columns if c not in ['Time', 'Ticker']]
            alerts_df = alerts_df[cols]

        return alerts_df
    
    def display_stats(self):
        '''
        Launch a Streamlit page to display statistics
        Parameters:
            None
        Returns:
            None
        '''

        # Page Setup
        st.set_page_config(layout= 'wide')
        st.title('SPUR Stock Alerts Dashboard')

        # Ensure there is data
        if self.scans_df.empty:
            st.warning('No system stats to display.')
            return
        
        # Build components
        self.build_scan_table()
        self.build_alert_table()
        
    def build_scan_table(self):
        '''
        Renders a filterable table that displays info from scans
        Parameters:
            None
        Returns:
            None
        '''

        st.subheader('Filter Scans')

        # Format data
        display_df = self.scans_df.copy()
        display_df.sort_values(by = 'Time', ascending = False, inplace = True)
        
        # Filter for the DataFrame
        today = datetime.now().date()
        default_start = self.scans_df['Time'].min().date()

        date_range = st.date_input(
            'Select Date Range',
            value = (default_start, today),
            max_value = today,
            key = 'scan_table_dates'
        )

        # Set the start and end date
        if len(date_range) == 2:
            start_date, end_date = date_range
        elif len(date_range) == 1:
            start_date = date_range[0]
            end_date = today
        else:
            start_date = default_start
            end_date = today
            
        # Apply the filter
        mask = (display_df['Time'].dt.date >= start_date) & (display_df['Time'].dt.date <= end_date)
        filtered_scans_df = display_df.loc[mask]

        # Display the DataFrame
        st.subheader(f'Ticker Scans ({len(filtered_scans_df)})')
        st.dataframe(
           filtered_scans_df,
           use_container_width = True,
           hide_index = True,

           column_order = [
               'Time', 
               'Drop_Tickers', 
               'High_IV_Tickers'
           ],
           
           column_config = {
               'Time': 'Time',
               'Drop_Tickers': 'Drop Tickers',
               'High_IV_Tickers': 'High IV Tickers'
           }
        )

    def build_alert_table(self):
        '''
        Renders a filterable table that displays info from alerts
        Parameters:
            None
        Returns:
            None
        '''

        st.subheader('Filter Alerts')

        # Format data
        display_df = self.alerts_df.copy()
        
        if display_df.empty:
            st.warning('No alerts to display.')
            return
        
        display_df.sort_values(by = 'Time', ascending = False, inplace = True)
        
        # Filter for the DataFrame
        today = datetime.now().date()
        default_start = self.scans_df['Time'].min().date()

        date_range = st.date_input(
            'Select Date Range',
            value = (default_start, today),
            max_value = today,
            key = 'alert_table_dates'
        )

        # Set the start and end date
        if len(date_range) == 2:
            start_date, end_date = date_range
        elif len(date_range) == 1:
            start_date = date_range[0]
            end_date = today
        else:
            start_date = default_start
            end_date = today
            
        # Apply the filter
        mask = (display_df['Time'].dt.date >= start_date) & (display_df['Time'].dt.date <= end_date)
        filtered_scans_df = display_df.loc[mask]

        # Display the DataFrame
        st.subheader(f'Alerts ({len(filtered_scans_df)})')
        st.dataframe(
           filtered_scans_df,
           use_container_width = True,
           hide_index = True,
           
           column_order = [
               'Time', 
               'Ticker', 
               'Live_Price', 
               'Live_Return',
               'Implied_Volatility',
               'ATM_Strike',
               'Expiration'
            ],
           
           column_config = {
               'Time': 'Time', 
               'Ticker': 'Ticker', 
               'Live_Price': 'Live Price', 
               'Live_Return': 'Live Return',
               'Implied_Volatility': 'Implied Volatility',
               'ATM_Strike': 'ATM Strike',
               'Expiration': 'Expiration'
            },
        )

if __name__ == '__main__':
    stats_cache_file = 'data/system_data.json'
    dashboard = SystemStats(stats_cache_file)
    dashboard.display_stats()


