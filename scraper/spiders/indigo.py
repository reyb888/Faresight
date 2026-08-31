"""
Template spider for an airline-direct source (IndiGo used as the example).

This is a structural template - the actual CSS/XPath selectors or network
response shape depend on the live site at the time you build this, which
changes and needs to be inspected directly by the team (open devtools ->
Network tab on the real fare-search flow, find whether fares come back as
JSON from an XHR call or are rendered into the DOM, then fill in
parse_search_results accordingly). Everything else — scheduling shape,
rate-limit inheritance, item construction, ethical constraints — is meant
to be reused as-is across every other spider.

Run a single test crawl:
    scrapy crawl indigo -a origin=DEL -a destination=BOM -a advance_days=7
"""
from datetime import datetime, timedelta

import scrapy

from scraper.items import FareQuoteItem


class IndigoSpider(scrapy.Spider):
    name = "indigo"
    allowed_domains = ["goindigo.in"]

    custom_settings = {
        # Per-source overrides go here if IndiGo needs different pacing
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
        # TODO: replace with the real fare-search URL pattern once inspected.
        # Many airline sites expose a JSON search API you can hit directly
        # (preferred — skip Playwright entirely if so, it's lighter and
        # faster). Only fall back to meta={"playwright": True} if the fare
        # only appears after client-side JS execution.
        search_url = (
            f"https://www.goindigo.in/search"
            f"?origin={self.origin}&destination={self.destination}"
            f"&date={self.travel_date.isoformat()}"
        )
        yield scrapy.Request(
            search_url,
            callback=self.parse_search_results,
            meta={"playwright": True},  # remove if a direct JSON API is found instead
        )

    def parse_search_results(self, response: scrapy.http.Response):
        # TODO: replace with real selectors/JSON parsing for the live site.
        # Example shape for a JSON-API-backed page:
        #
        #   data = response.json()
        #   for flight in data["flights"]:
        #       yield self._build_item(flight)
        #
        # Example shape for a DOM-rendered page:
        #
        #   for card in response.css(".flight-card"):
        #       yield self._build_item_from_dom(card)
        self.logger.warning(
            "parse_search_results is a template — fill in real selectors "
            "for %s before this spider produces data.",
            self.name,
        )
        return

    def _build_item(self, flight: dict) -> FareQuoteItem:
        """Example helper once real field names are known — adjust the
        dict keys to match whatever the real response actually contains."""
        item = FareQuoteItem()
        item["source"] = "indigo"
        item["source_type"] = "airline_direct"
        item["origin"] = self.origin
        item["destination"] = self.destination
        item["carrier"] = "6E"
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