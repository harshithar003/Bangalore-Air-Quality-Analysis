"""
Bangalore Real-Time Air Quality + Weather Collector
-----------------------------------------------------
Mirrors the structure of the original Dublin bike-share collector:
  - Every N minutes, pull live station-level data for a whole city
    (there: JCDecaux bike stations, here: WAQI air-quality stations)
  - Also pull current weather for the same city
  - Append a timestamped snapshot to CSV so we build a real time-series

DATA SOURCES
  1) WAQI (World Air Quality Index) - api.waqi.info
     Free token: https://aqicn.org/data-platform/token/
     Uses the "map/bounds" endpoint, which returns EVERY monitoring
     station inside a lat/lon box in one call - this is the direct
     analogue of JCDecaux's "all stations for a contract" call.

  2) OpenWeatherMap - api.openweathermap.org
     Free token: https://home.openweathermap.org/users/sign_up
     Current weather for Bangalore (temperature, humidity, wind, rain).

SETUP
  1. pip install requests pandas schedule python-dotenv
  2. Copy .env.example to .env and fill in your two tokens
  3. python fetch_data.py                        # runs once immediately, then every 30 min
     python fetch_data.py --once                 # runs a single fetch and exits
     python fetch_data.py --interval 30 --unit seconds   # fast demo mode (see note below)

NOTE ON FAST/DEMO MODE
  --unit seconds is meant for short live demos (e.g. showing this running for
  a few minutes) so you can visibly watch new rows land in the CSVs. It is
  NOT meant to be left running for days - the WAQI and OpenWeatherMap free
  tiers have daily request caps, and AQI/weather don't meaningfully change
  every 30 seconds anyway. Use minutes (the default) for real data collection.
"""

import os
import sys
import time
import argparse
import warnings
from datetime import datetime, timezone

import requests
import pandas as pd
import schedule
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

# --- Configuration -----------------------------------------------------

WAQI_TOKEN = os.getenv("WAQI_TOKEN", "")
OWM_TOKEN = os.getenv("OWM_TOKEN", "")

# Bounding box roughly covering Bangalore Urban district
# (south_lat, west_lon, north_lat, east_lon)
BANGALORE_BOUNDS = (12.75, 77.35, 13.15, 77.85)
BANGALORE_LAT, BANGALORE_LON = 12.9716, 77.5946

WAQI_BOUNDS_URL = "https://api.waqi.info/map/bounds/"
WAQI_FEED_URL = "https://api.waqi.info/feed/@{station_id}/"
OWM_URL = "https://api.openweathermap.org/data/2.5/weather"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

AQI_OUT = os.path.join(DATA_DIR, "aqi_stations.csv")
WEATHER_OUT = os.path.join(DATA_DIR, "weather.csv")


# --- Fetchers ------------------------------------------------------------

def fetch_aqi_stations(bounds=BANGALORE_BOUNDS, token=WAQI_TOKEN):
    """Fetch every WAQI station inside the Bangalore bounding box."""
    if not token or "your_" in token:
        raise RuntimeError(
            "WAQI_TOKEN looks unset or still a placeholder. "
            "Get a real token at https://aqicn.org/data-platform/token/ and put it in .env."
        )

    south, west, north, east = bounds
    params = {"latlng": f"{south},{west},{north},{east}", "token": token}

    response = requests.get(WAQI_BOUNDS_URL, params=params, timeout=15)
    response.raise_for_status()
    payload = response.json()

    # status != "ok" means the API rejected the request (bad/unactivated token,
    # over quota, malformed params, etc) - surface the real reason instead of
    # silently returning an empty list, which used to print as "0 stations"
    # and hide the actual problem.
    if payload.get("status") != "ok":
        raise RuntimeError(f"WAQI bounds call failed - status={payload.get('status')!r}, response={payload}")

    if not payload.get("data"):
        print("WAQI returned status=ok but an empty station list for this bounding box. "
              "Double-check BANGALORE_BOUNDS, or the box may genuinely have no reporting stations right now.")

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for station in payload["data"]:
        # station["aqi"] can be "-" when a station is temporarily offline
        aqi_val = station.get("aqi")
        try:
            aqi_val = float(aqi_val)
        except (TypeError, ValueError):
            aqi_val = None

        rows.append({
            "fetched_at": fetched_at,
            "station_uid": station.get("uid"),
            "station_name": station.get("station", {}).get("name"),
            "latitude": station.get("lat"),
            "longitude": station.get("lon"),
            "aqi": aqi_val,
        })
    return rows


def fetch_station_detail(station_uid, token=WAQI_TOKEN):
    """Optional: fetch full pollutant breakdown (PM2.5, PM10, NO2...) for one station."""
    url = WAQI_FEED_URL.format(station_id=station_uid)
    response = requests.get(url, params={"token": token}, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "ok":
        return None
    iaqi = payload["data"].get("iaqi", {})
    return {k: v.get("v") for k, v in iaqi.items()}


def fetch_weather(lat=BANGALORE_LAT, lon=BANGALORE_LON, token=OWM_TOKEN):
    """Fetch current Bangalore weather from OpenWeatherMap."""
    if not token:
        raise RuntimeError("OWM_TOKEN is not set. Add it to your .env file.")

    params = {"lat": lat, "lon": lon, "appid": token, "units": "metric"}
    response = requests.get(OWM_URL, params=params, timeout=15)
    response.raise_for_status()
    payload = response.json()

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "temperature_c": payload.get("main", {}).get("temp"),
        "humidity_pct": payload.get("main", {}).get("humidity"),
        "pressure_hpa": payload.get("main", {}).get("pressure"),
        "wind_speed_ms": payload.get("wind", {}).get("speed"),
        "rain_1h_mm": payload.get("rain", {}).get("1h", 0.0),
        "clouds_pct": payload.get("clouds", {}).get("all"),
        "weather_main": (payload.get("weather") or [{}])[0].get("main"),
        "weather_desc": (payload.get("weather") or [{}])[0].get("description"),
    }


# --- Persistence ----------------------------------------------------------

def append_rows(rows, out_path):
    if not rows:
        return
    df = pd.DataFrame(rows)
    header = not os.path.exists(out_path)
    df.to_csv(out_path, mode="a", header=header, index=False)


def run_once():
    print(f"[{datetime.now().isoformat(timespec='seconds')}] Fetching Bangalore AQI + weather...")
    try:
        aqi_rows = fetch_aqi_stations()
        append_rows(aqi_rows, AQI_OUT)
        print(f"  AQI: {len(aqi_rows)} stations -> {AQI_OUT}")
    except Exception as error:
        print(f"  AQI fetch failed: {error}")

    try:
        weather_row = fetch_weather()
        append_rows([weather_row], WEATHER_OUT)
        print(f"  Weather: {weather_row['weather_desc']}, {weather_row['temperature_c']}C -> {WEATHER_OUT}")
    except Exception as error:
        print(f"  Weather fetch failed: {error}")


# --- Entry point ------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Bangalore AQI + weather data.")
    parser.add_argument("--once", action="store_true", help="Run a single fetch and exit.")
    parser.add_argument("--interval", type=int, default=30, help="How often to fetch (default 30).")
    parser.add_argument("--unit", choices=["minutes", "seconds"], default="minutes",
                         help="Unit for --interval. Use 'seconds' only for short live demos (see NOTE above).")
    args = parser.parse_args()

    run_once()

    if args.once:
        sys.exit(0)

    if args.unit == "seconds":
        schedule.every(args.interval).seconds.do(run_once)
        print(f"Scheduled to run every {args.interval} seconds (DEMO MODE). Press Ctrl+C to stop.")
    else:
        schedule.every(args.interval).minutes.do(run_once)
        print(f"Scheduled to run every {args.interval} minutes. Press Ctrl+C to stop.")

    while True:
        schedule.run_pending()
        time.sleep(1)