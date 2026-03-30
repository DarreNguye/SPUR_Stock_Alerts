import os
import json
from google import genai
from google.genai import types

class ValuationAgent:
    '''
    Class that uses Gemini 2.5 Flash LLM to determine relative valuation
    '''
     
    def __init__(self, api_key):
        self.client = genai.Client(api_key = api_key)

    def analyze_tickers(self, alerts_data):
        '''
        Takes a list of alert dictionaries and returns a dictionary of AI valuation summaries
        Parameters:
            alerts_data: Tickers to value (pandas.DataFrame)
        Returns:
            
        '''
        tickers = [alert['Ticker'] for alert in alerts_data]
        print(f'Asking Gemini for context on batch: {tickers}...')
        
        # Build a single prompt for all tickers
        prompt = f'''
        The following stocks have just triggered a price drop alert:
        {json.dumps(alerts_data, indent=2)}
        
        For EACH ticker:
        1. Use Google Search to find the most recent financial data and news.
        2. Write a 3-sentence summary analyzing if the stock is overvalued or undervalued based on its drop today.
        
        You MUST return the output as a JSON array of objects, with keys "Ticker" and "AI_Context".
        '''

        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}],
                    temperature=0.2,
                    # FORCING JSON OUTPUT: This guarantees the output is parseable by your code!
                    response_mime_type="application/json", 
                )
            )
            
            # Convert the string response back into a Python list of dictionaries
            return json.loads(response.text)
            
        except Exception as e:
            print(f"Gemini API Error during batch analysis: {e}")
            return []