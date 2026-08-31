"""
APIx API entrypoint.

Run locally with:  uvicorn api.main:app --reload
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

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
    allow_origins=_allowed_origins or ["*"],
    allow_methods=["GET"],
    allow_headers=["x-api-key"],
)

app.include_router(index_router)


@app.get("/healthz", tags=["meta"])
async def health_check() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root_portal() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>APIx | Real-time Airfare Price Index for India</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #090d16;
            --card-bg: rgba(18, 26, 44, 0.75);
            --border: rgba(255, 255, 255, 0.1);
            --primary: #38bdf8;
            --accent: #818cf8;
            --text: #f8fafc;
            --muted: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        body {
            background-color: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem 1rem;
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(56, 189, 248, 0.15) 0%, transparent 40%),
                radial-gradient(circle at 85% 85%, rgba(129, 140, 248, 0.15) 0%, transparent 40%);
        }
        .container {
            max-width: 900px;
            width: 100%;
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 3rem;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }
        .header { margin-bottom: 2rem; text-align: center; }
        .badge {
            display: inline-block;
            padding: 0.35rem 0.85rem;
            background: rgba(56, 189, 248, 0.1);
            border: 1px solid rgba(56, 189, 248, 0.3);
            color: var(--primary);
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 1rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        h1 {
            font-size: 2.75rem;
            font-weight: 800;
            background: linear-gradient(135deg, #ffffff 0%, #94a3b8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.75rem;
        }
        p.subtitle { color: var(--muted); font-size: 1.1rem; max-width: 650px; margin: 0 auto; line-height: 1.6; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5rem; margin: 2.5rem 0; }
        .card {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
            transition: all 0.3s ease;
            text-decoration: none;
            color: inherit;
        }
        .card:hover {
            transform: translateY(-4px);
            border-color: var(--primary);
            background: rgba(56, 189, 248, 0.05);
        }
        .card h3 { font-size: 1.2rem; margin-bottom: 0.5rem; color: var(--primary); display: flex; align-items: center; justify-content: space-between; }
        .card p { font-size: 0.9rem; color: var(--muted); line-height: 1.5; }
        .interactive-box {
            background: #030712;
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
            font-family: 'JetBrains Mono', monospace;
        }
        .interactive-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
        .btn {
            background: linear-gradient(135deg, var(--primary), var(--accent));
            color: #000;
            font-weight: 700;
            border: none;
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        .btn:hover { opacity: 0.9; }
        pre { color: #38bdf8; font-size: 0.85rem; overflow-x: auto; max-height: 250px; }
        footer { margin-top: 2.5rem; text-align: center; color: var(--muted); font-size: 0.85rem; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="badge">SIH 2026 | Problem Statement SIH26056</span>
            <h1>APIx (Faresight) Portal</h1>
            <p class="subtitle">Real-time Airfare Price Index Engine for India. Scrapes airline & OTA data daily, applies outlier cleaning, and computes weighted Laspeyres indices for CPI augmentation.</p>
        </div>

        <div class="grid">
            <a href="/docs" class="card" target="_blank">
                <h3>Swagger API Docs <span>&rarr;</span></h3>
                <p>Explore interactive OpenAPI endpoints, schema definitions, and parameters.</p>
            </a>
            <a href="/v1/index" class="card" target="_blank">
                <h3>Airfare Index Endpoint <span>&rarr;</span></h3>
                <p>Fetch real-time daily, weekly, and monthly price index computations.</p>
            </a>
            <a href="/healthz" class="card" target="_blank">
                <h3>Health Check <span>&rarr;</span></h3>
                <p>Verify serverless runtime status and Supabase database availability.</p>
            </a>
        </div>

        <div class="interactive-box">
            <div class="interactive-header">
                <span style="color: var(--muted); font-weight: 600;">GET /v1/index</span>
                <button class="btn" onclick="testApi()">Run Live Query</button>
            </div>
            <pre id="json-output">// Click "Run Live Query" to fetch index response...</pre>
        </div>

        <footer>
            Built for Smart India Hackathon 2026 • MoSPI Airfare Index System
        </footer>
    </div>

    <script>
        async function testApi() {
            const output = document.getElementById('json-output');
            output.textContent = '// Loading...';
            try {
                const res = await fetch('/v1/index');
                const data = await res.json();
                output.textContent = JSON.stringify(data, null, 2);
            } catch (err) {
                output.textContent = '// Error fetching API: ' + err.message;
            }
        }
    </script>
</body>
</html>"""
