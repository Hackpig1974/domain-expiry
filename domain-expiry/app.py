import os
import time
import math
import requests
import logging
from datetime import datetime, timezone
from dateutil import parser as dtparse
from fastapi import FastAPI
from typing import Dict

try:
    import whois
    WHOIS_AVAILABLE = True
except ImportError:
    WHOIS_AVAILABLE = False

app = FastAPI(title="Domain Expiry API")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Required envs (fail fast) ---
DOMAINS = [d.strip() for d in os.environ["DOMAINS"].split(",") if d.strip()]
RDAP_BASE = os.environ["RDAP_BASE"].rstrip("/")
ALERT_DAYS = int(os.environ["ALERT_DAYS"])

# --- Optional envs ---
REFRESH_MINUTES = int(os.getenv("REFRESH_MINUTES", "360"))  # 6h cache
ALERT_EMOJI = os.getenv("ALERT_EMOJI", "🔴")
WHOIS_FALLBACK_ENABLED = os.getenv("WHOIS_FALLBACK_ENABLED", "false").lower() in ("true", "1", "yes")

CACHE_TTL = REFRESH_MINUTES * 60
_cache = {"data": None, "ts": 0.0}

# Reuse HTTP connections + set a UA (some RDAPs care)
_session = requests.Session()
_session.headers.update({"User-Agent": "domain-expiry/1.0 (+rdap client)"})

if WHOIS_FALLBACK_ENABLED and not WHOIS_AVAILABLE:
    logger.warning("WHOIS fallback enabled but python-whois not installed. Install with: pip install python-whois")

def _fetch_whois(domain: str) -> Dict:
    """Fallback to WHOIS when RDAP fails"""
    try:
        logger.info(f"Attempting WHOIS lookup for {domain}")
        w = whois.whois(domain)
        
        # WHOIS returns various formats, try to find expiration
        exp_date = None
        if hasattr(w, 'expiration_date') and w.expiration_date:
            # Sometimes it's a list, sometimes a single value
            exp_raw = w.expiration_date
            if isinstance(exp_raw, list):
                exp_date = exp_raw[0] if exp_raw else None
            else:
                exp_date = exp_raw
        
        if not exp_date:
            logger.warning(f"WHOIS lookup for {domain} succeeded but no expiration date found")
            return {
                "domain": domain,
                "expires": None,
                "expires_us": None,
                "days_left": None,
                "label": "n/a",
                "alert": False,
                "source": "whois",
                "error": "no-expiration-in-whois",
            }
        
        # Convert to timezone-aware datetime
        if exp_date.tzinfo is None:
            exp_dt = exp_date.replace(tzinfo=timezone.utc)
        else:
            exp_dt = exp_date.astimezone(timezone.utc)
        
        today = datetime.now(timezone.utc).date()
        days_left = (exp_dt.date() - today).days
        expires_us = exp_dt.strftime("%m/%d/%Y")
        alert = days_left <= ALERT_DAYS
        
        label = f"{ALERT_EMOJI} {expires_us} ({days_left}d)" if alert else f"{expires_us} ({days_left}d)"
        
        logger.info(f"WHOIS lookup successful for {domain}: expires {expires_us} ({days_left}d)")
        
        return {
            "domain": domain,
            "expires": exp_dt.isoformat(),
            "expires_us": expires_us,
            "days_left": days_left,
            "label": label,
            "alert": alert,
            "source": "whois",
        }
    except Exception as e:
        logger.error(f"WHOIS lookup failed for {domain}: {str(e)}")
        return {
            "domain": domain,
            "expires": None,
            "expires_us": None,
            "days_left": None,
            "label": "n/a",
            "alert": False,
            "source": "whois",
            "error": str(e),
        }

def _fetch_one(domain: str) -> Dict:
    url = f"{RDAP_BASE}/{domain}"
    
    # Try RDAP first
    try:
        logger.info(f"Attempting RDAP lookup for {domain}")
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
            logger.warning(f"RDAP lookup for {domain} succeeded but no expiration event found")
            # Try WHOIS fallback if enabled
            if WHOIS_FALLBACK_ENABLED and WHOIS_AVAILABLE:
                logger.info(f"Falling back to WHOIS for {domain}")
                return _fetch_whois(domain)
            
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

        label = f"{ALERT_EMOJI} {expires_us} ({days_left}d)" if alert else f"{expires_us} ({days_left}d)"
        
        logger.info(f"RDAP lookup successful for {domain}: expires {expires_us} ({days_left}d)")

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
        logger.error(f"RDAP lookup failed for {domain}: {str(e)}")
        
        # Try WHOIS fallback if enabled
        if WHOIS_FALLBACK_ENABLED and WHOIS_AVAILABLE:
            logger.info(f"Falling back to WHOIS for {domain}")
            return _fetch_whois(domain)
        
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
        "whois_fallback_enabled": WHOIS_FALLBACK_ENABLED,
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
