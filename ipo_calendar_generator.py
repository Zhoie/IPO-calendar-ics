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
from datetime import date, timedelta, datetime

import requests
from dateutil import tz
from ics import Calendar, Event

API = "https://finnhub.io/api/v1/calendar/ipo"
TOKEN = os.getenv("FINNHUB_TOKEN")

# ---- date window: past 15 days + next 30 days -------------------------------
TODAY = date.today()
FROM = (TODAY - timedelta(days=15)).isoformat()
TO = (TODAY + timedelta(days=30)).isoformat()

# Finnhub dates are in UTC; we treat them as ET for consistency
TZ_NY = tz.gettz("America/New_York")


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


def fetch_ipos() -> list[dict]:
    if not TOKEN:
        raise RuntimeError("FINNHUB_TOKEN env-var is missing.")
    params = {"from": FROM, "to": TO, "token": TOKEN}
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("ipoCalendar", [])


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


def main() -> None:
    cal = Calendar()
    for record in fetch_ipos():
        cal.events.add(to_event(record))

    out = "ipo_calendar.ics"
    with open(out, "w", encoding="utf-8") as f:
        f.writelines(cal)
    print(f"✅  Calendar refreshed → {out}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("💥  Script failed:", exc)
        sys.exit(1)
