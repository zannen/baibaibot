"""
BaiBaiBot: A simple Kraken trading bot.
"""

import datetime
import json
import logging
import math
import os
import time
import traceback
from typing import Any, Dict, List, Optional, Union

from .kapi import KAPI
from .ohlc import OHLC
from .ticker import Ticker

VALIDATE = "false"


class Bot:

    # asset_pair ID or altname -> asset_pair dict
    asset_pairs: Dict[str, Dict[str, Any]] = {}

    # asset -> dict of total and unencumbered balances
    balances: Dict[str, Dict[str, float]] = {}

    configfile = ""
    k: Optional[Any] = None  # TODO
    keyfile = ""

    # pair -> list of order dicts
    open_orders: Dict[str, List[Dict[str, Any]]] = {}

    # From config
    fee_percent = 0.0
    inter_apireq_sleep_seconds = 0.0
    loglevel = ""
    order_lifespan_seconds = 0
    markets: List[Dict[str, Any]] = []

    def __init__(self, configfile: str, keyfile: str):
        self.configfile = configfile
        self.keyfile = keyfile
        logging.basicConfig(format="%(asctime)-15s %(levelname)s %(message)s ")
        self.logger = logging.getLogger("BaiBaiBot")
        self.logger.setLevel(logging.INFO)

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
            self.logger.debug("Result: %s", json.dumps(result, sort_keys=True))
            time.sleep(self.inter_apireq_sleep_seconds)  # avoid rate limit
            return result

        if "error" in reply:
            raise Exception(", ".join(reply["error"]))

        raise Exception("Query failed: " + json.dumps(reply, sort_keys=True))

    def _query_private(self, query: str, *args, **kwargs):
        return self._query(self.krak.query_private, query, *args, **kwargs)

    def _query_public(self, query: str, *args, **kwargs):
        return self._query(self.krak.query_public, query, *args, **kwargs)

    def connect(self) -> None:
        self.krak = KAPI()
        self.krak.load_key(self.keyfile)

    def get_balances(self) -> None:
        self.balances = {
            k: {"total": float(v), "unencumbered": float(v)}
            for k, v in self._query_private("Balance").items()
        }

    def get_asset_pairs(self) -> None:
        asset_pairs: Dict[str, Dict[str, Any]] = {}
        asset_pairs = self._query_public("AssetPairs")
        self.asset_pairs = {}
        for pair_id, asset_pair in asset_pairs.items():
            asset_pair["_id"] = pair_id
            self.asset_pairs[pair_id] = asset_pair
            alt = asset_pair["altname"]
            if alt != pair_id:
                self.logger.debug(
                    "get_asset_pairs: Adding alias %s for %s",
                    alt,
                    pair_id,
                )
                self.asset_pairs[alt] = asset_pair

    def get_ohlc(self, pair: str) -> OHLC:
        since = datetime.datetime.utcnow()
        since -= datetime.timedelta(seconds=self.order_lifespan_seconds * 2)
        params = {
            "pair": pair,
            "interval": int(self.order_lifespan_seconds / 60),  # minutes
            "since": int(since.timestamp()),
        }
        r = self._query_public("OHLC", params)
        ohlc = (OHLC(r[pair][0]), OHLC(r[pair][1]))
        result = ohlc[0].merge(ohlc[1])

        quote = self.asset_pairs[pair]["quote"]
        hdr = result.header()
        inf = result.info()
        self.logger.info("OHLC for %s (in %s): %s", pair, quote, hdr)
        self.logger.info("OHLC for %s (in %s): %s", pair, quote, inf)
        return result

    def get_open_orders(self):
        oo: Dict[str, Dict[str, Any]] = {}
        oo = self._query_private("OpenOrders")["open"]
        self.logger.info("Open orders: %d", len(oo))
        self.open_orders = {}
        for orderref, order in oo.items():
            order["_id"] = orderref
            pair = order["descr"]["pair"]
            if pair in self.open_orders:
                self.open_orders[pair].append(order)
            else:
                self.open_orders[pair] = [order]

            vol = float(order["vol"]) - float(order["vol_exec"])
            pair_or_alt = order["descr"]["pair"]
            pair = self.real_pair(pair_or_alt)
            typ = order["descr"]["type"]
            if typ == "buy":
                # encumber quote
                asset_quote = self.asset_pairs[pair]["quote"]
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
                asset_base = self.asset_pairs[pair]["base"]
                self.balances[asset_base]["unencumbered"] -= vol
                self.logger.debug(
                    "Encumbering base for SELL %10.3f %s for %s",
                    vol,
                    asset_base,
                    pair,
                )
            else:
                raise Exception(f'Unknown order type "{typ}"')

        for pair, orders in self.open_orders.items():
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
        ticker = Ticker(results[pair])
        quote = self.asset_pairs[pair]["quote"]
        hdr = ticker.header()
        inf = ticker.info()
        self.logger.info("Ticker for %s (in %s): %s", pair, quote, hdr)
        self.logger.info("Ticker for %s (in %s): %s", pair, quote, inf)
        return ticker

    def load_cfg(self):
        cfg = json.load(open(self.configfile, "r"))
        for attrname in [
            "fee_percent",
            "inter_apireq_sleep_seconds",
            "loglevel",
            "order_lifespan_seconds",
            "markets",
        ]:
            setattr(self, attrname, cfg[attrname])
        self.logger.setLevel(self.loglevel)

    def loop(self):
        while True:
            self.load_cfg()
            self.connect()
            self.get_asset_pairs()
            self.get_balances()
            self.get_open_orders()
            for market in self.markets:
                try:
                    _ = self.tick(market)
                except Exception:
                    self.logger.warning(
                        "Caught exception while placing orders for %s.%s%s",
                        market["pair"],
                        os.linesep,
                        traceback.format_exc(),
                    )
            self.get_balances()
            self.get_open_orders()
            self.print_all_balances()

            sleep_time = self.order_lifespan_seconds
            self.logger.info("Sleeping for %d seconds", sleep_time)
            time.sleep(sleep_time)

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

    def print_trade_summary(
        self,
        order: Dict[str, Any],
        market: Dict[str, Any],
    ):
        pair = self.real_pair(market["pair"])
        c_base = self.asset_pairs[pair]["base"]
        c_quote = self.asset_pairs[pair]["quote"]

        quantity_base = float(order["volume"])
        open_price_quote = float(order["price"])
        open_cost = quantity_base * open_price_quote
        open_fee = open_cost * self.fee_percent / 100.0

        self.logger.info(
            "Open  Trade: %4s %9.4f %4s for %7.2f %4s (%8.3f %s/%s) fee %6.3f "
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
        close_fee = close_cost * self.fee_percent / 100.0
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
            " " * 14,
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
        return self.asset_pairs[pair]["_id"]

    def tick(self, market: Dict[str, Any]) -> int:
        pair = self.real_pair(market["pair"])
        self.logger.info("=== %s ===", pair)

        # ohlc = self.get_ohlc(pair)
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
        return order_count

    def tick_sell_batch(self, market: Dict[str, Any], ticker: Ticker) -> int:
        # SELL
        # ticker.high: 24h
        # ohlc.high: last 15~30 mins
        sell_order_count = market["sell"]["order_count"]
        if sell_order_count == 0:
            return 0

        pair = self.real_pair(market["pair"])
        asset_pair = self.asset_pairs[pair]
        c_base = asset_pair["base"]
        dp_base = asset_pair["lot_decimals"]
        dp_quote = asset_pair["pair_decimals"]

        self.logger.info("--- Sell %s ---", pair)
        bal = self.balances[c_base]["unencumbered"]
        if bal < 0.001:
            raise Exception(
                f"{pair}: Not enough unencumbered {c_base} to place SELL "
                f"orders: {bal} < 0.001"
            )

        self.logger.info(
            "Balance: %10.3f (%10.3f unencumbered) %s",
            self.balances[c_base]["total"],
            bal,
            c_base,
        )
        vol_total = sum(math.sqrt(i) for i in range(1, sell_order_count + 1))
        vol_p = market["sell"]["vol_percent"]
        vol_mul = bal / vol_total * vol_p / 100.0
        self.logger.info(
            "Sell: order_count=%d, vol_total=%f, bal=%f %s, vol_percent=%f, "
            "vol_mul=%f",
            sell_order_count,
            vol_total,
            bal,
            c_base,
            vol_p,
            vol_mul,
        )
        base_price = max(ticker.ask, ticker.vwap, ticker.high)
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
                "expiretm": f"+{self.order_lifespan_seconds}",
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
        c_base = asset_pair["base"]
        c_quote = asset_pair["quote"]
        dp_base = asset_pair["lot_decimals"]
        dp_quote = asset_pair["pair_decimals"]

        self.logger.info("--- Buy %s ---", pair)
        bal = self.balances[c_quote]["unencumbered"]
        self.logger.info(
            "Balance: %10.3f (%10.3f unencumbered) %s",
            self.balances[c_quote]["total"],
            bal,
            c_quote,
        )
        amt_quote = market["buy"]["amount"]
        if amt_quote > bal:
            raise Exception(
                f"{pair}: Not enough unencumbered {c_quote} to place BUY "
                f"orders: {amt_quote} > {bal}"
            )
        vol_total = sum(math.sqrt(i) for i in range(1, buy_order_count + 1))
        amt_base = amt_quote / ticker.bid
        vol_mul = amt_base / vol_total
        self.logger.info(
            "Buy: order_count=%d, vol_total=%f, amount_quote=%f %s, "
            "amount_base=%f %s, vol_mul=%f",
            buy_order_count,
            vol_total,
            amt_quote,
            c_quote,
            amt_base,
            c_base,
            vol_mul,
        )
        base_price = min(ticker.bid, ticker.vwap, ticker.low)
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
                "expiretm": f"+{self.order_lifespan_seconds}",
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
        types = ",".join(sorted(set([i["type"] for i in orders])))
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
