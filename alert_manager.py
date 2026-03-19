import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pandas as pd

class AlertManager:
    '''
    Alert manager class using email
    '''

    def __init__(self, sender_email, sender_password, to_emails):
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.to_emails = to_emails

        self.old_alerts = []

        # Email configurations
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 465 

    def process_alerts(self, alerts_df):
        '''
        Formats triggered alerts for the terminal and sends an email notification
        Parameters:
            alerts_df: Tickers to alert (pandas.DataFrame)
        Return:
            New tickers (pandas.DataFrame)
        '''

        # Check if there are tickers to alert
        if alerts_df is None or alerts_df.empty:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan complete: No tickers detected.")
            return pd.DataFrame()
        
        # Print to terminal
        self.print_terminal(alerts_df)
        
        # Filter for new alerts
        new_alerts_df = alerts_df[~alerts_df['Ticker'].isin(self.old_alerts)]
        if new_alerts_df.empty:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan complete: Tickers detected, but already alerted today.")
            return pd.DataFrame()
        
        # Send an email to all on the email list
        for email in self.to_emails:
            self.send_email(new_alerts_df, email)

        # Update old alerts
        new_tickers = new_alerts_df['Ticker'].tolist()
        self.old_alerts.extend(new_tickers)

        return new_alerts_df

    def print_terminal(self, alerts_df):
        '''
        Print to the terminal
        Parameters:
            alerts_df: Tickers to alert (pandas.DataFrame)
        Return:
            None
        '''

        # Format the header
        print('\n' + '='*55)
        print(f'Threshold')
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print('='*55)

        # Format the output
        for _, row in alerts_df.iterrows():
            ticker = row['Ticker']
            live_price = row['Live_Price']
            prev_close = row['Prev_Close']
            
            # Format decimals into percentages
            live_return_pct = row['Live_Return'] * 100
            returns_threshold_pct = row['Returns_Threshold'] * 100
            iv_pct = row['Implied_Volatility'] * 100
            volatility_threshold_pct = row['Volatility_Threshold'] * 100

            # Print info
            print(f'{ticker:<10} | Drop:               {live_return_pct:>7.2f}% | Return Threshold:     {returns_threshold_pct:>7.2f}%')
            print(f'{"":<10} | Implied Volatility: {iv_pct:>7.2f}% | Volatility Threshold: {volatility_threshold_pct:>7.2f}%')
            print(f'   Live Price: ${live_price:.2f}  (Prev Close: ${prev_close:.2f})')

            if 'Expiration' in row and 'ATM_Strike' in row and pd.notnull(row['Expiration']):
                print(f"   Option ATM: ${row['ATM_Strike']:.2f}  (Expires: {row['Expiration']})")
            else:
                print("   Option ATM: N/A (No options chain available)")
            
            print('-' * 75)


    def send_email(self, alerts_df, to_email):
        '''
        Helper function to build an HTML email and send it
        Parameters: 
            alerts_df: Tickers to alert (pandas.DataFrame)
            to_email: Email to send to (str)
        Return:
            None
        '''

        # Check if the email system is well defined
        if not self.sender_email or not self.sender_password or not to_email:
            print('Email information is missing.')
            return

        # Define the subject
        subject = f' ALERT: {len(alerts_df)} Stocks Breached Extreme Drop Thresholds'
        
        # Build an HTML Table for the email body
        html = '''
        <html>
          <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #d9534f;">Threshold Alerts</h2>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
              <tr style="background-color: #f2f2f2;">
                <th>Ticker</th>
                <th>Live Drop</th>
                <th>Return Threshold</th>
                <th>Implied Volatility</th>
                <th>Volatility Threshold</th>
                <th>Live Price</th>
                <th>Prev Close</th>
                <th>Option Expiration</th>
                <th>ATM Strike</th>
              </tr>
        '''
        
        # Add a row for each ticker
        for _, row in alerts_df.iterrows():

            # Extract options data
            expiration = row.get('Expiration')
            atm_strike = row.get('ATM_Strike')
            
            exp_display = expiration if pd.notnull(expiration) else 'N/A'
            strike_display = f'${atm_strike:.2f}' if pd.notnull(atm_strike) else 'N/A'

            html += f"""
              <tr>
                <td><strong>{row['Ticker']}</strong></td>
                <td style="color: red; font-weight: bold;">{row['Live_Return']*100:.2f}%</td>
                <td>{row['Returns_Threshold']*100:.2f}%</td>
                <td style="color: green; font-weight: bold;">{row['Implied_Volatility']*100:.2f}%</td>
                <td>{row['Volatility_Threshold']*100:.2f}%</td>
                <td>${row['Live_Price']:.2f}</td>
                <td>${row['Prev_Close']:.2f}</td>
                <td>{exp_display}</td>
                <td>{strike_display}</td>
              </tr>
            """
            
        html += """
            </table>
            <p style="font-size: 12px; color: gray;">Generated by Threshold Alert System</p>
          </body>
        </html>
        """

        # Construct message
        msg = MIMEMultipart()
        msg['From'] = self.sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(html, 'html'))

        # Send email
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, context=context) as server:
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, to_email, msg.as_string())
            print(f'Email alert successfully sent to {to_email}.')
        except Exception as e:
            print(f'Failed to send email alert: {e}')