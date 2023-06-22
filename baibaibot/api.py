import os
import traceback
from typing import Any, Dict

from .objects import AssetPair
from .ticker import Ticker


class SubclassError(Exception):
    def __init__(self, message):
        super().__init__("to be implemented in a subclass")


class API:
    # asset_pair ID or altname -> asset_pair dict
    asset_pairs: Dict[str, AssetPair] = {}

    # asset -> dict of total and unencumbered balances
    balances: Dict[str, Dict[str, float]] = {}

    def get_asset_pairs(self) -> None:
        raise SubclassError()

    def get_balances(self) -> None:
        raise SubclassError()

    def get_open_orders(self) -> None:
        raise SubclassError()

    def print_all_balances(self):
        self.logger.info("Balances: total (unencumbered)")
        for asset in sorted(self.balances.keys()):
            amt = self.balances[asset]["total"]
            if amt < 0.0001:
                continue
            unenc = self.balances[asset]["unencumbered"]
            self.logger.info(
                "Balance: %10.3f (%10.3f or %6.2f%%) %s",
                amt,
                unenc,
                unenc / amt * 100.0,
                asset,
            )

    def real_pair(self, pair: str) -> str:
        return pair

    def tick(self) -> None:
        for market in self.cfg["markets"]:
            try:
                self.tick_market(market)
            except Exception:
                self.logger.warning(
                    "Caught exception while placing orders for %s.%s%s",
                    market["pair"],
                    os.linesep,
                    traceback.format_exc(),
                )

    def tick_market(self, market: Dict[str, Any]) -> int:
        pair = self.real_pair(market["pair"])
        self.logger.info("=== %s ===", pair)

        ticker = self.get_ticker(pair)

        for k, minval in market["min"].items():
            val = getattr(ticker, k)
            if val < minval:
                self.logger.warning(
                    "No orders for %s. %s=%f, min=%f", pair, k, val, minval
                )
                return 0

        order_count = self.tick_sell_batch(market, ticker)
        order_count += self.tick_buy_batch(market, ticker)
        return 0  # order_count

    def tick_sell_batch(self, market: Dict[str, Any], ticker: Ticker) -> int:
        raise SubclassError()

    def tick_buy_batch(self, market: Dict[str, Any], ticker: Ticker) -> int:
        raise SubclassError()
