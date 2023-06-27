"""
Useful objects
"""

import math
from typing import Any, Dict, Optional, Tuple, Union

import gate_api


class AssetPair:
    exchange = "unknown"
    id = ""
    base = ""
    quote = ""
    dp_base = 0
    dp_quote = 0

    def __init__(self, **kwargs):
        for key, val in kwargs.items():
            setattr(self, key, val)

    @classmethod
    def from_gateio(cls, pair: gate_api.CurrencyPair) -> "AssetPair":
        return AssetPair(
            exchange="gate.io",
            id=pair.id,
            base=pair.base,
            quote=pair.quote,
            dp_base=pair.amount_precision,
            dp_quote=pair.precision,
        )

    @classmethod
    def from_kraken(cls, pair_id: str, pair: Dict[str, Any]) -> "AssetPair":
        return AssetPair(
            exchange="Kraken",
            id=pair_id,
            base=pair["base"],
            quote=pair["quote"],
            dp_base=pair["lot_decimals"],
            dp_quote=pair["pair_decimals"],
        )

    def inc_price(self, price: Union[int, float]) -> float:
        """
        Increment the price by the minimum possible amount.
        """
        return self.round_quote(price + math.pow(10, -self.dp_quote))

    def dec_price(self, price: Union[int, float]) -> float:
        """
        Increment the price by the minimum possible amount.
        """
        return self.round_quote(price - math.pow(10, -self.dp_quote))

    def round_base(self, volume: Union[int, float]) -> float:
        return round(volume, self.dp_base)

    def round_quote(self, price: Union[int, float]) -> float:
        return round(price, self.dp_quote)


KrakenOrder = Dict[str, Union[str, Dict[str, str]]]


class Order:
    expire = ""
    ordertype = ""
    price = 0.0
    side = ""
    tif = ""
    volume = 0.0
    close: Optional[Dict[str, Any]] = None

    def __init__(self, **kwargs):
        for key, val in kwargs.items():
            setattr(self, key, val)

    def to_gateio(
        self,
        pair: str,
        asset_pair: AssetPair,
        expire: int,
    ) -> Tuple[gate_api.Order, Optional[gate_api.SpotPriceTriggeredOrder]]:
        order = gate_api.Order(
            text="t-apiv4-zannen-baibaibot",  # max 30 chars
            currency_pair=pair,
            type=self.ordertype,
            account="spot",
            side=self.side,
            amount=str(self.volume),
            price=str(self.price),
            time_in_force="gtc",
            iceberg=str(min(10, self.volume)),
            auto_borrow=False,
            auto_repay=False,
        )
        close_order: Optional[gate_api.SpotPriceTriggeredOrder] = None
        if self.close is not None:
            trigger_price = self.price
            trigger_rule = ""
            if self.side == "sell":
                trigger_price = asset_pair.inc_price(trigger_price)
                trigger_rule = ">="
            else:
                trigger_price = asset_pair.dec_price(trigger_price)
                trigger_rule = "<="
            trigger = gate_api.SpotPriceTrigger(
                price=str(trigger_price),
                rule=trigger_rule,
                expiration=expire,
            )
            put = gate_api.SpotPricePutOrder(
                type=self.ordertype,
                side=self.close["side"],
                price=str(self.close["price"]),
                amount=str(self.volume),
                account="normal",
                time_in_force="gtc",
            )
            close_order = gate_api.SpotPriceTriggeredOrder(
                trigger=trigger,
                put=put,
                market=pair,
            )
        return (order, close_order)

    def to_kraken(self) -> KrakenOrder:
        order: KrakenOrder = {
            # https://www.kraken.com/en-gb/features/api#add-standard-order
            # "userref": 0,  # int32
            "ordertype": self.ordertype,
            "type": self.side,
            "volume": str(self.volume),
            # "displayvol": "",
            "price": str(self.price),
            # "price2": "",
            # "trigger": "",
            # "leverage": "",
            "stptype": "cancel-newest",
            "oflags": "fciq",
            "timeinforce": self.tif,
            "starttm": "0",  # now
            "expiretm": self.expire,
        }
        if self.close is not None:
            order["close"] = {
                "ordertype": self.ordertype,
                "type": self.close["side"],
                "price": str(self.close["price"]),
                # "price2": "",
            }

        return order
