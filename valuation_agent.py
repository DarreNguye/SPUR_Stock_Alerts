import pandas as pd
import json
from google import genai
from google.genai import types

class ValuationAgent:
    '''
    Class that uses Gemini 2.5 Flash LLM to determine relative valuation
    '''
     
    def __init__(self, api_key):
        self.client = genai.Client(api_key = api_key)

    def analyze_tickers(self, prompt, temperature, alerts_df):
        '''
        Takes a list of alert dictionaries and adds in AI-generated context
        Parameters:
            prompt: Directions for the AI (str)
            temperature: The temperature to set the LLM response (float)
            alerts_df: Tickers to value (pandas.DataFrame)
        Returns:
            Alerts data enriched with context (pandas.DataFrame)
        '''

        # Check if there are tickers to analyze
        if alerts_df is None or alerts_df.empty:
            print(f'No tickers detected')
            return pd.DataFrame()


        # Create a safe copy
        enriched_df = alerts_df.copy() 

        # Extract data
        tickers = enriched_df['Ticker'].tolist()
        alert_data = enriched_df.to_dict(orient='records')

        print(f'Asking Gemini for context on batch: {tickers}...')
        
        # Create the directions
        data_string = f'The following stocks have just triggered a price drop alert: {json.dumps(alert_data, indent=2)}'
        out_format = 'You MUST return the output as a JSON array of objects, with keys "Ticker" and "Context"'
        query = data_string + prompt + out_format 

        try:
            # Generate a response from the LLM
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents = query,
                config = types.GenerateContentConfig(
                    tools = [{"google_search": {}}],
                    temperature = temperature,
                    response_mime_type = 'application/json', 
                )
            )
            
            # Convert the response
            results = json.loads(response.text)

            # Merge into the DataFrame
            if results:
                results_df = pd.DataFrame(results)
                enriched_df = enriched_df.merge(results_df, on = 'Ticker', how = 'left')
                enriched_df['Context'] = enriched_df['Context'].fillna('Analysis unavailable.')
            else:
                enriched_df['Context'] = 'Analysis unavailable.'

            return enriched_df
            
        except Exception as e:

            # Handle unsuccessful LLM integration
            print(f'Gemini API Error during analysis: {e}')
            enriched_df['Context'] = 'Analysis unavailable.'
            return enriched_df