import datetime
import json
import logging
import math
import time
from typing import Any, Dict, List, Optional, Union

from .api import API
from .errors import NotConnectedError
from .kapi import KAPI
from .objects import AssetPair
from .ohlc import OHLC
from .ticker import Ticker

VALIDATE = "true"


class KrakenAPI(API):
    krak: Optional[Any] = None  # TODO

    inter_apireq_sleep_seconds = 0.0
    order_lifespan_seconds = 0.0

    def __init__(self, key="", secret="", logger=None):
        self.key = key
        self.secret = secret
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger("KrakenAPI")
            self.logger.setLevel(logging.INFO)

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
            time.sleep(self.inter_apireq_sleep_seconds)  # avoid rate limit
            return result

        if "error" in reply:
            raise Exception(", ".join(reply["error"]))

        raise Exception("Query failed: " + json.dumps(reply, sort_keys=True))

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
        pairs = self._query_public("AssetPairs")
        for pair_id, pair in pairs.items():
            self.asset_pairs[pair_id] = AssetPair.from_kraken(pair_id, pair)
            alt = pair["altname"]
            if alt != pair_id:
                # self.logger.debug("alias %s->%s", alt, pair_id)
                self.asset_pairs[alt] = self.asset_pairs[pair_id]

    def get_balances(self) -> None:
        self.balances = {
            k: {"total": float(v), "unencumbered": float(v)}
            for k, v in self._query_private("Balance").items()
        }

    def get_ohlc(self, pair: str) -> OHLC:
        since = datetime.datetime.utcnow()
        since -= datetime.timedelta(
            seconds=self.cfg["order_lifespan_seconds"] * 2
        )
        params = {
            "pair": pair,
            "interval": int(self.cfg["order_lifespan_seconds"] / 60),  # mins
            "since": int(since.timestamp()),
        }
        r = self._query_public("OHLC", params)
        ohlc = (OHLC(r[pair][0]), OHLC(r[pair][1]))
        result = ohlc[0].merge(ohlc[1])

        quote = self.asset_pairs[pair].quote
        hdr = result.header()
        inf = result.info()
        self.logger.info("OHLC for %s (in %s): %s", pair, quote, hdr)
        self.logger.info("OHLC for %s (in %s): %s", pair, quote, inf)
        return result

    def get_open_orders(self) -> None:
        oo: Dict[str, Dict[str, Any]] = {}
        oo = self._query_private("OpenOrders")["open"]
        self.logger.info("Open orders: %d", len(oo))
        open_orders: Dict[str, List[Dict[str, Any]]] = {}
        for orderref, order in oo.items():
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
                raise Exception(f'Unknown order type "{typ}"')

        for pair, orders in open_orders.items():
            self.logger.debug("Orders for %s:", pair)
            for order in orders:
                self.logger.debug(
                    "    %s: %s (%s)",
                    order_open_time(order),
                    order["_id"],
                    order["descr"]["order"],
                )

    def get_ticker(self, pair: str) -> Ticker:
        results = self._query_public("Ticker", {"pair": pair})
        ticker = Ticker()
        ticker.from_kraken(results[pair])
        quote = self.asset_pairs[pair].quote
        hdr = ticker.header()
        inf = ticker.info()
        self.logger.info("Ticker for %s (in %s): %s", pair, quote, hdr)
        self.logger.info("Ticker for %s (in %s): %s", pair, quote, inf)
        return ticker

    def print_trade_summary(
        self,
        order: Dict[str, Any],
        market: Dict[str, Any],
    ):
        pair = self.real_pair(market["pair"])
        c_base = self.asset_pairs[pair].base
        c_quote = self.asset_pairs[pair].quote

        quantity_base = float(order["volume"])
        open_price_quote = float(order["price"])
        open_cost = quantity_base * open_price_quote
        open_fee = open_cost * self.cfg["fee_percent"] / 100.0

        self.logger.info(
            "Open  Trade: %4s %9.4f %5s for %7.2f %4s (%8.3f %s/%s) fee %6.3f "
            "%4s",
            order["type"],
            quantity_base,
            c_base,
            open_cost,
            c_quote,
            open_price_quote,
            c_quote,
            c_base,
            open_fee,
            c_quote,
        )

        if "close" not in order:
            return

        close_price_quote = float(order["close"]["price"])
        close_cost = quantity_base * close_price_quote
        close_fee = close_cost * self.cfg["fee_percent"] / 100.0
        gross_profit = close_cost - open_cost
        if order["type"] == "sell":
            gross_profit *= -1
        net_profit = gross_profit - open_fee - close_fee
        percent_fee = 100.0 - net_profit * 100.0 / gross_profit

        self.logger.info(
            "Close Trade: %4s %s for %7.2f %4s (%8.3f %s/%s) fee %6.3f %s ("
            "Gross profit %6.2f %4s (%5.2f%%) Net profit %6.2f %4s (%5.2f%%) "
            "Fee as percentage of profit %5.2f%%)",
            order["close"]["type"],
            " " * 15,
            close_cost,
            c_quote,
            close_price_quote,
            c_quote,
            c_base,
            close_fee,
            c_quote,
            gross_profit,
            c_quote,
            gross_profit * 100.0 / close_cost,
            net_profit,
            c_quote,
            net_profit * 100.0 / open_cost,
            percent_fee,
        )

    def real_pair(self, pair: str) -> str:
        return self.asset_pairs[pair].id

    def tick_sell_batch(self, market: Dict[str, Any], ticker: Ticker) -> int:
        # SELL
        # ticker.high: 24h
        # ohlc.high: last 15~30 mins
        sell_order_count = market["sell"]["order_count"]
        if sell_order_count == 0:
            return 0

        pair = self.real_pair(market["pair"])
        asset_pair = self.asset_pairs[pair]
        c_base = asset_pair.base
        dp_base = asset_pair.dp_base
        dp_quote = asset_pair.dp_quote

        self.logger.info("--- Sell %s ---", pair)
        bal_base = self.balances[c_base]["unencumbered"]
        if bal_base < 0.001:
            raise Exception(
                f"{pair}: Not enough unencumbered {c_base} to place SELL "
                f"orders: {bal_base} < 0.001"
            )

        self.logger.info(
            "Balance: %10.3f %s, %10.3f %s unencumbered",
            self.balances[c_base]["total"],
            c_base,
            bal_base,
            c_base,
        )
        vol_total = sum(math.sqrt(i) for i in range(1, sell_order_count + 1))
        vol_p = market["sell"]["vol_percent"]
        vol_mul = bal_base / vol_total * vol_p / 100.0
        self.logger.info(
            "Sell: order_count=%d, vol_total=%f, bal=%f %s, vol_percent=%f, "
            "vol_mul=%f",
            sell_order_count,
            vol_total,
            bal_base,
            c_base,
            vol_p,
            vol_mul,
        )
        base_price = ticker.high
        orders: List[Dict[str, Union[str, Dict[str, str]]]] = []
        for n in range(1, sell_order_count + 1):
            pcnt_bump_sell = (
                market["sell"]["pcnt_bump_a"] * n**2
                + market["sell"]["pcnt_bump_c"]
            )
            p_sell = round(base_price * (1 + pcnt_bump_sell / 100), dp_quote)
            p_buy = round(
                p_sell * (1.0 - market["sell"]["rebuy_bump_percent"] / 100.0),
                dp_quote,
            )

            vol_sell = round(vol_mul * math.sqrt(n), dp_base)
            order: Dict[str, Union[str, Dict[str, str]]] = {
                # https://www.kraken.com/en-gb/features/api#add-standard-order
                # "userref": 0,  # int32
                "ordertype": "limit",
                "type": "sell",
                "volume": str(vol_sell),
                # "displayvol": "",
                "price": str(p_sell),
                # "price2": "",
                # "trigger": "",
                # "leverage": "",
                "stptype": "cancel-newest",
                "oflags": "fciq",
                "timeinforce": "GTD",
                "starttm": "0",  # now
                "expiretm": f"+{self.cfg['order_lifespan_seconds']}",
                "close": {
                    "ordertype": "limit",
                    "type": "buy",
                    "price": str(p_buy),
                    # "price2": "",
                },
            }
            self.print_trade_summary(order, market)
            orders.append(order)

        count = self.place_orders(pair, orders)
        time.sleep(self.inter_apireq_sleep_seconds)  # avoid rate limit
        return count

    def tick_buy_batch(self, market: Dict[str, Any], ticker: Ticker) -> int:
        # BUY
        # ticker.low: 24h
        # ohlc.low: last 15~30 mins
        buy_order_count = market["buy"]["order_count"]
        if buy_order_count == 0:
            return 0

        pair = self.real_pair(market["pair"])
        asset_pair = self.asset_pairs[pair]
        c_base = asset_pair.base
        c_quote = asset_pair.quote
        dp_base = asset_pair.dp_base
        dp_quote = asset_pair.dp_quote

        self.logger.info("--- Buy %s ---", pair)
        bal_quote = self.balances[c_quote]["unencumbered"]
        bal_base = bal_quote / ticker.bid
        self.logger.info(
            "Balance: %10.3f %s, %10.3f %s (approx %10.3f %s) unencumbered",
            self.balances[c_quote]["total"],
            c_quote,
            bal_quote,
            c_quote,
            bal_base,
            c_base,
        )
        vol_total = sum(math.sqrt(i) for i in range(1, buy_order_count + 1))
        vol_p = market["buy"]["vol_percent"]
        vol_mul = bal_base / vol_total * vol_p / 100.0

        self.logger.info(
            "Buy: order_count=%d, vol_total=%f, amount_quote=%f %s, "
            "amount_base=%f %s, vol_mul=%f",
            buy_order_count,
            vol_total,
            bal_quote,
            c_quote,
            bal_base,
            c_base,
            vol_mul,
        )
        base_price = ticker.low
        orders: List[Dict[str, Union[str, Dict[str, str]]]] = []
        for n in range(1, buy_order_count + 1):
            pcnt_bump_buy = (
                market["buy"]["pcnt_bump_a"] * n**2
                + market["buy"]["pcnt_bump_c"]
            )
            p_buy = round(base_price * (1 - pcnt_bump_buy / 100), dp_quote)
            p_sell = round(
                p_buy * (1.0 + market["buy"]["resell_bump_percent"] / 100.0),
                dp_quote,
            )

            vol_buy = round(vol_mul * math.sqrt(n), dp_base)

            order: Dict[str, Union[str, Dict[str, str]]] = {
                # https://www.kraken.com/en-gb/features/api#add-standard-order
                # "userref": 0,  # int32
                "ordertype": "limit",
                "type": "buy",
                "volume": str(vol_buy),
                # "displayvol": "",
                "price": str(p_buy),
                # "price2": "",
                # "trigger": "",
                # "leverage": "",
                "stptype": "cancel-newest",
                "oflags": "fciq",
                "timeinforce": "GTD",
                "starttm": "0",  # now
                "expiretm": f"+{self.cfg['order_lifespan_seconds']}",
                "close": {
                    "ordertype": "limit",
                    "type": "sell",
                    "price": str(p_sell),
                    # "price2": "",
                },
            }
            orders.append(order)
            self.print_trade_summary(order, market)

        count = self.place_orders(pair, orders)
        return count

    def place_orders(
        self,
        pair: str,
        orders: List[Dict[str, Union[str, Dict[str, str]]]],
    ) -> int:
        if len(orders) == 1:
            # AddOrderBatch not possible
            orders[0]["pair"] = pair
            orders[0]["validate"] = VALIDATE
            result = self._query_private("AddOrder", data=orders[0])
            if VALIDATE == "false":
                ids = ", ".join(result["txid"])
            else:
                ids = "N/A (validate only)"
            self.logger.info(
                "Placed %s order. ID: %s",
                orders[0]["type"],
                ids,
            )
            return 1

        # Use AddOrderBatch
        req: Dict[str, Any] = {
            # "deadline": "",
            "orders": orders,
            "pair": pair,
            "validate": VALIDATE,
        }
        expected = len(orders)
        result = self._query_private("AddOrderBatch", data=req)
        count = len(result["orders"])
        types = ",".join(sorted(set([str(i["type"]) for i in orders])))
        errors = [itm["error"] for itm in result["orders"] if "error" in itm]
        if len(errors) > 0:
            raise Exception(
                f"Errors placing batch {types} orders: " + ", ".join(errors)
            )
        if VALIDATE == "false":
            ids = ", ".join(item["txid"] for item in result["orders"])
        else:
            ids = "N/A (validate only)"
        self.logger.info(
            "Placed %d/%d BATCH %s orders. IDs: %s",
            count,
            expected,
            types,
            ids,
        )
        if count < expected:
            self.logger.warning(
                "Some %s orders were not placed: %d < %d: %s",
                types,
                count,
                expected,
                json.dumps(result, sort_keys=True),
            )
        return count


def order_open_time(order: Dict[str, Any]) -> str:
    optm = float(order["opentm"])
    opentime = datetime.datetime.utcfromtimestamp(optm).replace(microsecond=0)
    return opentime.isoformat().replace("T", " ")
