"""
APIx API entrypoint.

Run locally with:  uvicorn api.main:app --reload
On Render, the start command is the same — Render just runs it as the
web service's process (see render.yaml).
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers.index import router as index_router

app = FastAPI(
    title="APIx — Real-time Airfare Price Index for India",
    description=(
        "Daily/weekly/monthly airfare price index computed from scraped "
        "Indian airline and OTA fare data, weighted by DGCA route traffic. "
        "See /docs for the full schema."
    ),
    version="1.0.0",
)

_allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins or ["*"],  # tighten in production via env var
    allow_methods=["GET"],
    allow_headers=["x-api-key"],
)

app.include_router(index_router)


@app.get("/healthz", tags=["meta"])
async def health_check() -> dict:
    return {"status": "ok"}
