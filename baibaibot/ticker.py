"""
A class for a Ticker object.
"""

from typing import Any, Dict


class Ticker:
    """
    A Ticker object.
    """

    def __init__(self):
        pass

    def from_gateio(self, tick: Any) -> None:
        self.ask = float(tick.lowest_ask)
        self.bid = float(tick.highest_bid)
        self.high = float(tick.high_24h)
        self.low = float(tick.low_24h)

    def from_kraken(self, tick: Dict[str, Any]) -> None:
        # a = ask array(<price>, <whole lot volume>, <lot volume>),
        self.ask = float(tick["a"][0])
        # b = bid array(<price>, <whole lot volume>, <lot volume>),
        self.bid = float(tick["b"][0])
        # h = high array(<today>, <last 24 hours>),
        self.high = float(tick["h"][1])
        # l = low array(<today>, <last 24 hours>),
        self.low = float(tick["l"][1])

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
