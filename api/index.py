"""
Vercel serverless entrypoint for Faresight API & Dashboard.
"""
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
api_dir = Path(__file__).resolve().parent
for p in (str(root_dir), str(api_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from api.main import app
except ImportError:
    from main import app

__all__ = ["app"]
