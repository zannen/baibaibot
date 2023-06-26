import logging
import time
from typing import Any, Dict, List, Optional

# https://github.com/gateio/gateapi-python
import gate_api

from .api import API, time_ms_to_str
from .errors import NotConnectedError
from .objects import AssetPair, Order
from .ticker import Ticker


class GateIOAPI(API):
    gate: Optional[gate_api.SpotApi] = None

    # pair -> list of open order IDs
    open_order_ids: Dict[str, List[str]] = {}

    def __init__(self, key="", secret="", logger=None):
        self.key = key
        self.secret = secret
        self.gate = None
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger("GateIOAPI")
            self.logger.setLevel(logging.INFO)

    def cancel_orders(self) -> None:
        """
        GTC orders are used on gate.io, so they must be cancelled.
        """
        if self.gate is None:
            raise NotConnectedError()
        for market in self.cfg["markets"]:
            pair = self.real_pair(market["pair"])
            if (
                pair not in self.open_order_ids
                or len(self.open_order_ids[pair]) == 0
            ):
                self.logger.info("No orders to cancel for %s", pair)
                continue
            self.logger.info(
                "Cancelling orders for %s: [%s]",
                pair,
                ", ".join(self.open_order_ids[pair]),
            )
            cancel_orders = [
                gate_api.CancelOrder(
                    currency_pair=pair,
                    id=order_id,
                )
                for order_id in self.open_order_ids[pair]
            ]
            self.gate.cancel_batch_orders(cancel_orders)
            self.open_order_ids[pair] = []

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
        self.asset_pairs = {
            pair.id: AssetPair.from_gateio(pair)
            for pair in self.gate.list_currency_pairs()
        }

    def get_balances(self) -> None:
        if self.gate is None:
            raise NotConnectedError()
        self.balances = {
            acc.currency: {
                "total": float(acc.available),
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
                    # self.balances[asset_quote]["unencumbered"] -= amt_quote
                    self.logger.debug(
                        "Quote is encumbered for BUY %10.3f %s for %s",
                        amt_quote,
                        asset_quote,
                        order.currency_pair,
                    )
                elif order.side == "sell":
                    # encumber base
                    asset_base = self.asset_pairs[order.currency_pair].base
                    # self.balances[asset_base]["unencumbered"] -= vol
                    self.logger.debug(
                        "Base is encumbered for SELL %10.3f %s for %s",
                        vol,
                        asset_base,
                        order.currency_pair,
                    )

        for pair, orders in open_orders.items():
            self.logger.debug("Open orders for %s: %d", pair, len(orders))
            for order in orders:
                self.logger.debug(
                    "    %s: %s (%s)",
                    time_ms_to_str(order.create_time),
                    order.id,
                    order_info(order),
                )

    def get_ticker(self, pair: str) -> Ticker:
        if self.gate is None:
            raise NotConnectedError()
        results = self.gate.list_tickers(currency_pair=pair)[0]
        return Ticker.from_gateio(results)

    def place_orders(self, pair: str, orders: List[Order]) -> int:
        if self.gate is None:
            raise NotConnectedError()
        if pair not in self.open_order_ids:
            self.open_order_ids[pair] = []
        asset_pair = self.asset_pairs[pair]

        count = 0
        for order in orders:
            ope, clo = order.to_gateio(
                pair,
                asset_pair,
                self.cfg["order_lifespan_seconds"],
            )
            ope_resp = self.gate.create_order(ope)
            self.open_order_ids[pair].append(str(ope_resp.id))
            self.logger.info(
                "Created Open  order ID %s: %s %s %s @%s %s",
                ope_resp.id,
                ope.side,
                ope.amount,
                asset_pair.base,
                ope.price,
                asset_pair.quote,
            )
            time.sleep(self.cfg["inter_apireq_sleep_seconds"])
            if clo is not None:
                clo_resp = self.gate.create_spot_price_triggered_order(clo)
                # no need to add the closing order to the open_order_ids list,
                # since the closing orders expire.
                # self.open_order_ids[pair].append(str(clo_resp.id))
                self.logger.info(
                    "Created Close order ID %s: %s %s %s @%s %s "
                    "[if price %s %s %s]",
                    clo_resp.id,
                    clo.put.side,
                    clo.put.amount,
                    asset_pair.base,
                    clo.put.price,
                    asset_pair.quote,
                    clo.trigger.rule,
                    clo.trigger.price,
                    asset_pair.quote,
                )
                time.sleep(self.cfg["inter_apireq_sleep_seconds"])
                count += 1

        return count


def order_info(order: Any) -> str:
    return (
        f"{order.side} {order.left} {order.currency_pair} "
        f"@ {order.type} {order.price}"
    )
