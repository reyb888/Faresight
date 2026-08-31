#!/usr/bin/env bash
# Runs one full daily cycle: scrape every source x route x window in the
# basket, clean the batch, then compute today's index.
# Invoked as the start command of the Render Cron Job (see render.yaml).
set -euo pipefail

export SCRAPY_SETTINGS_MODULE=scraper.settings

TODAY=$(date -u +%F)
ROUTES=("DEL-BOM" "DEL-BLR" "BOM-BLR" "DEL-CCU" "BLR-HYD" "MAA-DEL")
WINDOWS=(1 7 15 30 45)
SPIDERS=("indigo")  # add air_india, akasa, spicejet, makemytrip, ixigo, etc. as they're built

echo "== APIx daily batch: ${TODAY} =="

for spider in "${SPIDERS[@]}"; do
  for route in "${ROUTES[@]}"; do
    origin="${route%-*}"
    destination="${route#*-}"
    for window in "${WINDOWS[@]}"; do
      echo "-- scraping ${spider} ${origin}->${destination} T+${window}"
      scrapy crawl "${spider}" \
        -a origin="${origin}" -a destination="${destination}" -a advance_days="${window}" \
        || echo "!! ${spider} ${origin}-${destination} T+${window} failed — continuing (see docs/SYSTEM_ARCHITECTURE.md §6)"
    done
  done
done

echo "== cleaning batch =="
python -m pipeline.cleaning --date "${TODAY}"

echo "== computing index =="
python -m index.index_engine --date "${TODAY}" --frequency daily

echo "== done =="
