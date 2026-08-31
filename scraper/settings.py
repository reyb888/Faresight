"""
Scrapy settings enforcing the ethical-scraping constraints from
docs/SECURITY.md §1. Every spider inherits these unless explicitly
overridden per-source with a documented reason.
"""
import os

BOT_NAME = "apix"

SPIDER_MODULES = ["scraper.spiders"]
NEWSPIDER_MODULE = "scraper.spiders"

# --- Identify honestly rather than spoofing a real browser (SECURITY.md §1.3) ---
USER_AGENT = os.environ.get(
    "SCRAPE_USER_AGENT",
    "APIx-ResearchBot/1.0 (+https://your-project-contact-page)",
)

# --- Respect robots.txt by default (SECURITY.md §1.1) ---
ROBOTSTXT_OBEY = True

# --- Rate limiting (SECURITY.md §1.2) ---
DOWNLOAD_DELAY = float(os.environ.get("SCRAPE_MIN_DELAY_SECONDS", 3))
RANDOMIZE_DOWNLOAD_DELAY = True  # adds jitter so requests aren't mechanically spaced
CONCURRENT_REQUESTS_PER_DOMAIN = 2
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 3
AUTOTHROTTLE_MAX_DELAY = 30
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# --- Retry / backoff on transient blocks, not aggressive hammering ---
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# --- JS rendering via Playwright for sources that need it ---
DOWNLOAD_HANDLERS = {
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30_000  # ms

# --- Item pipeline (schema validation -> DB write) ---
ITEM_PIPELINES = {
    "pipeline.validation.ValidationPipeline": 100,
    "pipeline.loader.SupabaseLoaderPipeline": 300,
}

# --- Logging ---
LOG_LEVEL = "INFO"

# Never scrape authenticated/checkout flows — every spider should only hit
# public fare-search result pages. See docs/SECURITY.md §1.1.