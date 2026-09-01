"""
Faresight API entrypoint.
Run locally with: uvicorn api.main:app --reload
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from api.routers.index import router as index_router

app = FastAPI(
    title="Faresight - Real-time Airfare Price Index for India",
    description=(
        "Daily, weekly and monthly airfare price index computed from scraped "
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
<title>Faresight - Real-time Airfare Price Index for India</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/@phosphor-icons/web"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#0e4a7a}
*{font-family:'DM Sans',system-ui,sans-serif}
.mono{font-family:'JetBrains Mono',monospace}
</style>
</head>
<body class="bg-[#fcfdf8] text-slate-900 antialiased">
<nav class="sticky top-0 z-40 bg-white/90 backdrop-blur border-b border-slate-200">
  <div class="max-w-7xl mx-auto px-6 h-[64px] flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="w-9 h-9 rounded-xl bg-slate-900 text-white grid place-items-center font-bold">F</div>
      <div>
        <div class="font-semibold tracking-tight leading-none">Faresight</div>
        <div class="text-xs text-slate-500">MoSPI • SIH26056</div>
      </div>
    </div>
    <div class="hidden md:flex items-center gap-3">
      <a href="/docs" class="text-sm font-medium text-slate-600 hover:text-slate-900">API Docs</a>
      <a href="http://localhost:5000" class="px-4 py-2 rounded-full bg-slate-900 text-white text-sm font-semibold hover:bg-slate-800 transition">Open Dashboard</a>
    </div>
  </div>
</nav>

<main class="max-w-7xl mx-auto px-6">
  <section class="grid md:grid-cols-2 gap-10 items-center pt-12 pb-10 md:pt-16">
    <div>
      <p class="text-xs font-semibold tracking-widest uppercase text-slate-500 mb-3">SIH26056 • Ministry of Statistics and Programme Implementation</p>
      <h1 class="text-4xl md:text-5xl font-semibold tracking-tight leading-none">A live airfare index<br>for India</h1>
      <p class="mt-4 text-base leading-relaxed text-slate-600 max-w-[52ch]">DGCA averages arrive two months late. Faresight scrapes airlines and OTAs daily, cleans the data, and publishes a Base 100 index weighted by passenger traffic.</p>
      <div class="mt-6 flex gap-3">
        <a href="http://localhost:5000" class="px-5 py-3 rounded-full bg-slate-900 text-white text-sm font-semibold">View live index</a>
        <a href="/docs" class="px-5 py-3 rounded-full border border-slate-200 bg-white text-sm font-semibold">Explore API</a>
      </div>
      <div class="mt-6 flex gap-6 text-xs text-slate-500">
        <span class="flex items-center gap-1.5"><i class="ph ph-check-circle text-emerald-600"></i> Daily scrape</span>
        <span class="flex items-center gap-1.5"><i class="ph ph-check-circle text-emerald-600"></i> MAD outlier filter</span>
        <span class="flex items-center gap-1.5"><i class="ph ph-check-circle text-emerald-600"></i> DGCA weighted</span>
      </div>
    </div>
    <div class="relative">
      <img src="https://picsum.photos/seed/faresight-hero-india/800/600" alt="Aerial view of India flight corridors at dusk" class="w-full h-[380px] object-cover rounded-2xl border border-slate-200">
      <div class="absolute -bottom-4 -left-4 bg-white border border-slate-200 rounded-2xl p-4 shadow-sm max-w-[260px]">
        <div class="text-xs font-semibold tracking-widest uppercase text-slate-500">Faresight Daily</div>
        <div class="mono text-2xl font-semibold mt-1">104.24 <span class="text-sm text-slate-500 font-normal">/ 100</span></div>
        <div class="text-xs text-emerald-700 mt-1">Up 4.24 percent vs base week Jan 6 2026</div>
      </div>
    </div>
  </section>

  <section class="grid md:grid-cols-4 gap-4 py-6 border-y border-slate-200">
    <div class="bg-white border border-slate-200 rounded-2xl p-5">
      <div class="text-xs font-semibold tracking-widest uppercase text-slate-500">Daily index</div>
      <div class="mono text-2xl font-semibold mt-2">104.24</div>
      <div class="text-xs text-slate-500 mt-1">Base 100 • Jan 6 2026</div>
    </div>
    <div class="bg-white border border-slate-200 rounded-2xl p-5">
      <div class="text-xs font-semibold tracking-widest uppercase text-slate-500">Corridors</div>
      <div class="mono text-2xl font-semibold mt-2">6</div>
      <div class="text-xs text-slate-500 mt-1">DEL BOM BLR CCU HYD MAA</div>
    </div>
    <div class="bg-white border border-slate-200 rounded-2xl p-5">
      <div class="text-xs font-semibold tracking-widest uppercase text-slate-500">Windows</div>
      <div class="mono text-2xl font-semibold mt-2">T+1 to T+45</div>
      <div class="text-xs text-slate-500 mt-1">Advance purchase aware</div>
    </div>
    <div class="bg-white border border-slate-200 rounded-2xl p-5">
      <div class="text-xs font-semibold tracking-widest uppercase text-slate-500">Cleaning</div>
      <div class="mono text-2xl font-semibold mt-2">99.4%</div>
      <div class="text-xs text-slate-500 mt-1">Median Absolute Deviation</div>
    </div>
  </section>

  <section class="grid md:grid-cols-12 gap-6 py-8">
    <div class="md:col-span-8 bg-white border border-slate-200 rounded-2xl p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="font-semibold tracking-tight">Index trajectory 2026</h2>
        <span class="text-xs text-slate-500">Daily • Base 100</span>
      </div>
      <div class="h-[300px]"><canvas id="indexChart"></canvas></div>
    </div>
    <div class="md:col-span-4 bg-slate-900 text-white rounded-2xl p-6 relative overflow-hidden">
      <img src="https://picsum.photos/seed/faresight-method/600/400" alt="Close up of airport departure board" class="absolute inset-0 w-full h-full object-cover opacity-20">
      <div class="relative">
        <h3 class="font-semibold">How the index is built</h3>
        <p class="text-sm leading-relaxed text-slate-300 mt-2">We sample each route and window, keep the median fare, then weight by DGCA traffic.</p>
        <div class="mt-4 bg-white/10 rounded-xl p-3 mono text-xs leading-relaxed">F(t) = sum [ w × ( P(t) / P(0) ) ] × 100</div>
        <ul class="mt-4 text-sm leading-relaxed text-slate-300 space-y-1">
          <li><span class="text-white font-medium">w</span> DGCA passenger share for the route</li>
          <li><span class="text-white font-medium">P(t)</span> Median fare on day t</li>
          <li><span class="text-white font-medium">P(0)</span> Median fare in base week</li>
        </ul>
        <a href="http://localhost:5000" class="inline-flex mt-6 px-4 py-2 rounded-full bg-white text-slate-900 text-sm font-semibold">Open full dashboard</a>
      </div>
    </div>
  </section>

  <section class="bg-white border border-slate-200 rounded-2xl p-6">
    <div class="flex items-center justify-between">
      <h2 class="font-semibold tracking-tight">Monitored route basket</h2>
      <a href="http://localhost:5000" class="text-sm font-medium text-slate-600 hover:text-slate-900">Open dashboard</a>
    </div>
    <div class="mt-4 overflow-auto">
      <table class="w-full text-sm">
        <thead class="text-xs tracking-widest uppercase text-slate-500 border-b border-slate-200">
          <tr><th class="py-2 text-left font-semibold">Corridor</th><th class="py-2 text-left font-semibold">DGCA share</th><th class="py-2 text-left font-semibold">Base fare</th><th class="py-2 text-left font-semibold">Latest</th><th class="py-2 text-left font-semibold">Status</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr><td class="py-3 font-medium">DEL to BOM</td><td>28.5%</td><td>Rs 4,850</td><td>Rs 5,120</td><td class="text-emerald-700 font-medium">Active</td></tr>
          <tr><td class="py-3 font-medium">DEL to BLR</td><td>21.2%</td><td>Rs 5,200</td><td>Rs 5,450</td><td class="text-emerald-700 font-medium">Active</td></tr>
          <tr><td class="py-3 font-medium">BOM to BLR</td><td>18.4%</td><td>Rs 3,900</td><td>Rs 4,050</td><td class="text-emerald-700 font-medium">Active</td></tr>
          <tr><td class="py-3 font-medium">DEL to CCU</td><td>12.6%</td><td>Rs 4,600</td><td>Rs 4,780</td><td class="text-emerald-700 font-medium">Active</td></tr>
          <tr><td class="py-3 font-medium">BLR to HYD</td><td>10.8%</td><td>Rs 2,900</td><td>Rs 3,020</td><td class="text-emerald-700 font-medium">Active</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <footer class="py-8 text-center text-xs text-slate-500 border-t border-slate-200 mt-8">Ministry of Statistics and Programme Implementation • SIH 2026 SIH26056 • Faresight</footer>
</main>

<script>
const ctx=document.getElementById('indexChart');
if(ctx){
  new Chart(ctx,{
    type:'line',
    data:{labels:['Aug 01','Aug 05','Aug 10','Aug 15','Aug 20','Aug 25','Aug 30'], datasets:[{label:'Faresight', data:[100,100.72,101.45,102.18,102.9,103.62,104.24], borderColor:'#0e4a7a', backgroundColor:'rgba(14,74,122,0.08)', fill:true, tension:0.4, borderWidth:2.5, pointRadius:0}]},
    options:{responsive:true,maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{x:{grid:{display:false}, ticks:{color:'#64748b', font:{size:11}}}, y:{grid:{color:'#f1f5f9'}, ticks:{color:'#64748b', font:{size:11}}}}}
  });
}
</script>
</body>
</html>"""
