"""
Test objects
"""

import gate_api

from baibaibot.objects import AssetPair, KrakenOrder, Order


def test_asset_pair_gateio() -> None:
    response = [
        gate_api.CurrencyPair(
            amount_precision=0,
            base="100X",
            buy_start=1622793600,
            fee="0.2",
            id="100X_USDT",
            min_base_amount=None,
            min_quote_amount="1",
            precision=11,
            quote="USDT",
            sell_start=1608782400,
            trade_status="untradable",
        )
    ]
    pair = AssetPair.from_gateio(response[0])
    assert pair.exchange == "gate.io"
    assert pair.id == "100X_USDT"
    assert pair.base == "100X"
    assert pair.quote == "USDT"
    assert pair.dp_base == 0
    assert pair.dp_quote == 11


def test_asset_pair_kraken() -> None:
    response = {
        "1INCHEUR": {
            "altname": "1INCHEUR",
            "wsname": "1INCH/EUR",
            "aclass_base": "currency",
            "base": "1INCH",
            "aclass_quote": "currency",
            "quote": "ZEUR",
            "lot": "unit",
            "cost_decimals": 5,
            "pair_decimals": 3,
            "lot_decimals": 8,
            "lot_multiplier": 1,
            "leverage_buy": [],
            "leverage_sell": [],
            "fees": [
                [0, 0.26],
            ],
            "fees_maker": [
                [0, 0.16],
            ],
            "fee_volume_currency": "ZUSD",
            "margin_call": 80,
            "margin_stop": 40,
            "ordermin": "10",
            "costmin": "0.45",
            "tick_size": "0.001",
            "status": "online",
        }
    }
    pair_id = "1INCHEUR"
    pair = AssetPair.from_kraken(pair_id, response[pair_id])
    assert pair.exchange == "Kraken"
    assert pair.id == "1INCHEUR"
    assert pair.base == "1INCH"
    assert pair.quote == "ZEUR"
    assert pair.dp_base == 8
    assert pair.dp_quote == 3


def test_order_kraken() -> None:
    order = Order(
        expire="+900",
        ordertype="limit",
        price=12.34,
        side="buy",
        tif="GTD",
        volume=1234.5,
        close={
            "price": 12.56,
            "side": "sell",
        },
    )
    apiorder = order.to_kraken()
    expected: KrakenOrder = {
        # https://www.kraken.com/en-gb/features/api#add-standard-order
        # "userref": 0,  # int32
        "ordertype": "limit",
        "type": "buy",
        "volume": "1234.5",
        # "displayvol": "",
        "price": "12.34",
        # "price2": "",
        # "trigger": "",
        # "leverage": "",
        "stptype": "cancel-newest",
        "oflags": "fciq",
        "timeinforce": "GTD",
        "starttm": "0",  # now
        "expiretm": "+900",
        "close": {
            "ordertype": "limit",
            "type": "sell",
            "price": "12.56",
            # "price2": "",
        },
    }
    assert apiorder == expected
