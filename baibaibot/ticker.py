"""
A class for a Ticker object.
"""

from typing import Any, Dict


class Ticker:
    """
    A Kraken Ticker object.
    """

    def __init__(self, tick: Dict[str, Any]) -> None:
        # a = ask array(<price>, <whole lot volume>, <lot volume>),
        # "a": ["1213.81000", "22", "22.000"],
        self.ask = float(tick["a"][0])
        # b = bid array(<price>, <whole lot volume>, <lot volume>),
        # "b": ["1213.80000", "2", "2.000"],
        self.bid = float(tick["b"][0])
        # c = last trade closed array(<price>, <lot volume>),
        # "c": ["1214.22000", "1.46202958"],
        self.close = float(tick["c"][0])
        # h = high array(<today>, <last 24 hours>),
        # "h": ["1331.25000", "1331.25000"],
        self.high = float(tick["h"][1])
        # l = low array(<today>, <last 24 hours>),
        # "l": ["1210.52000", "1210.52000"],
        self.low = float(tick["l"][1])
        # o = today's opening price
        # "o": "1304.03000",
        self.open = float(tick["o"])
        # p = volume weighted average price array(<today>, <last 24h>),
        # "p": ["1282.29270", "1281.74247"],
        self.vwap = float(tick["p"][1])
        # t = number of trades array(<today>, <last 24 hours>),
        # "t": [22357, 25907],
        self.count = tick["t"][1]
        # v = volume array(<today>, <last 24 hours>),
        # "v": ["35758.54519338", "41744.63351722"]
        self.vol = float(tick["v"][1])

    def header(self) -> str:
        """
        Return a nicely formatted header line.
        """
        ask, bid, opn, hig, low = "Ask", "Bid", "Open", "High", "Low"
        clo, vwa, cnt, vol = "Close", "VWAP", "Count", "Volume"
        return (
            f"{ask:>9s}, {bid:>9s}, {opn:>9s}, {hig:>9s}, {low:>9s}, "
            + f"{clo:>9s}, {vwa:>9s}, {cnt:>9s}, {vol:>10s}"
        )

    def info(self) -> str:
        """
        Return a nicely formatted information line.
        """
        return (
            f"{self.ask:9.3f}, {self.bid:9.3f}, {self.open:9.3f}, "
            + f"{self.high:9.3f}, {self.low:9.3f}, {self.close:9.3f}, "
            + f"{self.vwap:9.3f}, {self.count:9d}, {self.vol:10.2f}"
        )
