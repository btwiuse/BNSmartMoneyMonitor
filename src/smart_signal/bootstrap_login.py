"""Bootstrap Binance login session for Playwright persistent profile."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright


DEFAULT_PROFILE_DIR = Path("pw-profile")
DEFAULT_BOOTSTRAP_SYMBOL = "BTCUSDT"


def build_signal_url(symbol: str) -> str:
    return (
        f"https://www.binance.com/zh-CN/smart-money/signal/{symbol}"
        "?timeRange=30m&side=BOTH&sortBy=TIME&sortOrder=DESC&page=1"
    )


def launch_persistent_context(profile_dir: Path, *, headless: bool = False) -> BrowserContext:
    profile_dir.mkdir(parents=True, exist_ok=True)
    playwright = sync_playwright().start()
    try:
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            viewport={"width": 1440, "height": 960},
        )
    except Exception:
        playwright.stop()
        raise


def open_signal_page(context: BrowserContext, symbol: str) -> Page:
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(build_signal_url(symbol), wait_until="domcontentloaded", timeout=60_000)
    return page


def bootstrap_login(profile_dir: Path = DEFAULT_PROFILE_DIR, symbol: str = DEFAULT_BOOTSTRAP_SYMBOL) -> None:
    context = launch_persistent_context(profile_dir, headless=False)
    try:
        page = open_signal_page(context, symbol)
        print("Binance Smart Signal login bootstrap started.")
        print(f"Profile directory: {profile_dir.resolve()}")
        print(f"Open page: {page.url}")
        print("Complete Binance login in the browser window, then press Enter here to save the session.")
        input()
    finally:
        context.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap Binance login session for Playwright.")
    parser.add_argument(
        "--profile-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="Persistent Playwright profile directory.",
    )
    parser.add_argument(
        "--symbol",
        default=DEFAULT_BOOTSTRAP_SYMBOL,
        help="Smart Signal symbol to open during login bootstrap.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bootstrap_login(profile_dir=Path(args.profile_dir), symbol=args.symbol.upper())


if __name__ == "__main__":
    main()
