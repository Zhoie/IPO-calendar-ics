#!/usr/bin/env python3
"""
Generate an IPO calendar (.ics) using Finnhub's IPO endpoint.

* Free tier allows ±30 days of data (historical & upcoming IPOs).
* Each IPO is saved as an all-day event.
* Description includes company name, exchange, share count, price range.

Env-var required:
  FINNHUB_TOKEN   your Finnhub API key
"""

import os
import sys
import time
from datetime import date, timedelta, datetime
from pathlib import Path

import requests
from dateutil import tz
from ics import Calendar, Event

API = "https://finnhub.io/api/v1/calendar/ipo"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "ipo_calendar.ics"
MAX_FETCH_ATTEMPTS = 4
BASE_RETRY_DELAY_SECONDS = 2
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Finnhub dates are in UTC; we treat them as ET for consistency
TZ_NY = tz.gettz("America/New_York")


class RetryableFinnhubError(RuntimeError):
    """Raised when Finnhub is temporarily unavailable after all retries."""


def fmt_num(n):
    """Format big numbers like 12000000 → '12 M'."""
    if n in (None, 0, "0"):
        return "-"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    if n >= 1_000_000:
        return f"{n/1_000_000:.0f}\u202fM"
    return f"{n:.0f}"


def build_date_window(today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    return (
        (today - timedelta(days=15)).isoformat(),
        (today + timedelta(days=30)).isoformat(),
    )


def is_retryable_error(exc: requests.RequestException) -> bool:
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exc, requests.HTTPError):
        status_code = exc.response.status_code if exc.response is not None else None
        return status_code in RETRYABLE_STATUS_CODES
    return False


def fetch_ipos(session=requests, sleep_fn=time.sleep) -> list[dict]:
    token = os.getenv("FINNHUB_TOKEN")
    if not token:
        raise RuntimeError("FINNHUB_TOKEN env-var is missing.")

    from_date, to_date = build_date_window()
    params = {"from": from_date, "to": to_date, "token": token}
    last_error = None

    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            response = session.get(API, params=params, timeout=30)
            response.raise_for_status()
            return response.json().get("ipoCalendar", [])
        except requests.RequestException as exc:
            if not is_retryable_error(exc):
                raise

            last_error = exc
            if attempt == MAX_FETCH_ATTEMPTS:
                break

            wait_seconds = BASE_RETRY_DELAY_SECONDS ** attempt
            status_text = ""
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                status_text = f" (HTTP {exc.response.status_code})"

            print(
                "⚠️  Finnhub request failed"
                f"{status_text}; retrying in {wait_seconds}s"
                f" ({attempt}/{MAX_FETCH_ATTEMPTS - 1})"
            )
            sleep_fn(wait_seconds)

    raise RetryableFinnhubError(
        f"Finnhub IPO API remained unavailable after {MAX_FETCH_ATTEMPTS} attempts."
    ) from last_error


def to_event(item: dict) -> Event:
    """
    Map Finnhub IPO record to an iCalendar Event.
    Expected keys in item:
      symbol, date, name, numberOfShares, price, exchange
    """
    ev = Event()
    ev.name = f"IPO: {item.get('symbol', '-')}"
    ev.begin = datetime.combine(
        datetime.fromisoformat(item["date"]).date(),
        datetime.min.time(),
        TZ_NY,
    )
    ev.make_all_day()

    price = item.get("price", "-")
    if price and isinstance(price, str) and "-" in price:
        price_range = price
    elif price not in ("", None, "-"):
        price_range = f"${price}"
    else:
        price_range = "-"

    lines = [
        f"Company : {item.get('name', '-')}",
        f"Exchange: {item.get('exchange', '-')}",
        f"Shares  : {fmt_num(item.get('numberOfShares'))}",
        f"Price   : {price_range}",
        "Source  : Finnhub IPO Calendar",
    ]
    ev.description = "\n".join(lines)
    ev.location = item.get("exchange", "-")
    return ev


def main(fetch_fn=fetch_ipos, output_file: Path = OUTPUT_FILE) -> None:
    try:
        records = fetch_fn()
    except RetryableFinnhubError as exc:
        if output_file.exists():
            print(
                "⚠️  Finnhub is temporarily unavailable; "
                f"keeping existing calendar at {output_file.name}. {exc}"
            )
            return
        raise

    cal = Calendar()
    for record in records:
        cal.events.add(to_event(record))

    with output_file.open("w", encoding="utf-8") as f:
        f.writelines(cal)
    print(f"✅  Calendar refreshed → {output_file.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("💥  Script failed:", exc)
        sys.exit(1)
