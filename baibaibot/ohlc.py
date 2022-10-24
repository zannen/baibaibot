"""
A class for an Open-High-Low-Close object.
"""

import datetime
from typing import List, Union


class OHLC:
    """
    A Kraken Open-High-Low-Close object.
    """

    def __init__(self, ohlc: List[Union[float, int, str]]) -> None:
        if isinstance(ohlc[0], (float, int)):
            self.time = datetime.datetime.fromtimestamp(ohlc[0])
        else:
            raise TypeError(f"time not float/int: {type(ohlc[0])}")

        self.open = self.high = self.low = self.close = 0.0
        self.vwap = self.vol = 0.0
        attrs = ["open", "high", "low", "close", "vwap", "vol"]
        for i in range(len(attrs)):
            if isinstance(ohlc[i + 1], (float, str)):
                setattr(self, attrs[i], float(ohlc[i + 1]))
            else:
                raise TypeError(f"{attrs[i]} not float/str: {type(ohlc[i+1])}")

        if isinstance(ohlc[7], int):
            self.count = ohlc[7]
        else:
            raise TypeError("count not int")

    def header(self) -> str:
        """
        Return a nicely formatted header line.
        """
        tim, opn, hig, low, clo = "Time", "Open", "High", "Low", "Close"
        vwa, cnt, vol = "VWAP", "Count", "Volume"
        return (
            f"{tim:20s}, {opn:8s}, {hig:8s}, {low:8s}, {clo:8s}, "
            + f"{vwa:8s}, {cnt:8s}, {vol:9s}"
        )

    def info(self) -> str:
        """
        Return a nicely formatted information line.
        """
        tim = self.time.strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"{tim:20s}, {self.open:8.3f}, {self.high:8.3f}, "
            + f"{self.low:8.3f}, {self.close:8.3f}, {self.vwap:8.3f}, "
            + f"{self.count:8d}, {self.vol:9.2f}"
        )

    def merge(self, other: "OHLC") -> "OHLC":
        """
        Merge this OHLC with another.
        """
        first = self
        second = other

        if second.time < first.time:
            first, second = second, first
        # first is before second.

        vol = first.vol + second.vol
        vwap = float("inf")
        if vol > 0:
            vwap = (first.vwap * first.vol + second.vwap * second.vol) / vol

        return OHLC(
            [
                first.time.timestamp(),
                first.open,
                max(first.high, second.high),
                min(first.low, second.low),
                second.close,
                vwap,
                vol,
                first.count + second.count,
            ]
        )
