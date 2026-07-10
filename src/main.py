import argparse
import logging
from pathlib import Path

from src.bot import MmBot
from src.config import load_config
from src.daemon import clear_stop, show_status, start_background, stop_background
from src.exchange.ondo import OndoClient


def run_bot(config_path: Path) -> None:
    config = load_config(config_path)
    log_dir = config_path.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, config.bot.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "mm-bot.log", encoding="utf-8"),
        ],
    )

    if config.bot.dry_run:
        raise SystemExit("dry_run is not implemented for MM bot yet — set dry_run: false")

    if not config.key_id or not config.api_secret:
        raise SystemExit("Missing ONDO_KEY_ID / ONDO_API_SECRET in .env")

    exchange = OndoClient(
        config.api_base_url,
        config.key_id,
        config.api_secret,
        order_prefix=config.bot.order_prefix,
    )
    MmBot(config, exchange).run()
    clear_stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ondo Professional Market Maker Bot")
    parser.add_argument("command", nargs="?", default="start", choices=["start", "stop", "status", "run"])
    parser.add_argument("-c", "--config", default="config.yaml")
    args = parser.parse_args()

    config_path = Path(args.config)
    if args.command == "start":
        start_background(str(config_path))
    elif args.command == "stop":
        stop_background()
    elif args.command == "status":
        show_status()
    elif args.command == "run":
        run_bot(config_path)


if __name__ == "__main__":
    main()