"""
A class for a Ticker object.
"""

from typing import Any, Dict

import gate_api


class Ticker:
    """
    A Ticker object.
    """

    ask = 0.0
    bid = 0.0
    high = 0.0
    low = 0.0

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @classmethod
    def from_gateio(cls, tick: gate_api.Ticker) -> "Ticker":
        """
        Create a Ticker object from a gate.io API response.
        """
        return Ticker(
            ask=float(tick.lowest_ask),
            bid=float(tick.highest_bid),
            high=float(tick.high_24h),
            low=float(tick.low_24h),
        )

    @classmethod
    def from_kraken(cls, tick: Dict[str, Any]) -> "Ticker":
        """
        Create a Ticker object from a Kraken API response.
        """
        return Ticker(
            # a = ask array(<price>, <whole lot volume>, <lot volume>),
            ask=float(tick["a"][0]),
            # b = bid array(<price>, <whole lot volume>, <lot volume>),
            bid=float(tick["b"][0]),
            # h = high array(<today>, <last 24 hours>),
            high=float(tick["h"][1]),
            # l = low array(<today>, <last 24 hours>),
            low=float(tick["l"][1]),
        )

    def header(self) -> str:
        """
        Return a nicely formatted header line.
        """
        ask, bid, hig, low = "Ask", "Bid", "High", "Low"
        return f"{ask:>9s}, {bid:>9s}, {hig:>9s}, {low:>9s}"

    def info(self) -> str:
        """
        Return a nicely formatted information line.
        """
        return (
            f"{self.ask:9.3f}, {self.bid:9.3f}, "
            f"{self.high:9.3f}, {self.low:9.3f}"
        )
