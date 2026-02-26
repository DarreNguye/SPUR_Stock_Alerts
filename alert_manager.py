import pandas as pd
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

        print(alerts_df)
        pass