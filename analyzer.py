import pandas
import numpy

class Analyzer:
    """Handles price, distribution, and volatility math."""
    def __init__(self, data):
        self.data = data

    def check_price_drop_condition(self, ticker: str) -> bool:
        """
        Calculates if drop > 20% OR drop < 0.15th percentile of historical returns.
        """
        # 1. Fetch historical and current prices
        # 2. Calculate daily returns distribution
        # 3. Calculate 0.15th percentile threshold
        # 4. Return True if current drop breaches either condition
        pass

    def check_high_iv(self, ticker: str, iv_rank_threshold: float = 80.0) -> bool:
        """
        Calculates IV Rank (IVR) based on historical IV vs current IV.
        """
        pass