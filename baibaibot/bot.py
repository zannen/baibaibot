"""
BaiBaiBot: A simple Kraken trading bot.
"""

import json
import logging
import time
from typing import Optional

from .gateioapi import GateIOAPI
from .krakenapi import KrakenAPI


class Bot:
    configfile = ""

    gate: Optional[GateIOAPI] = None
    krak: Optional[KrakenAPI] = None

    def __init__(self, configfile: str, keysfile: str):
        # "%(asctime)s %(name)s:%(levelname)s %(message)s "
        logging.basicConfig(
            level=logging.INFO,
            format=(
                "%(asctime)s %(name)s:%(levelname)-5s "
                "[%(funcName)s:%(lineno)4d] %(message)s"
            ),
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.logger = logging.getLogger("BaiBaiBot")

        self.configfile = configfile
        keys = json.load(open(keysfile, "r"))
        if "gate.io" in keys:
            self.gate = GateIOAPI(
                key=keys["gate.io"]["key"],
                secret=keys["gate.io"]["secret"],
                # logger=self.logger,
            )
        if "Kraken" in keys:
            self.krak = KrakenAPI(
                key=keys["Kraken"]["key"],
                secret=keys["Kraken"]["secret"],
                # logger=self.logger,
            )
        self.load_config()
        self.connect()
        self.get_asset_pairs()

    def exch_fn(self, funcname: str, *args, **kwargs) -> None:
        for exchange in sorted(self.cfg["exchanges"].keys()):
            if exchange == "gate.io":
                func = getattr(self.gate, funcname)
                func(*args, **kwargs)
            elif exchange == "Kraken":
                func = getattr(self.krak, funcname)
                func(*args, **kwargs)
            else:
                raise Exception(f"Unknown exchange {exchange}")

    def connect(self) -> None:
        self.exch_fn("connect")

    def get_asset_pairs(self) -> None:
        self.exch_fn("get_asset_pairs")

    def get_balances(self) -> None:
        self.exch_fn("get_balances")

    def get_open_orders(self) -> None:
        self.exch_fn("get_open_orders")

    def load_config(self):
        self.cfg = json.load(open(self.configfile, "r"))
        lvl = self.cfg["loglevel"]
        self.logger.setLevel(lvl)
        for exchange, cfg in self.cfg["exchanges"].items():
            if exchange == "gate.io":
                self.gate.logger.setLevel(lvl)
                self.gate.cfg = cfg
            elif exchange == "Kraken":
                self.krak.logger.setLevel(lvl)
                self.krak.cfg = cfg
            else:
                raise Exception(f"Unknown exchange {exchange}")

    def loop(self):
        while True:
            self.load_config()
            self.get_balances()
            self.get_open_orders()
            self.tick()
            # self.get_balances()
            # self.get_open_orders()
            self.print_all_balances()

            sleep_time = max(
                cfg["order_lifespan_seconds"]
                for cfg in self.cfg["exchanges"].values()
            )
            self.logger.info("Sleeping for %d seconds", sleep_time)
            time.sleep(sleep_time)

    def print_all_balances(self) -> None:
        self.exch_fn("print_all_balances")

    def tick(self) -> None:
        self.exch_fn("tick")
