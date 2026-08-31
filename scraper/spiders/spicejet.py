"""
Real SpiceJet low-cost carrier spider for SIH26056.
"""
from datetime import datetime, timedelta
import scrapy

from scraper.items import FareQuoteItem


class SpiceJetSpider(scrapy.Spider):
    name = "spicejet"
    allowed_domains = ["spicejet.com"]

    custom_settings = {}

    def __init__(self, origin: str, destination: str, advance_days: int = 7, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.origin = origin.upper()
        self.destination = destination.upper()
        self.advance_days = int(advance_days)
        self.travel_date = datetime.utcnow().date() + timedelta(days=self.advance_days)

    def start_requests(self):
        search_url = (
            f"https://www.spicejet.com/search"
            f"?origin={self.origin}&destination={self.destination}"
            f"&date={self.travel_date.isoformat()}"
        )
        yield scrapy.Request(
            search_url,
            callback=self.parse_search_results,
            meta={"playwright": True},
        )

    def parse_search_results(self, response: scrapy.http.Response):
        try:
            data = response.json()
            if isinstance(data, dict) and "flights" in data:
                for flight in data["flights"]:
                    yield self._build_item(flight)
                return
        except Exception:
            pass

        self.logger.info("SpiceJet search results for %s → %s (T+%s)", self.origin, self.destination, self.advance_days)

        flights = response.css(".flight-card, .flight-row, .search-result")
        if flights:
            for flight in flights:
                yield self._build_item_from_dom(flight)
        else:
            self.logger.warning("No flight data found for SpiceJet %s → %s (T+%s)", self.origin, self.destination, self.advance_days)

    def _build_item(self, flight: dict) -> FareQuoteItem:
        item = FareQuoteItem()
        item["source"] = "spicejet"
        item["source_type"] = "airline_direct"
        item["origin"] = self.origin
        item["destination"] = self.destination
        item["carrier"] = "UK"
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

    def _build_item_from_dom(self, flight) -> FareQuoteItem:
        item = FareQuoteItem()
        item["source"] = "spicejet"
        item["source_type"] = "airline_direct"
        item["origin"] = self.origin
        item["destination"] = self.destination
        item["carrier"] = "UK"
        item["flight_number"] = flight.css(".flight-number::text").get()
        item["fare_class"] = flight.css(".fare-class::text").get()
        item["travel_date"] = self.travel_date
        item["advance_purchase_days"] = self.advance_days
        item["observed_at"] = datetime.utcnow()
        item["base_fare"] = flight.css(".base-fare::text").get()
        item["taxes_fees"] = flight.css(".taxes::text").get()
        item["total_fare"] = flight.css(".total-fare::text").get()
        item["currency"] = "INR"
        item["availability_status"] = "available" if flight.css(".available::text").get() else "sold_out"
        item["raw_payload"] = {"dom": True}
        return item