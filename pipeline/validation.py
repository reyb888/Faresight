"""
Item pipeline stage: validate every scraped item against FareQuoteModel
before it's allowed further downstream. See docs/DESIGN.md §3.1.
"""
import structlog
from scrapy.exceptions import DropItem

from scraper.items import FareQuoteModel

logger = structlog.get_logger()


class ValidationPipeline:
    def process_item(self, item, spider):
        try:
            validated = FareQuoteModel(**dict(item))
        except Exception as exc:  # pydantic.ValidationError, mainly
            logger.warning(
                "item_validation_failed",
                spider=spider.name,
                error=str(exc),
                raw_item=dict(item),
            )
            raise DropItem(f"Invalid item from {spider.name}: {exc}") from exc

        # Return the validated (and normalized — e.g. uppercased IATA codes)
        # version so downstream stages work off clean data.
        return validated.model_dump()
