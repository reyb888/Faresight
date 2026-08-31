"""
Template spider for an airline-direct source (Air India used as the example).

Follows the same structural pattern as scraper/spiders/indigo.py — fill in
real selectors/JSON parsing for the live site before this spider produces data.
"""
from datetime import datetime, timedelta

import scrapy

from scraper.items import FareQuoteItem


class AirIndiaSpider(scrapy.Spider):
    name = "air_india"
    allowed_domains = ["airindia.com"]

    custom_settings = {
        # Per-source overrides go here if Air India needs different pacing
        # than the global defaults in scraper/settings.py — document why
        # if you change it.
    }

    def __init__(self, origin: str, destination: str, advance_days: int = 7, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.origin = origin.upper()
        self.destination = destination.upper()
        self.advance_days = int(advance_days)
        self.travel_date = datetime.utcnow().date() + timedelta(days=self.advance_days)

    def start_requests(self):
        search_url = (
            f"https://www.airindia.in/search"
            f"?origin={self.origin}&destination={self.destination}"
            f"&date={self.travel_date.isoformat()}"
        )
        yield scrapy.Request(
            search_url,
            callback=self.parse_search_results,
            meta={"playwright": True},
        )

    def parse_search_results(self, response: scrapy.http.Response):
        self.logger.warning(
            "parse_search_results is a template — fill in real selectors "
            "for %s before this spider produces data.",
            self.name,
        )
        return

    def _build_item(self, flight: dict) -> FareQuoteItem:
        item = FareQuoteItem()
        item["source"] = "air_india"
        item["source_type"] = "airline_direct"
        item["origin"] = self.origin
        item["destination"] = self.destination
        item["carrier"] = "AI"
        item["flight_number"] = flight.get("flightNumber")
        item["fare_class"] = flight.get("fareClass")
        item["travel_date"] = self.travel_date
        item["advance_purchase_days"] = self.advance_days
        item["observed_at"] = datetime.utcnow()
        item["base_fare"] = flight.get("baseFare")
        item["taxes_fees"] = flight.get("taxesAndFees")
        item["total_fare"] = flight.get("totalFare")
        item["currency"] = "INR"
        item["availability_status"] = "available" if flight.get("available") else "sold_out"
        item["raw_payload"] = flight
        return item