"""
Template spider for an OTA source (Goibibo used as the example).
"""
from datetime import datetime, timedelta

import scrapy

from scraper.items import FareQuoteItem


class GoibiboSpider(scrapy.Spider):
    name = "goibibo"
    allowed_domains = ["goibibo.com"]

    custom_settings = {}

    def __init__(self, origin: str, destination: str, advance_days: int = 7, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.origin = origin.upper()
        self.destination = destination.upper()
        self.advance_days = int(advance_days)
        self.travel_date = datetime.utcnow().date() + timedelta(days=self.advance_days)

    def start_requests(self):
        search_url = (
            f"https://www.goibibo.com/flights/search"
            f"?origin={self.origin}&destination={self.destination}"
            f"&departure={self.travel_date.isoformat()}"
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
        item["source"] = "goibibo"
        item["source_type"] = "ota"
        item["origin"] = self.origin
        item["destination"] = self.destination
        item["carrier"] = flight.get("airline", "6E")
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