"""
Useful objects
"""

from typing import Any, Dict, Optional, Union


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
    def from_kraken(cls, pair_id: str, pair: Dict[str, Any]) -> "AssetPair":
        return AssetPair(
            exchange="Kraken",
            id=pair_id,
            base=pair["base"],
            quote=pair["quote"],
            dp_base=pair["lot_decimals"],
            dp_quote=pair["pair_decimals"],
        )

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
