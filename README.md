# PS5 Pro Stock Tracker (Best Buy Canada)

A small, dependency-free Python script that polls Best Buy Canada's availability
endpoint for a PS5 Pro and sends a push notification to your phone the moment
it's available for online order or store pickup.

## Features
- Python standard library only, no `pip install`
- Phone alerts through [ntfy.sh](https://ntfy.sh) (no account needed)
- Filters out Open Box / Refurbished / Used listings by name
- Adaptive polling: faster around midnight, with jitter and exponential backoff on errors/rate limits
- Config via environment variables or CLI flags (no secrets in source)

## Setup (macOS)
1. Check Python: `python3 --version` (if missing, install from python.org or `brew install python`)
2. Install the ntfy app on your phone and subscribe to a private topic name.
3. Run:

```bash
export NTFY_TOPIC="ps5pro-your-secret-topic"
export POSTAL_CODE="A1A1A1"
python3 ps5pro_tracker.py --test   # verify alerts work
python3 ps5pro_tracker.py          # start watching
```

Options: `--skus 123,456`, `--slow 45`, `--fast 12`, `-v`.

## Notes
- Find a SKU in the product URL: `bestbuy.ca/en-ca/product/<name>/<SKU>`.
- Alerts only; it does not purchase anything. Keep poll intervals reasonable.
- Not affiliated with Best Buy. The endpoints are unofficial and may change.
