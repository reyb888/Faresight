"""
Vercel serverless entrypoint for Faresight API & Dashboard.
"""
from api.main import app

__all__ = ["app"]
