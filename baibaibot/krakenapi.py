import datetime
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from .api import API, time_ms_to_str
from .errors import APIError, NotConnectedError
from .kapi import KAPI
from .objects import AssetPair, Order
from .ohlc import OHLC
from .ticker import Ticker

VALIDATE = os.getenv("VALIDATE", "true").lower() != "false"


class KrakenAPI(API):
    krak: Optional[KAPI] = None

    def __init__(self, key="", secret="", logger=None):
        self.key = key
        self.secret = secret
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger("KrakenAPI")
            self.logger.setLevel(logging.INFO)

    def cancel_orders(self) -> None:
        """
        There is no need to cancel orders on Kraken, since GTT orders are used.
        """
        pass

    def connect(self):
        self.krak = KAPI(self.key, self.secret)

    def _query(self, func, query: str, *args, **kwargs) -> Dict[str, Any]:
        self.logger.debug(
            "Query (%s): %s args=%s, kwargs=%s",
            func.__name__,
            query,
            args,
            kwargs,
        )
        t_start = time.monotonic()
        reply = func(query, *args, **kwargs)
        t_end = time.monotonic()
        t_taken = t_end - t_start
        if t_taken > 1.0:
            self.logger.warning("Slow query: %s took %fs", query, t_taken)

        if "result" in reply:
            result = reply["result"]
            # self.logger.debug(
            #     "Result: %s",
            #     json.dumps(result, indent=2, sort_keys=True),
            # )
            time.sleep(self.cfg["inter_apireq_sleep_seconds"])
            return result

        if "error" in reply:
            raise APIError(", ".join(reply["error"]))

        raise APIError("Query failed: " + json.dumps(reply, sort_keys=True))

    def _query_private(self, query: str, *args, **kwargs):
        if self.krak is None:
            raise NotConnectedError()
        return self._query(self.krak.query_private, query, *args, **kwargs)

    def _query_public(self, query: str, *args, **kwargs):
        if self.krak is None:
            raise NotConnectedError()
        return self._query(self.krak.query_public, query, *args, **kwargs)

    def get_asset_pairs(self) -> None:
        self.asset_pairs = {}
        for pair_id, pair in self._query_public("AssetPairs").items():
            self.asset_pairs[pair_id] = AssetPair.from_kraken(pair_id, pair)
            alt = pair["altname"]
            if alt != pair_id:
                self.asset_pairs[alt] = self.asset_pairs[pair_id]

    def get_balances(self) -> None:
        self.balances = {
            key: {"total": float(val), "unencumbered": float(val)}
            for key, val in self._query_private("Balance").items()
        }

    def get_ohlc(self, pair: str) -> OHLC:
        since = datetime.datetime.now(datetime.UTC)
        since -= datetime.timedelta(
            seconds=self.cfg["order_lifespan_seconds"] * 2
        )
        params = {
            "pair": pair,
            "interval": int(self.cfg["order_lifespan_seconds"] / 60),  # mins
            "since": int(since.timestamp()),
        }
        res = self._query_public("OHLC", params)
        ohlc = (OHLC(res[pair][0]), OHLC(res[pair][1]))
        result = ohlc[0].merge(ohlc[1])

        if self.logger.level >= logging.INFO:
            quote = self.asset_pairs[pair].quote
            hdr = result.header()
            inf = result.info()
            self.logger.info("OHLC for %s (in %s): %s", pair, quote, hdr)
            self.logger.info("OHLC for %s (in %s): %s", pair, quote, inf)
        return result

    def get_open_orders(self) -> None:
        api_open_orders: Dict[str, Dict[str, Any]] = {}
        api_open_orders = self._query_private("OpenOrders")["open"]
        open_orders: Dict[str, List[Dict[str, Any]]] = {}
        for orderref, order in api_open_orders.items():
            order["_id"] = orderref
            pair = order["descr"]["pair"]
            if pair in open_orders:
                open_orders[pair].append(order)
            else:
                open_orders[pair] = [order]

            vol = float(order["vol"]) - float(order["vol_exec"])
            pair_or_alt = order["descr"]["pair"]
            pair = self.real_pair(pair_or_alt)
            typ = order["descr"]["type"]
            if typ == "buy":
                # encumber quote
                asset_quote = self.asset_pairs[pair].quote
                amt_quote = vol * float(order["descr"]["price"])
                self.balances[asset_quote]["unencumbered"] -= amt_quote
                self.logger.debug(
                    "Encumbering quote for BUY %10.3f %s for %s",
                    amt_quote,
                    asset_quote,
                    pair,
                )
            elif typ == "sell":
                # encumber base
                asset_base = self.asset_pairs[pair].base
                self.balances[asset_base]["unencumbered"] -= vol
                self.logger.debug(
                    "Encumbering base for SELL %10.3f %s for %s",
                    vol,
                    asset_base,
                    pair,
                )
            else:
                raise APIError(f'Unknown order type "{typ}"')

        for pair, orders in open_orders.items():
            self.logger.debug("Open orders for %s: %d", pair, len(orders))
            for order in orders:
                self.logger.debug(
                    "    %s: %s (%s)",
                    time_ms_to_str(order["opentm"]),
                    order["_id"],
                    order["descr"]["order"],
                )

    def get_ticker(self, pair: str) -> Ticker:
        results = self._query_public("Ticker", {"pair": pair})
        return Ticker.from_kraken(results[pair])

    def real_pair(self, pair: str) -> str:
        return self.asset_pairs[pair].id

    def place_order(
        self,
        pair: str,
        order: Order,
    ) -> Tuple[int, Optional[List[str]], List[str]]:
        # AddOrderBatch not possible
        kraken_order = order.to_kraken()
        kraken_order["pair"] = pair
        kraken_order["validate"] = VALIDATE
        result = self._query_private("AddOrder", data=kraken_order)
        order_txids: Optional[List[str]] = None
        ids = "N/A (validate only)"
        if not VALIDATE:
            order_txids = [result["txid"]]
            ids = order_txids[0]
        self.logger.info(
            "Placed %s order. ID: %s",
            order.side,
            ids,
        )
        return (1, order_txids, [order.side])

    def place_orders_batch(
        self,
        pair: str,
        orders: List[Order],
    ) -> Tuple[int, Optional[List[str]], List[str]]:
        # Returns (count, order_txids, sides)

        # AddOrderBatch has a minimum of 2 and a limit of 15
        req: Dict[str, Any] = {
            # "deadline": "",
            "orders": [order.to_kraken() for order in orders],
            "pair": pair,
        }
        if VALIDATE:
            req["validate"] = VALIDATE
        result = self._query_private("AddOrderBatch", data=req)
        count = len(result["orders"])
        sides = sorted(set(str(order.side) for order in orders))
        errors = [itm["error"] for itm in result["orders"] if "error" in itm]
        if len(errors) > 0:
            errs = ", ".join(errors)
            raise APIError(
                f"Errors placing batch {",".join(sides)} orders: {errs}"
            )
        if count < len(orders):
            self.logger.warning(
                "Some %s orders were not placed: %d < %d: %s",
                ",".join(sorted(set(sides))),
                count,
                len(orders),
                json.dumps(result, sort_keys=True),
            )
        order_txids: Optional[List[str]] = []
        if not VALIDATE:
            order_txids = [item["txid"] for item in result["orders"]]
        return (count, order_txids, sides)

    def place_orders(self, pair: str, orders: List[Order]) -> int:
        total_count = 0
        all_order_txids: List[str] = []
        all_sides: List[str] = []
        for i in range(0, len(orders), 15):
            # AddOrderBatch has a minimum of 2 and a limit of 15
            ords = orders[i : i + 15]
            if len(ords) == 1:
                count, order_txids, sides = self.place_order(pair, ords[0])
            else:
                count, order_txids, sides = self.place_orders_batch(pair, ords)
            total_count += count
            if not VALIDATE and order_txids is not None:
                all_order_txids.extend(order_txids)
            all_sides.extend(sides)

        if VALIDATE:
            ids = "N/A (validate only)"
        else:
            ids = ", ".join(all_order_txids)
        sides_str = ",".join(sorted(set(all_sides)))
        self.logger.info(
            "Placed %d/%d BATCH %s orders. IDs: %s",
            total_count,
            len(orders),
            sides_str,
            ids,
        )
        return count
