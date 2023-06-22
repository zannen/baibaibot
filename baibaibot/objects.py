from typing import Any, Dict

import gate_api


class AssetPair:
    exchange = "unknown"
    id = ""
    base = ""
    quote = ""
    dp_base = 0
    dp_quote = 0

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @classmethod
    def from_kraken(self, pair_id: str, pair: Dict[str, Any]) -> "AssetPair":
        return AssetPair(
            exchange="Kraken",
            id=pair_id,
            base=pair["base"],
            quote=pair["quote"],
            dp_base=pair["lot_decimals"],
            dp_quote=pair["pair_decimals"],
        )

    @classmethod
    def from_gateio(self, pair: gate_api.CurrencyPair) -> "AssetPair":
        return AssetPair(
            exchange="gate.io",
            id=pair.id,
            base=pair.base,
            quote=pair.quote,
            dp_base=pair.amount_precision,
            dp_quote=pair.precision,
        )
