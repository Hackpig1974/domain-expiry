# domain-expiry
Homepage Service to allow for domain expiration Lookups

I created this custom service which allows for monitoring of domain names so that you know when they are coming up for expiration. This uses a docker container that runs locally (Not from a repository) that quereis at an interval that you set, and then makes the data available so that homepage can query that output to display as a service. If a domain is in need of renewal within so many days, it will put a Red orb in front of that domain entry to let you know, and bring attention to, that the domain is going to expire soon.

I find myself using Homepage daily, and this is just an easy way to know that I have domain renewals coming due soon. This consists of one new docker container and an edit to your homepage/config/services.yaml file.

=== TL/DR Instructions:  ===
1. Make a folder for the new container and drop in the files listed. (mkdir /your/container/path/domain-expiry)
2. Put your domains + settings in .env. (nano /your/container/path/.env)
3. docker compose up -d --build.
4. Add the tile to services.yaml, edit the IP address, and reload Homepage.


=== Full instructions: ===
1) Make the project
sudo mkdir -p /your/container/path/domain-expiry
cd /your/container/path/domain-expiry

2) Create .env (edit the domain list + alert window)
```Yaml
DOMAINS=ebay.com,sony.com,etc.com
RDAP_BASE=https://rdap.org/domain
ALERT_DAYS=183          # show 🔴 at/under this many days
REFRESH_MINUTES=360     # API cache window
TZ=America/Denver       # Your timezone
```

3) app.py (drop-in full file)
```Yaml
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
        alert = days_left <= ALERT_DAYS  # days_left is always int here

        # Right-side label for Homepage dynamic-list (emoji BEFORE date)
        label = f"{ALERT_EMOJI} {expires_us} ({days_left}d)" if alert else f"{expires_us} ({days_left}d)"

        return {
            "domain": domain,
            "expires": exp_dt.isoformat(),
            "expires_us": expires_us,
            "days_left": days_left,
            "label": label,
            "alert": alert,
            "source": url,  # drop if you don’t use it
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
```

4) requirements.txt
``` Yaml
fastapi==0.115.0
uvicorn[standard]==0.30.6
requests==2.32.3
python-dateutil==2.9.0.post0
```

5) Dockerfile
``` Yaml
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

6) compose.yml (Running the docker-expiry container on the Homepage server)
``` Yaml
services:
  domain-expiry:
    build: .
    container_name: domain-expiry
    env_file: .env    # loads DOMAINS/ALERT_DAYS/RDAP_BASE/TZ into the container from the .env file
    environment:
      - TZ=${TZ}
    ports:
      - "8088:8000"          
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:8000/healthz || exit 1"]
      interval: 60s
      timeout: 5s
      retries: 3
```

7) Build + run + test
``` Yaml
docker compose up -d --build
curl -s http://127.0.0.1:8088/healthz
curl -s "http://127.0.0.1:8088/status?force=true"
```

8) Wire the Homepage tile (dynamic-list)
In config/services.yaml:
``` Yaml
- Domain Tools:
    - Domain Expirations:
        icon: mdi-web
        widget:
          type: customapi
          url: http://192.168.100.23:8088/status   # This required the hardcoded IP of your docker server where the apps run
          display: dynamic-list
          refreshInterval: 900000  # 15 min
          mappings:
            items: domains
            name: domain
            label: label            # shows "🔴 MM/DD/YYYY (Xd)" when <= ALERT_DAYS
```

9) Reload Homepage:
``` Yaml
docker compose -f /your/container/path/homepage/docker-compose.yml up -d
```

      
