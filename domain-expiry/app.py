import os
import time
import math
import requests
from datetime import datetime, timezone
from dateutil import parser as dtparse
from fastapi import FastAPI
from typing import Dict

app = FastAPI(title="Domain Expiry API")

# --- Required envs (fail fast) ---
DOMAINS = [d.strip() for d in os.environ["DOMAINS"].split(",") if d.strip()]
RDAP_BASE = os.environ["RDAP_BASE"].rstrip("/")
ALERT_DAYS = int(os.environ["ALERT_DAYS"])

# --- Optional envs ---
REFRESH_MINUTES = int(os.getenv("REFRESH_MINUTES", "360"))  # 6h cache
ALERT_EMOJI = os.getenv("ALERT_EMOJI", "🔴")

CACHE_TTL = REFRESH_MINUTES * 60
_cache = {"data": None, "ts": 0.0}

# Reuse HTTP connections + set a UA (some RDAPs care)
_session = requests.Session()
_session.headers.update({"User-Agent": "domain-expiry/1.0 (+rdap client)"})

def _fetch_one(domain: str) -> Dict:
    url = f"{RDAP_BASE}/{domain}"
    try:
        r = _session.get(url, timeout=20)
        r.raise_for_status()
        j = r.json()

        # Find expiration event
        exp_iso = None
        for ev in j.get("events", []):
            if ev.get("eventAction") in ("expiration", "expiry"):
                exp_iso = ev.get("eventDate")
                break

        if not exp_iso:
            return {
                "domain": domain,
                "expires": None,
                "expires_us": None,
                "days_left": None,
                "label": "n/a",
                "alert": False,
                "source": url,
                "error": "no-expiration-in-rdap",
            }

        exp_dt = dtparse.isoparse(exp_iso).astimezone(timezone.utc)
        today = datetime.now(timezone.utc).date()
        days_left = (exp_dt.date() - today).days
        expires_us = exp_dt.strftime("%m/%d/%Y")
        alert = days_left <= ALERT_DAYS

        # Right-side label for Homepage dynamic-list (emoji BEFORE date)
        label = f"{ALERT_EMOJI} {expires_us} ({days_left}d)" if alert else f"{expires_us} ({days_left}d)"

        return {
            "domain": domain,
            "expires": exp_dt.isoformat(),
            "expires_us": expires_us,
            "days_left": days_left,
            "label": label,
            "alert": alert,
            "source": url,
        }
    except Exception as e:
        return {
            "domain": domain,
            "expires": None,
            "expires_us": None,
            "days_left": None,
            "label": "n/a",
            "alert": False,
            "source": url,
            "error": str(e),
        }


def _refresh(force: bool = False):
    now = time.monotonic()
    if not force and _cache["data"] is not None and (now - _cache["ts"] < CACHE_TTL):
        return

    data = [_fetch_one(d) for d in DOMAINS]
    # Soonest first; missing dates last
    data.sort(key=lambda d: (d.get("days_left") is None, d.get("days_left", math.inf)))

    _cache["data"] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "domains": data,
        "refresh_minutes": REFRESH_MINUTES,
        "alert_days": ALERT_DAYS,
        "rdap_base": RDAP_BASE,
    }
    _cache["ts"] = now

@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/status")
def status(force: bool = False):
    _refresh(force=force)
    return _cache["data"]

@app.get("/flat")
def flat():
    _refresh(force=False)
    lines = {}
    for i, item in enumerate(_cache["data"]["domains"], start=1):
        if item["expires_us"]:
            prefix = f"{ALERT_EMOJI} " if item.get("alert") else ""
            line = f"{item['domain']} — Exp: {prefix}{item['expires_us']} ({item['days_left']}d)"
        else:
            line = f"{item['domain']} — Exp: n/a"
            if item.get("error"):
                line += f" [{item['error']}]"
        lines[f"line{i}"] = line
    lines["updated"] = _cache["data"]["updated"]
    return lines
