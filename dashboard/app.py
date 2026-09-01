"""
Faresight Dashboard — SIH26056
Real-time Airfare Price Index for India.

Problem (SIH26056): India has no real-time airfare inflation index.
DGCA publishes monthly averages with ~2 month lag — too slow for CPI.
Faresight scrapes airline + OTA sites daily across 6 representative
routes × 5 advance-purchase windows (T+1, T+7, T+15, T+30, T+45),
cleans with MAD outlier detection, and publishes a Base-100 weighted
index (100 = base week 2026-01-06). This dashboard is the public face
of that pipeline — and a thin proxy over /v1/* API.
"""

from datetime import date

import requests
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# -- SIH26056 basket (DGCA-weighted representative routes)
ROUTES = [
    {
        "id": "del-bom",
        "origin": "DEL",
        "destination": "BOM",
        "name": "Delhi ↔ Mumbai",
        "traffic": "High",
    },
    {
        "id": "del-blr",
        "origin": "DEL",
        "destination": "BLR",
        "name": "Delhi ↔ Bengaluru",
        "traffic": "High",
    },
    {
        "id": "bom-blr",
        "origin": "BOM",
        "destination": "BLR",
        "name": "Mumbai ↔ Bengaluru",
        "traffic": "High",
    },
    {
        "id": "del-ccu",
        "origin": "DEL",
        "destination": "CCU",
        "name": "Delhi ↔ Kolkata",
        "traffic": "Medium",
    },
    {
        "id": "blr-hyd",
        "origin": "BLR",
        "destination": "HYD",
        "name": "Bengaluru ↔ Hyderabad",
        "traffic": "Medium",
    },
    {
        "id": "maa-del",
        "origin": "MAA",
        "destination": "DEL",
        "name": "Chennai ↔ Delhi",
        "traffic": "Medium",
    },
]

WINDOWS = [1, 7, 15, 30, 45]
WINDOW_LABELS = {
    1: "Tomorrow",
    7: "In 1 week",
    15: "In 2 weeks",
    30: "In 1 month",
    45: "In 45 days",
}

BASE_PERIOD = date(2026, 1, 6)
API_BASE = "http://127.0.0.1:8000"
API_KEY = "test-key"


# -- helpers
def call_api(path, params=None):
    try:
        r = requests.get(
            f"{API_BASE}{path}",
            params=params or {},
            headers={"x-api-key": API_KEY},
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def route_by_id(rid):
    return next((r for r in ROUTES if r["id"] == rid), None)


# -- pages
@app.route("/")
def index():
    return render_template(
        "dashboard.html",
        routes=ROUTES,
        windows=WINDOWS,
        window_labels=WINDOW_LABELS,
        base_period=BASE_PERIOD,
    )


# -- proxy api (keeps dashboard thin, no direct DB)
@app.route("/api/index")
def api_index():
    freq = request.args.get("frequency", "daily")
    data = call_api("/v1/index", {"frequency": freq})
    return jsonify(data or [])


@app.route("/api/route-data")
def api_route_data():
    rid = request.args.get("route", "")
    window = int(request.args.get("window", 7))
    route = route_by_id(rid)
    if not route:
        return jsonify({"error": "Invalid route"}), 400
    days = max(7, window * 4)
    data = call_api(
        f"/v1/routes/{route['origin']}/{route['destination']}", {"days": days}
    )
    points = (data or {}).get("points", []) if isinstance(data, dict) else []
    return jsonify(
        {
            "route": route,
            "window": window,
            "label": WINDOW_LABELS.get(window, f"T+{window}"),
            "points": points,
        }
    )


@app.route("/api/heatmap")
def api_heatmap():
    data = call_api("/v1/heatmap")
    return jsonify(data or [])


@app.route("/api/elasticity")
def api_elasticity():
    rid = request.args.get("route", "")
    route = route_by_id(rid)
    if not route:
        return jsonify([])
    data = call_api(f"/v1/routes/{route['origin']}/{route['destination']}/elasticity")
    return jsonify(data or [])


@app.route("/api/backtest")
def api_backtest():
    data = call_api("/v1/backtest")
    return jsonify(data or [])


@app.route("/api/route/<route_id>")
def api_route_detail(route_id):
    route = route_by_id(route_id)
    if not route:
        return jsonify({"error": "Invalid route"}), 404
    window = int(request.args.get("window", 7))
    days = max(7, window * 4)
    data = call_api(
        f"/v1/routes/{route['origin']}/{route['destination']}", {"days": days}
    )
    points = (data or {}).get("points", []) if isinstance(data, dict) else []
    return jsonify({"route": route, "window": window, "points": points})


@app.route("/api/comparison")
def api_comparison():
    ids = request.args.getlist("routes")
    # also support comma-separated
    if len(ids) == 1 and "," in ids[0]:
        ids = [x.strip() for x in ids[0].split(",") if x.strip()]
    window = int(request.args.get("window", 7))
    days = max(7, window * 4)
    out = []
    for rid in ids:
        route = route_by_id(rid)
        if not route:
            continue
        data = call_api(
            f"/v1/routes/{route['origin']}/{route['destination']}", {"days": days}
        )
        points = (data or {}).get("points", []) if isinstance(data, dict) else []
        if points:
            fares = [p["median_total_fare"] for p in points]
            out.append(
                {
                    "route": route["name"],
                    "origin": route["origin"],
                    "destination": route["destination"],
                    "id": route["id"],
                    "avg_fare": round(sum(fares) / len(fares), 2),
                    "min_fare": round(min(fares), 2),
                    "max_fare": round(max(fares), 2),
                    "points": len(points),
                }
            )
    return jsonify(
        {
            "results": out,
            "window": window,
            "label": WINDOW_LABELS.get(window, f"T+{window}"),
        }
    )


@app.route("/api/windows")
def api_windows():
    return jsonify(
        {
            "windows": WINDOWS,
            "labels": WINDOW_LABELS,
            "base_period": BASE_PERIOD.isoformat(),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
