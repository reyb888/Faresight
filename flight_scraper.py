"""
Crawlee Flight Scraper with Error Isolation
Each airline/route runs in isolation - failures buried, don't stop pipeline
"""
import asyncio
import logging
import os
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import date, timedelta
from crawlee import PlaywrightCrawler
from crawlee.configuration import Configuration
from crawlee.playwright_crawler import PlaywrightCrawlingContext
from crawlee.configuration import Configuration as CrawleeConfig
from crawlee.proxy_configuration import ProxyConfiguration
import json

logger = logging.getLogger(__name__)

@dataclass
class ScrapedFare:
    route: str
    airline: str
    flight_date: str
    lead_time_days: int
    price: float
    currency: str
    source: str
    scraped_at: str

class FlightScraper:
    """Crawlee-based flight scraper with per-route error isolation"""
    
    def __init__(self, headless: bool = True, max_concurrent: int = 2):
        self.results: List[dict] = []
        self.errors: List[dict] = []
        self.max_concurrent = max_concurrent
        
        self.crawler = PlaywrightCrawler(
            max_requests_per_crawl=50,
            max_requests_per_minute=10,
            headless=True,
            max_session_rotations=3,
            max_session_rotations=3,
            persist_cookies=False,
            launch_context={
                "launch_options": {
                    "headless": True,
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                    ],
                },
            },
            max_requests_per_crawl=50,
            max_request_retries=2,
        )
        
        # Setup error handler
        self.crawler.router.default_handler(self._default_handler)
    
    async def _default_handler(self, context):
        """Default handler - override per-route"""
        pass
    
    def _extract_fares_from_page(self, page, route: str, flight_date: str, lead_time: int) -> List[dict]:
        """Extract fare data from page - override per site"""
        raise NotImplementedError("Override per site")
    
    async def scrape_route(
        self, 
        origin: str, 
        destination: str, 
        flight_date: date, 
        lead_time: int,
        serpapi_key: str = None
    ) -> List[dict]:
        """Scrape single route - errors buried, returns empty list on failure"""
        route_key = f"{origin}-{destination}-{flight_date.isoformat()}"
        logger.info(f"Scraping {route_key} (T+{lead_time})")
        
        route_results = []
        route_errors = []
        
        try:
            # This is where you'd add SerpApi + Crawlee combo
            # For now, return empty - implement per-site handlers
            route_results = await self._scrape_with_fallback(
                origin, destination, flight_date, lead_time
            )
            
            return route_results
            
        except Exception as e:
            error_info = {
                "route": f"{origin}-{destination}",
                "date": flight_date.isoformat(),
                "lead_time": lead_time,
                "error": str(e),
                "type": type(e).__name__
            }
            logger.error(f"Route {origin}-{destination} failed: {e}")
            return []  # Bury error, return empty
    
    async def _scrape_with_fallback(self, origin, destination, flight_date, lead_time) -> List[dict]:
        """Override with actual SerpApi + Crawlee implementation"""
        return []
    
    async def scrape_multiple_routes(
        self,
        routes: List[tuple],  # [(origin, dest), ...]
        lead_times: List[int],
        start_date: date = None
    ) -> List[dict]:
        """Scrape multiple routes concurrently with error isolation"""
        if start_date is None:
            start_date = date.today()
        
        all_results = []
        
        # Create tasks for each route/lead_time combo
        tasks = []
        for origin, dest in routes:
            for lt in lead_times:
                flight_date = date.today() + timedelta(days=lt)
                tasks.append(self.scrape_route(origin, destination, flight_date, lt))
        
        # Run with semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def bounded_scrape(task):
            async with semaphore:
                return await task
        
        results = await asyncio.gather(
            *[bounded_scrape(t) for t in tasks],
            return_exceptions=True
        )
        
        # Flatten results, bury exceptions
        all_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Task {i} failed: {result}")
            elif isinstance(result, list):
                all_results.extend(result)
        
        return all_results


class SerpApiCrawler(FlightScraper):
    """SerpApi + Crawlee hybrid scraper"""
    
    def __init__(self, serpapi_keys: List[str], **kwargs):
        super().__init__(**kwargs)
        self.serpapi_keys = serpapi_keys
        self.key_index = 0
        
    def _get_next_key(self) -> str:
        """Simple round-robin key rotation"""
        key = self.serpapi_keys[self.key_index % len(self.serpapi_keys)]
        self.key_index = (self.key_index + 1) % len(self.serpapi_keys)
        return key
    
    async def _scrape_with_fallback(
        self, 
        origin: str, 
        destination: str, 
        flight_date: date, 
        lead_time: int
    ) -> List[dict]:
        """Use SerpApi Google Flights + fallback to Crawlee if needed"""
        results = []
        
        # Try SerpApi first (fast, structured)
        serpapi_results = await self._serpapi_google_flights(
            origin, destination, flight_date
        )
        
        if serpapi_results:
            return serpapi_results
        
        # Fallback to Crawlee if SerpApi fails
        logger.info("SerpApi failed, falling back to Crawlee")
        return await self._crawlee_fallback(origin, destination, flight_date)
    
    async def _serpapi_google_flights(self, origin, destination, flight_date) -> List[dict]:
        """Use SerpApi Google Flights engine"""
        import httpx
        
        key = self._get_next_key()
        params = {
            "engine": "google_flights",
            "q": f"{origin} {destination}",
            "gl": "in",
            "hl": "en",
            "date": flight_date.isoformat(),
            "currency": "INR",
            "api_key": self._get_next_key(),
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://serpapi.com/search",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                if "error" in data:
                    logger.warning(f"SerpApi error: {data['error']}")
                    return []
                
                return self._parse_serpapi_flights(data)
                
        except Exception as e:
            logger.warning(f"SerpApi request failed: {e}")
            return []
    
    def _parse_serpapi_flights(self, data: dict) -> List[dict]:
        """Parse SerpApi Google Flights response"""
        results = []
        
        try:
            flights_data = data.get("flights", [])
            for flight_group in flights_data:
                routes = flight_group.get("routes", [])
                for route in routes:
                    fare_groups = route.get("fare_groups", [])
                    for fare_group in fare_groups:
                        flights = fare_group.get("flights", [])
                        for flight in flights:
                            price_str = flight.get("price")
                            if price_str:
                                try:
                                    price = float(str(price_str).replace(",", "").replace("₹", "").replace("Rs", ""))
                                except:
                                    continue
                                
                                results.append({
                                    "airline": flight.get("airline") or route.get("airline"),
                                    "price": price,
                                    "currency": "INR",
                                    "departure": flight.get("departure_airport", {}).get("name"),
                                    "arrival": flight.get("arrival_airport", {}).get("name"),
                                    "departure_time": flight.get("departure_time"),
                                    "arrival_time": flight.get("arrival_time"),
                                    "duration": flight.get("duration"),
                                    "flight_number": flight.get("flight_number"),
                                    "stops": flight.get("stops", 0),
                                })
        except Exception as e:
            logger.warning(f"SerpApi parsing failed: {e}")
        
        return results
    
    async def _crawlee_fallback(self, origin, destination, flight_date) -> List[dict]:
        """Fallback to Crawlee if SerpApi fails"""
        # Implement actual Crawlee scraping here
        logger.info(f"Crawlee fallback for {origin}-{destination}")
        return []


# Async function to run scraper pipeline
async def run_scraper_pipeline(
    routes: List[tuple],
    lead_times: List[int],
    serpapi_keys: List[str],
    max_concurrent: int = 2
) -> List[dict]:
    """Main pipeline entry point"""
    
    scraper = SerpApiCrawler(
        serpapi_keys=serpapi_keys,
        max_concurrent=2,
    )
    
    if not lead_times:
        lead_times = [1, 3, 5, 7, 15, 30, 45]
    
    routes = routes or [
        ("DEL", "BOM"),
        ("BLR", "DEL"),
        ("MAA", "DEL"),
        ("CCU", "BOM"),
        ("HYD", "DEL"),
    ]
    
    lead_times = lead_times or [1, 3, 5, 7, 15, 30, 45]
    
    results = await scraper.scrape_multiple_routes(
        routes=routes,
        lead_times=lead_times,
        max_concurrent=2
    )
    
    logger.info(f"Scraping complete: {len(results)} fares collected")
    return results


# Quick test function
async def test_scraper():
    """Quick test with your 5 SerpApi keys"""
    keys = [
        os.getenv("SERP_API_KEY_1"),
        os.getenv("SERP_API_KEY_2"),
        os.getenv("SERP_API_KEY_3"),
        os.getenv("SERP_API_KEY_4"),
        os.getenv("SERP_API_KEY_5"),
    ]
    keys = [k for k in keys if k]
    
    if not keys:
        logger.warning("No SerpApi keys found in env")
        return []
    
    return await run_scraper_pipeline(
        serpapi_keys=keys,
        max_concurrent=2
    )


if __name__ == "__main__":
    asyncio.run(test_scraper())