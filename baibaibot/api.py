import datetime
import logging
import math
import os
import traceback
from typing import Any, Dict, List, Union

from .errors import APIError, SubclassError
from .objects import AssetPair, Order
from .ticker import Ticker


class API:
    cfg: Dict[str, Any] = {}
    logger: logging.Logger

    # asset_pair ID or altname -> asset_pair dict
    asset_pairs: Dict[str, AssetPair] = {}

    # asset -> dict of total and unencumbered balances
    balances: Dict[str, Dict[str, float]] = {}

    def cancel_orders(self) -> None:
        raise SubclassError()

    def get_asset_pairs(self) -> None:
        raise SubclassError()

    def get_balances(self) -> None:
        raise SubclassError()

    def get_open_orders(self) -> None:
        raise SubclassError()

    def get_ticker(self, pair: str) -> Ticker:
        raise SubclassError()

    def place_orders(self, pair: str, orders: List[Order]) -> int:
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

    def print_ticker(self, pair: str, ticker: Ticker) -> None:
        quote = self.asset_pairs[pair].quote
        hdr = ticker.header()
        inf = ticker.info()
        self.logger.info("Ticker for %s (in %s): %s", pair, quote, hdr)
        self.logger.info("Ticker for %s (in %s): %s", pair, quote, inf)

    def print_trade_summary(
        self,
        order: Order,
        market: Dict[str, Any],
    ):
        pair = self.real_pair(market["pair"])
        c_base = self.asset_pairs[pair].base
        c_quote = self.asset_pairs[pair].quote

        quantity_base = order.volume
        open_price_quote = order.price
        open_cost = quantity_base * open_price_quote
        open_fee = open_cost * self.cfg["fee_percent"] / 100.0

        self.logger.info(
            "Open  Trade: %4s %9.4f %5s for %7.2f %4s (%8.3f %s/%s) fee %6.3f "
            "%4s",
            order.side,
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

        if order.close is None:
            return

        close_price_quote = order.close["price"]
        close_cost = quantity_base * close_price_quote
        close_fee = close_cost * self.cfg["fee_percent"] / 100.0
        gross_profit = close_cost - open_cost
        if order.side == "sell":
            gross_profit *= -1
        net_profit = gross_profit - open_fee - close_fee
        percent_fee = 100.0 - net_profit * 100.0 / gross_profit

        self.logger.info(
            "Close Trade: %4s %s for %7.2f %4s (%8.3f %s/%s) fee %6.3f %s ("
            "Gross profit %6.2f %4s (%5.2f%%) Net profit %6.2f %4s (%5.2f%%) "
            "Fee as percentage of profit %5.2f%%)",
            order.close["side"],
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
        self.print_ticker(pair, ticker)

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
        # SELL
        # ticker.high: 24h
        # ohlc.high: last 15~30 mins
        sell_order_count = market["sell"]["order_count"]
        if sell_order_count == 0:
            return 0

        pair = self.real_pair(market["pair"])
        asset_pair = self.asset_pairs[pair]
        c_base = asset_pair.base

        self.logger.info("--- Sell %s ---", pair)
        bal_base = self.balances[c_base]["unencumbered"]
        if bal_base < 0.001:
            raise APIError(
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
        orders: List[Order] = []
        for n in range(1, sell_order_count + 1):
            pcnt_bump_sell = (
                market["sell"]["pcnt_bump_a"] * n**2
                + market["sell"]["pcnt_bump_c"]
            )
            p_sell = asset_pair.round_quote(
                base_price * (1 + pcnt_bump_sell / 100)
            )
            p_buy = asset_pair.round_quote(
                p_sell * (1.0 - market["sell"]["rebuy_bump_percent"] / 100.0)
            )

            vol_sell = asset_pair.round_base(vol_mul * math.sqrt(n))

            order = Order(
                expire=f"+{self.cfg['order_lifespan_seconds']}",
                ordertype="limit",
                price=p_sell,
                side="sell",
                tif="GTD",
                volume=vol_sell,
                close={
                    "price": p_buy,
                    "side": "buy",
                },
            )
            orders.append(order)
            self.print_trade_summary(order, market)

        count = self.place_orders(pair, orders)
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
        orders: List[Order] = []
        for n in range(1, buy_order_count + 1):
            pcnt_bump_buy = (
                market["buy"]["pcnt_bump_a"] * n**2
                + market["buy"]["pcnt_bump_c"]
            )
            p_buy = asset_pair.round_quote(
                base_price * (1 - pcnt_bump_buy / 100)
            )
            if p_buy <= 0.0:
                self.logger.warning(
                    "Skipping buy order. price=%9.4f %s",
                    p_buy,
                    c_quote,
                )
                continue
            p_sell = asset_pair.round_quote(
                p_buy * (1.0 + market["buy"]["resell_bump_percent"] / 100.0)
            )

            vol_buy = asset_pair.round_base(vol_mul * math.sqrt(n))

            order = Order(
                expire=f"+{self.cfg['order_lifespan_seconds']}",
                ordertype="limit",
                price=p_buy,
                side="buy",
                tif="GTD",
                volume=vol_buy,
                close={
                    "price": p_sell,
                    "side": "sell",
                },
            )
            orders.append(order)
            self.print_trade_summary(order, market)

        count = self.place_orders(pair, orders)
        return count


def time_ms_to_str(tim: Union[int, float]) -> str:
    return (
        datetime.datetime.utcfromtimestamp(float(tim))
        .replace(microsecond=0)
        .isoformat()
        .replace("T", " ")
    )
