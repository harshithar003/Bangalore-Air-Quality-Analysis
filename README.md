# 🌫️ Bangalore Real-Time Air Quality Analytics

A Bangalore-focused adaptation of the "From Data to Decisions" real-time analytics
project structure (originally built for Dublin bike-share data). Since Bangalore
has no public real-time bike-share API, this version pairs live **air quality**
data with live **weather** data — the same "real-time stations + weather,
merged and analyzed" shape, applied to a genuinely available Bangalore data source.

## Data Sources
| Source | What it gives us | Token |
|---|---|---|
| [WAQI](https://aqicn.org/api/) `map/bounds` API | Every air-quality monitoring station in Bangalore, in one call, with live AQI | Free — [register here](https://aqicn.org/data-platform/token/) |
| [OpenWeatherMap](https://openweathermap.org/current) current weather API | Live Bangalore temperature, humidity, rain, wind | Free tier — [sign up here](https://home.openweathermap.org/users/sign_up) |

Real Bangalore stations already on WAQI (confirmed): City Railway Station, BWSSB,
BTM, Peenya, BWSSB Kadabesanahalli, Silk Board, Hebbal — and more may show up
inside the bounding box once you query live.

## Repository Contents
| File | Description |
|---|---|
| `fetch_data.py` | Collector: pulls all Bangalore AQI stations + current weather on a schedule, appends to CSV |
| `01_data_cleaning.ipynb` | Loads raw snapshots, cleans, merges AQI + weather on timestamp |
| `02_eda_analysis.ipynb` | EDA answering: busiest/worst/best stations, rush-hour patterns, weather correlation |
| `data/aqi_stations.csv`, `data/weather.csv` | **Seed/demo data** (synthetically generated) so the notebooks run out of the box |
| `data/cleaned_bangalore_aqi.csv` | Output of the cleaning notebook |
| `.env.example` | Template for your API tokens |

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and add your WAQI_TOKEN and OWM_TOKEN
```

## Running the collector
```bash
python fetch_data.py --once        # single fetch, good for testing your tokens
python fetch_data.py               # runs continuously, fetches every 30 min
python fetch_data.py --interval 15 # custom interval
```
Leave it running for a few days (e.g. on a spare machine, a Raspberry Pi, or a
free-tier cloud VM) to build up a real time-series, the same way the original
project collected Dublin data over Dec 24-31.

## ⚠️ About the seed data
`data/aqi_stations.csv` and `data/weather.csv` ship with **synthetically
generated** sample rows (7 real Bangalore station names, 7 days of realistic
but simulated hourly-ish readings) so you can run both notebooks immediately
and see the full pipeline work end-to-end. Once you've collected real data
with `fetch_data.py`, replace these files (or just let the collector append
to them) and re-run the notebooks for genuine results.

## Project Highlights (once real data is collected)
- **Real-time AQI**: live station-level readings across Bangalore via WAQI
- **Weather Impact**: temperature, humidity, rainfall, wind vs AQI
- **Peak Hour Patterns**: how AQI moves through morning/evening rush hours
- **Station Comparison**: which areas consistently have the worst/best air quality, and why
