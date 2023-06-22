import datetime
import logging
from typing import Any, Dict, Optional

# https://github.com/gateio/gateapi-python
import gate_api

from .api import API
from .errors import NotConnectedError
from .objects import AssetPair
from .ticker import Ticker


class GateIOAPI(API):
    gate: Optional[Any] = None  # TODO

    def __init__(self, key="", secret="", logger=None):
        self.key = key
        self.secret = secret
        self.gate = None
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger("GateIOAPI")
            self.logger.setLevel(logging.INFO)

    def connect(self) -> None:
        conf = gate_api.Configuration(
            host="https://api.gateio.ws/api/v4",
            key=self.key,
            secret=self.secret,
        )
        cli = gate_api.ApiClient(conf)
        self.gate = gate_api.SpotApi(cli)

    def get_asset_pairs(self) -> None:
        if self.gate is None:
            raise NotConnectedError()
        self.asset_pairs = {}
        pairs = self.gate.list_currency_pairs()
        for pair in pairs:
            self.asset_pairs[pair.id] = AssetPair(
                exchange="gate.io",
                id=pair.id,
                base=pair.base,
                quote=pair.quote,
                dp_base=pair.amount_precision,
                dp_quote=pair.precision,
            )

    def get_balances(self) -> None:
        if self.gate is None:
            raise NotConnectedError()
        self.balances = {
            acc.currency: {
                "total": float(acc.available) - float(acc.locked),
                "unencumbered": float(acc.available) - float(acc.locked),
            }
            for acc in self.gate.list_spot_accounts()
        }

    def get_open_orders(self) -> None:
        if self.gate is None:
            raise NotConnectedError()
        open_orders: Dict[str, gate_api.Order] = {}
        for market in self.cfg["markets"]:
            open_orders[market["pair"]] = []
            for order in self.gate.list_orders(market["pair"], "open"):
                open_orders[market["pair"]].append(order)
                vol = float(order.left)  # remaining to be filled
                if order.side == "buy":
                    # encumber quote
                    asset_quote = self.asset_pairs[order.currency_pair].quote
                    amt_quote = vol * float(order.price)
                    self.balances[asset_quote]["unencumbered"] -= amt_quote
                    self.logger.debug(
                        "Encumbering quote for BUY %10.3f %s for %s",
                        amt_quote,
                        asset_quote,
                        order.currency_pair,
                    )
                elif order.side == "sell":
                    # encumber base
                    asset_base = self.asset_pairs[order.currency_pair].base
                    self.balances[asset_base]["unencumbered"] -= vol
                    self.logger.debug(
                        "Encumbering base for SELL %10.3f %s for %s",
                        vol,
                        asset_base,
                        order.currency_pair,
                    )

        for pair, orders in open_orders.items():
            self.logger.debug("Orders for %s:", pair)
            for order in orders:
                self.logger.debug(
                    "    %s: %s (%s)",
                    order_open_time(order),
                    order.id,
                    order_info(order),
                )

    def get_ticker(self, pair: str) -> Ticker:
        if self.gate is None:
            raise NotConnectedError()
        results = self.gate.list_tickers(currency_pair=pair)[0]
        ticker = Ticker()
        ticker.from_gateio(results)
        quote = self.asset_pairs[pair].quote
        hdr = ticker.header()
        inf = ticker.info()
        self.logger.info("Ticker for %s (in %s): %s", pair, quote, hdr)
        self.logger.info("Ticker for %s (in %s): %s", pair, quote, inf)
        return ticker

    def tick_sell_batch(self, market: Dict[str, Any], ticker: Ticker) -> int:
        return 0

    def tick_buy_batch(self, market: Dict[str, Any], ticker: Ticker) -> int:
        return 0


def order_open_time(order: Any) -> str:
    optm = float(order.create_time)
    opentime = datetime.datetime.utcfromtimestamp(optm).replace(microsecond=0)
    return opentime.isoformat().replace("T", " ")


def order_info(order: Any) -> str:
    return (
        f"{order.side} {order.left} {order.currency_pair} "
        f"@ {order.type} {order.price}"
    )
