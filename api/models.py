from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


Frequency = Literal["daily", "weekly", "monthly"]


class IndexPoint(BaseModel):
    index_date: date
    frequency: Frequency
    index_value: float
    base_period_ref: date
    route_count: int
    quote_count: int


class RouteSeriesPoint(BaseModel):
    observed_date: date
    median_total_fare: float
    quote_count: int


class RouteSeries(BaseModel):
    origin: str
    destination: str
    points: list[RouteSeriesPoint]


class HeatmapCell(BaseModel):
    origin: str
    destination: str
    advance_purchase_days: int
    median_total_fare: float


class ElasticityPoint(BaseModel):
    advance_purchase_days: int
    median_total_fare: float


class BacktestRow(BaseModel):
    period: date
    apix_value: float
    dgca_avg_fare: float
    pct_deviation: float


class RouteWeight(BaseModel):
    origin: str
    destination: str
    weight: float
    effective_period: date


class APIKey(BaseModel):
    key: str
    is_valid: bool = True