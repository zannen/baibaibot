import argparse

from baibaibot import Bot


def parse_args() -> argparse.Namespace:
    """Parse cmdline arguments"""
    parser = argparse.ArgumentParser(
        description="Interact with Kraken", usage="%(prog)s [options]"
    )

    parser.add_argument("--configfile", help="", required=True)

    parser.add_argument("--keysfile", help="", required=True)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bot = Bot(args.configfile, args.keysfile)
    bot.loop()


if __name__ == "__main__":
    main()
