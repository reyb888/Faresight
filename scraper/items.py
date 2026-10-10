"""
Shared fare-quote item schema. Every spider yields this shape — see
docs/DESIGN.md §2.1. Keeping one schema across all sources is what lets the
pipeline, index engine, and API stay source-agnostic.
"""
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class FareQuoteItem:
    """Scrapy Item version - used by spiders during scraping."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FareQuoteModel(BaseModel):
    """pydantic validation gate — every item passes through this before
    it's allowed into the DB. See docs/DESIGN.md §3.1."""

    source: str
    source_type: str
    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    carrier: str
    flight_number: str | None = None
    fare_class: str | None = None
    travel_date: date
    advance_purchase_days: int = Field(ge=0)
    observed_at: datetime
    base_fare: float | None = None
    taxes_fees: float | None = None
    total_fare: float | None = None
    currency: str = "INR"
    availability_status: str = "available"
    raw_payload: dict | None = None

    @field_validator("origin", "destination")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("source_type")
    @classmethod
    def _valid_source_type(cls, v: str) -> str:
        if v not in {"airline_direct", "ota"}:
            raise ValueError("source_type must be 'airline_direct' or 'ota'")
        return v