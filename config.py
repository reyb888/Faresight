import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# SERP API KEY MANAGEMENT (Multi-key Round-Robin)
# ============================================================
SERP_API_KEYS_ENV = os.environ.get("SERP_API_KEYS", "")
SERP_API_KEYS = [k.strip() for k in SERP_API_KEYS_ENV.split(",") if k.strip()]


# Active pointer for round-robin rotation
SERP_API_KEY_POINTER = 0

# ============================================================
# TARGET FLIGHT ROUTES (Indian Corridors)
# ============================================================
ROUTES = [
    {"origin_code": "DEL", "destination_code": "BOM", "route_name": "DEL → BOM"},
    {"origin_code": "BLR", "destination_code": "DEL", "route_name": "BLR → DEL"},
    {"origin_code": "MAA", "destination_code": "DEL", "route_name": "MAA → DEL"},
    {"origin_code": "CCU", "destination_code": "BOM", "route_name": "CCU → BOM"},
    {"origin_code": "HYD", "destination_code": "DEL", "route_name": "HYD → DEL"},
]

# ============================================================
# LEAD-TIME BUCKETS (Days in advance)
# ============================================================
LEAD_TIMES = [1, 3, 5, 7, 15, 30, 45]

# ============================================================
# INDEX WEIGHTING CONFIGURATION
# ============================================================
# Short-Term Bucket (T+1, T+3): Weight = 0.40
# Medium-Term Bucket (T+5, T+7, T+15): Weight = 0.35
# Long-Term Bucket (T+30, T+45): Weight = 0.25
INDEX_WEIGHTS = {
    "short_term": 0.40,
    "medium_term": 0.35,
    "long_term": 0.25,
}

# ============================================================
# FASTAPI / SERVER CONFIGURATION
# ============================================================
API_V1_PREFIX = "/api/v1"
API_PREFIX = "/api"

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# ============================================================
# SERPAPI FETCHER SETTINGS
# ============================================================
SERPAPI_DEFAULT_TIMEOUT = float(os.environ.get("SERPAPI_TIMEOUT", "4.0"))  # seconds
SERPAPI_MAX_RETRIES = int(os.environ.get("SERPAPI_MAX_RETRIES", "2"))
SERPAPI_FALLBACK_TO_CACHE = os.environ.get("SERPAPI_FALLBACK_TO_CACHE", "true").lower() == "true"

# ============================================================
# AUTHENTICATION
# ============================================================
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "sih2026admin")

# ============================================================
# DATABASE
# ============================================================
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "airfare.db")
DB_PATH = os.environ.get("AIRFARE_DB_PATH", DEFAULT_DB_PATH)
INIT_DB = os.environ.get("INIT_DB", "true").lower() == "true"