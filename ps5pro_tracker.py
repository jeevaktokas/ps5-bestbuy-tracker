#!/usr/bin/env python3
"""
PS5 Pro stock tracker for Best Buy Canada (bestbuy.ca).

- Standard library only (Python 3.8+), no pip installs
- Push alerts to your phone via ntfy.sh (free, no account)
- Ignores Open Box / Refurbished / Used listings
- Polls faster around midnight, backs off automatically on errors

Configuration is read from environment variables (or CLI flags), so no
personal info lives in the source code:

    export NTFY_TOPIC="ps5pro-your-secret-topic"
    export POSTAL_CODE="A1A1A1"
    python3 ps5pro_tracker.py --test   # send a test alert
    python3 ps5pro_tracker.py          # start watching
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

log = logging.getLogger("ps5pro")

DEFAULT_SKUS = "19492009"  # NEW listing SKU = number at the end of the product URL
# Known non-new listings (ignored on purpose): 19669388, 19495500 = Open Box | 18924299 = Refurbished

BLOCK_RE = re.compile(r"\b(open[- ]?box|refurb\w*|used|pre-?owned|renewed)\b", re.I)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json",
}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8-sig"))


def notify(topic: str, title: str, msg: str, click_url: str | None = None,
           priority: str = "urgent") -> None:
    headers = {"Title": title, "Priority": priority, "Tags": "rotating_light,video_game"}
    if click_url:
        headers["Click"] = click_url
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=msg.encode(),
                                 headers=headers, method="POST")
    try:
        urllib.request.urlopen(req, timeout=15).close()
    except Exception as e:  # alerts failing must never crash the watcher
        log.warning("notify failed: %s", e)


def fetch_name(sku: str) -> str:
    try:
        return get_json(f"https://www.bestbuy.ca/api/v2/json/product/{sku}").get("name", "") or ""
    except Exception as e:
        log.debug("name lookup failed for %s: %s", sku, e)
        return ""


def check_availability(sku: str, postal: str) -> tuple[bool, bool]:
    """Return (available_online, available_for_pickup)."""
    q = urllib.parse.urlencode({
        "accept": "application/vnd.bestbuy.standardproduct.v1+json",
        "accept-language": "en-CA",
        "locations": "",
        "postalCode": postal,
        "skus": sku,
    })
    data = get_json(f"https://www.bestbuy.ca/ecomm-api/availability/products?{q}")
    avail = (data.get("availabilities") or [{}])[0]
    ship = avail.get("shipping") or {}
    pick = avail.get("pickup") or {}
    online = bool(ship.get("purchasable")) or str(ship.get("status", "")).lower() == "instock"
    store = bool(pick.get("purchasable"))
    return online, store


def is_new_stock(name: str) -> bool:
    return not BLOCK_RE.search(name or "")


def next_delay(slow: int, fast: int) -> float:
    h = datetime.now().hour
    near_midnight = h >= 23 or h < 1  # 11 PM - 1 AM local time
    return (fast if near_midnight else slow) + random.uniform(0, 4)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Best Buy Canada PS5 Pro stock tracker")
    p.add_argument("--topic", default=os.getenv("NTFY_TOPIC"), help="ntfy topic (or NTFY_TOPIC env)")
    p.add_argument("--postal", default=os.getenv("POSTAL_CODE"), help="postal code (or POSTAL_CODE env)")
    p.add_argument("--skus", default=os.getenv("SKUS", DEFAULT_SKUS), help="comma-separated SKUs")
    p.add_argument("--slow", type=int, default=45, help="seconds between checks (normal)")
    p.add_argument("--fast", type=int, default=12, help="seconds between checks (near midnight)")
    p.add_argument("--test", action="store_true", help="send a test notification and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")

    if not args.topic:
        sys.exit("Set NTFY_TOPIC (env var or --topic). Example: ps5pro-yourname-48213")
    if args.test:
        notify(args.topic, "PS5 Pro tracker test", "If you see this, alerts work!",
               "https://www.bestbuy.ca", "default")
        print("Test sent.")
        return 0
    if not args.postal:
        sys.exit("Set POSTAL_CODE (env var or --postal), no spaces.")

    postal = args.postal.replace(" ", "").upper()
    skus = [s.strip() for s in args.skus.split(",") if s.strip()]
    log.info("Watching SKUs %s | Ctrl+C to stop", ", ".join(skus))

    names: dict[str, str] = {}
    last_alert: dict[str, float] = {}
    errors = 0

    try:
        while True:
            had_error = False
            for sku in skus:
                try:
                    if not names.get(sku):          # retry until we get a name
                        names[sku] = fetch_name(sku)
                        if names[sku] and not is_new_stock(names[sku]):
                            log.info("Skipping %s: '%s' is not brand new", sku, names[sku])
                    name = names[sku]
                    if name and not is_new_stock(name):
                        continue

                    online, store = check_availability(sku, postal)
                    log.info("%s online=%s pickup=%s", sku, online, store)

                    if (online or store) and time.time() - last_alert.get(sku, 0) > 120:
                        where = "online" if online else "in-store pickup"
                        warn = "" if name else "\n(Couldn't verify product name - check it's not Open Box.)"
                        notify(args.topic, "PS5 PRO IN STOCK AT BEST BUY!",
                               f"{name or sku}\nAvailable ({where}). GO NOW!{warn}",
                               f"https://www.bestbuy.ca/en-ca/product/{sku}")
                        last_alert[sku] = time.time()
                except urllib.error.HTTPError as e:
                    had_error = True
                    log.warning("%s HTTP %s (rate-limited/blocked? backing off)", sku, e.code)
                except Exception as e:
                    had_error = True
                    log.warning("%s check failed: %s", sku, e)

            errors = errors + 1 if had_error else 0
            delay = next_delay(args.slow, args.fast)
            time.sleep(min(600, delay * (2 ** min(errors, 5))) if errors else delay)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
