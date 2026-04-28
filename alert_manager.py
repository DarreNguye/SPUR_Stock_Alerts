import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pandas as pd
import textwrap

class AlertManager:
    '''
    Alert manager class using email
    '''

    def __init__(self, sender_email, sender_password, to_emails):
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.to_emails = to_emails

        # Email configurations
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 465 

    def process_alerts(self, alerts_df):
        '''
        Formats triggered alerts for the terminal and sends an email notification
        Parameters:
            alerts_df: Tickers to alert (pandas.DataFrame)
        Return:
            None
        '''

        # Check if there are tickers to alert
        if alerts_df is None or alerts_df.empty:
            return
        
        # Print to terminal
        self.print_terminal(alerts_df)
        
        # Send an email to all on the email list
        for email in self.to_emails:
            self.send_email(alerts_df, email)

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

            # Get scores
            composite = row.get('Composite_Score', 'N/A')
            universe_score = row.get('Universe_Score', 'N/A')
            ttm = row.get('TTM_Score', 'N/A')
            ntm = row.get('NTM_Score', 'N/A')
            ind_ttm = row.get('Ind_TTM_Score', 'N/A')
            ind_ntm = row.get('Ind_NTM_Score', 'N/A')
            analyst = row.get('Analyst_Score', 'N/A')
            insider = row.get('Insider_Score', 'N/A')
            

            # Print info
            print(f'{ticker:<10} | Drop:               {live_return_pct:>7.2f}% | Return Threshold:     {returns_threshold_pct:>7.2f}%')
            print(f'{"":<10} | Implied Volatility: {iv_pct:>7.2f}% | Volatility Threshold: {volatility_threshold_pct:>7.2f}%')
            print(f'   Live Price: ${live_price:.2f}  (Prev Close: ${prev_close:.2f})')

            if 'Expiration' in row and 'ATM_Strike' in row and pd.notnull(row['Expiration']):
                print(f"   Option ATM: ${row['ATM_Strike']:.2f}  (Expires: {row['Expiration']})")
            else:
                print("   Option ATM: N/A (No options chain available)")
            print(f'   Composite Score: {composite} | Universe: {universe_score} (TTM:{ttm} NTM:{ntm} IndTTM:{ind_ttm} IndNTM:{ind_ntm} Analyst:{analyst} Insider:{insider})')

            # Print context
            if 'Context' in row and pd.notnull(row['Context']):
                print(f"   AI Context:")
                
                # Strip line breaks
                raw_context = str(row['Context']).replace('\n', ' ')
                
                # Wrap the text
                wrapped_text = textwrap.fill(
                    raw_context, 
                    width = 75, 
                    initial_indent = '      > ', 
                    subsequent_indent = '        '
                )
                print(wrapped_text)
            
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
                <th>Composite Score</th>
                <th>Returns Score</th>
                <th>IV Score</th>
                <th>Universe Score</th>
                <th>TTM Score</th>
                <th>NTM Score</th>
                <th>Ind TTM Score</th>
                <th>Ind NTM Score</th>
                <th>Analyst Score</th>
                <th>Insider Score</th>
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
                <td>{row['Live_Return']*100:.2f}%</td>
                <td>{row['Returns_Threshold']*100:.2f}%</td>
                <td>{row['Implied_Volatility']*100:.2f}%</td>
                <td>{row['Volatility_Threshold']*100:.2f}%</td>
                <td>${row['Live_Price']:.2f}</td>
                <td>${row['Prev_Close']:.2f}</td>
                <td>{exp_display}</td>
                <td>{strike_display}</td>
                <td>{row.get('Composite_Score', 'N/A')}</td>
                <td>{row.get('Returns_Score', 'N/A')}</td>
                <td>{row.get('IV_Score', 'N/A')}</td>
                <td>{row.get('Universe_Score', 'N/A')}</td>
                <td>{row.get('TTM_Score', 'N/A')}</td>
                <td>{row.get('NTM_Score', 'N/A')}</td>
                <td>{row.get('Ind_TTM_Score', 'N/A')}</td>
                <td>{row.get('Ind_NTM_Score', 'N/A')}</td>
                <td>{row.get('Analyst_Score', 'N/A')}</td>
                <td>{row.get('Insider_Score', 'N/A')}</td>
              </tr>
            """

        # Close the table
        html += """
            </table>
        """

        # Show context
        if 'Context' in alerts_df.columns:
            html += """
            <br>
            <h3 style="color: #333333;">Valuation Context</h3>
            <ul style="line-height: 1.6; padding-left: 20px;">
            """
            
            # Create a row for each context
            for _, row in alerts_df.iterrows():

                # Extract context
                context_text = row.get('Context', 'Analysis unavailable.')
                context_text_formatted = str(context_text).replace('\n', '<br>')
                
                # Format
                html += f"""
                <li style="margin-bottom: 15px;">
                  <strong>{row['Ticker']}:</strong> {context_text_formatted}
                </li>
                """
                
            html += """
            </ul>
            """

        # Add a footer and close the HTML
        html += """
            <hr style="border: 0; border-top: 1px solid #eeeeee; margin-top: 20px;">
            <p style="font-size: 12px; color: gray;">Generated by SPUR Stock Alert System</p>
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