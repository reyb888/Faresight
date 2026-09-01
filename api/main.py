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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Faresight — Real-time Airfare Price Index for India</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/@phosphor-icons/web"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{--ink:#0f172a;--line:#e2e8f0;--muted:#64748b;--accent:#0e4a7a}
*{font-family:'DM Sans',system-ui,sans-serif}
.mono{font-family:'JetBrains Mono',monospace}
html{scroll-behavior:smooth}
.reveal{opacity:0;transform:translateY(14px);transition:opacity .6s cubic-bezier(.16,1,.3,1),transform .6s cubic-bezier(.16,1,.3,1)}
.reveal.in{opacity:1;transform:none}
@media(prefers-reduced-motion:reduce){.reveal{opacity:1;transform:none;transition:none}}
.heat-cell{transition:transform .15s ease;cursor:default}
.heat-cell:hover{transform:scale(1.08);z-index:2}
@keyframes countUp{from{opacity:.5;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.stat-val{animation:countUp .5s ease both}
</style>
</head>
<body class="bg-[#fcfdf8] text-slate-900 antialiased">

<nav class="sticky top-0 z-40 bg-white/90 backdrop-blur border-b border-slate-200">
  <div class="max-w-7xl mx-auto px-6 h-[64px] flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="w-9 h-9 rounded-xl bg-slate-900 text-white grid place-items-center font-bold">F</div>
      <div>
        <div class="font-semibold tracking-tight leading-none">Faresight</div>
        <div class="text-xs text-slate-500">MoSPI &middot; SIH26056</div>
      </div>
    </div>
    <div class="hidden md:flex items-center gap-2 text-sm">
      <a href="#index" class="px-3 py-1.5 rounded-full hover:bg-slate-100 text-slate-600 font-medium">Index</a>
      <a href="#routes" class="px-3 py-1.5 rounded-full hover:bg-slate-100 text-slate-600 font-medium">Routes</a>
      <a href="#heatmap" class="px-3 py-1.5 rounded-full hover:bg-slate-100 text-slate-600 font-medium">Heatmap</a>
      <a href="/docs" class="px-4 py-2 rounded-full bg-slate-900 text-white font-semibold hover:bg-slate-800 transition">API Docs</a>
    </div>
  </div>
</nav>

<main class="max-w-7xl mx-auto px-6">

<section class="grid md:grid-cols-2 gap-10 items-center pt-12 pb-10 md:pt-16 reveal">
  <div>
    <p class="text-xs font-semibold tracking-widest uppercase text-slate-500 mb-3">SIH26056 &middot; Ministry of Statistics and Programme Implementation</p>
    <h1 class="text-4xl md:text-5xl font-semibold tracking-tight leading-none">A live airfare index<br>for India</h1>
    <p class="mt-4 text-base leading-relaxed text-slate-600 max-w-[52ch]">DGCA averages arrive two months late. Faresight scrapes airlines and OTAs daily, cleans the data, and publishes a Base 100 index weighted by passenger traffic.</p>
    <div class="mt-6 flex gap-3">
      <a href="#index" class="px-5 py-3 rounded-full bg-slate-900 text-white text-sm font-semibold flex items-center gap-1.5 hover:bg-slate-800 transition">View live index <i class="ph ph-arrow-square-out text-xs"></i></a>
      <a href="/docs" class="px-5 py-3 rounded-full border border-slate-200 bg-white text-sm font-semibold hover:border-slate-300 transition">Explore API</a>
    </div>
    <div class="mt-6 flex flex-wrap gap-3 text-xs text-slate-600">
      <span class="inline-flex items-center gap-1.5"><i class="ph ph-check-circle text-emerald-600"></i> Daily scrape</span>
      <span class="inline-flex items-center gap-1.5"><i class="ph ph-check-circle text-emerald-600"></i> MAD outlier filter</span>
      <span class="inline-flex items-center gap-1.5"><i class="ph ph-check-circle text-emerald-600"></i> DGCA weighted</span>
    </div>
  </div>
  <div class="relative">
    <img src="https://picsum.photos/seed/faresight-hero-india/800/600" alt="Aerial view of India flight corridors at dusk" class="w-full h-[380px] object-cover rounded-2xl border border-slate-200">
    <div class="absolute -bottom-4 -left-4 bg-white border border-slate-200 rounded-2xl p-4 shadow-sm max-w-[260px]" id="heroCard">
      <div class="text-xs font-semibold tracking-widest uppercase text-slate-500">Faresight Daily</div>
      <div class="mono text-2xl font-semibold mt-1" id="heroIndex">&mdash;</div>
      <div class="text-xs text-emerald-700 mt-1" id="heroDelta">&mdash;</div>
    </div>
  </div>
</section>

<section id="index" class="reveal">
  <div class="grid md:grid-cols-4 gap-4 py-6 border-y border-slate-200">
    <div class="bg-white border border-slate-200 rounded-2xl p-5">
      <div class="text-xs font-semibold tracking-widest uppercase text-slate-500">Live index</div>
      <div class="mono text-2xl font-semibold mt-2 stat-val" id="statIndex">&mdash;</div>
      <div class="text-xs text-slate-500 mt-1">Base 100 &middot; Jan 6 2026</div>
    </div>
    <div class="bg-white border border-slate-200 rounded-2xl p-5">
      <div class="text-xs font-semibold tracking-widest uppercase text-slate-500">Corridors</div>
      <div class="mono text-2xl font-semibold mt-2 stat-val" id="statRoutes">&mdash;</div>
      <div class="text-xs text-slate-500 mt-1">DEL BOM BLR CCU HYD MAA</div>
    </div>
    <div class="bg-white border border-slate-200 rounded-2xl p-5">
      <div class="text-xs font-semibold tracking-widest uppercase text-slate-500">Windows</div>
      <div class="mono text-2xl font-semibold mt-2 stat-val">T+1 to T+45</div>
      <div class="text-xs text-slate-500 mt-1">Advance purchase aware</div>
    </div>
    <div class="bg-white border border-slate-200 rounded-2xl p-5">
      <div class="text-xs font-semibold tracking-widest uppercase text-slate-500">Data points</div>
      <div class="mono text-2xl font-semibold mt-2 stat-val" id="statQuotes">&mdash;</div>
      <div class="text-xs text-slate-500 mt-1">Median Absolute Deviation</div>
    </div>
  </div>
</section>

<section id="index" class="grid md:grid-cols-12 gap-6 py-8 reveal">
  <div class="md:col-span-8 bg-white border border-slate-200 rounded-2xl p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="font-semibold tracking-tight">Index trajectory</h2>
      <span class="text-xs text-slate-500" id="chartFreq">Daily &middot; Base 100</span>
    </div>
    <div class="h-[300px]"><canvas id="indexChart"></canvas></div>
  </div>
  <div class="md:col-span-4 bg-slate-900 text-white rounded-2xl p-6 relative overflow-hidden">
    <img src="https://picsum.photos/seed/faresight-method/600/400" alt="Close up of airport departure board" class="absolute inset-0 w-full h-full object-cover opacity-20">
    <div class="relative">
      <h3 class="font-semibold">How the index is built</h3>
      <p class="text-sm leading-relaxed text-slate-300 mt-2">We sample each route and window, keep the median fare, then weight by DGCA traffic.</p>
      <div class="mt-4 bg-white/10 rounded-xl p-3 mono text-xs leading-relaxed">APIX(t) = &Sigma; [ w &times; ( P(t) / P(0) ) ] &times; 100</div>
      <ul class="mt-4 text-sm leading-relaxed text-slate-300 space-y-1">
        <li><span class="text-white font-medium">w</span> DGCA passenger share for the route</li>
        <li><span class="text-white font-medium">P(t)</span> Median fare on day t</li>
        <li><span class="text-white font-medium">P(0)</span> Median fare in base week</li>
      </ul>
    </div>
  </div>
</section>

<section id="routes" class="reveal">
  <div class="bg-white border border-slate-200 rounded-2xl p-6">
    <div class="flex items-center justify-between">
      <h2 class="font-semibold tracking-tight">Monitored route basket</h2>
      <span class="text-xs text-slate-500">DGCA passenger share</span>
    </div>
    <div class="mt-4 overflow-auto">
      <table class="w-full text-sm">
        <thead class="text-xs tracking-widest uppercase text-slate-500 border-b border-slate-200">
          <tr><th class="py-2 text-left font-semibold">Corridor</th><th class="py-2 text-left font-semibold">DGCA share</th><th class="py-2 text-left font-semibold">Latest fare</th><th class="py-2 text-left font-semibold">7-day trend</th><th class="py-2 text-left font-semibold">Status</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100" id="routeBody">
          <tr><td colspan="5" class="py-4 text-center text-slate-400">Loading route data&hellip;</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</section>

<section id="heatmap" class="grid md:grid-cols-12 gap-6 py-8 reveal">
  <div class="md:col-span-12 bg-white border border-slate-200 rounded-2xl p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="font-semibold tracking-tight">Fare heatmap &mdash; route &times; advance window</h2>
      <span class="text-xs text-slate-500">Latest snapshot &middot; Median total fare</span>
    </div>
    <div class="overflow-auto">
      <div id="heatmapGrid" class="min-w-[600px]">
        <div class="text-center text-slate-400 py-8">Loading heatmap&hellip;</div>
      </div>
    </div>
  </div>
</section>

<section id="backtest" class="reveal">
  <div class="bg-white border border-slate-200 rounded-2xl p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="font-semibold tracking-tight">APIX vs DGCA published fares</h2>
      <span class="text-xs text-slate-500">Backtest comparison</span>
    </div>
    <div class="overflow-auto">
      <table class="w-full text-sm">
        <thead class="text-xs tracking-widest uppercase text-slate-500 border-b border-slate-200">
          <tr><th class="py-2 text-left font-semibold">Period</th><th class="py-2 text-left font-semibold">APIX value</th><th class="py-2 text-left font-semibold">DGCA avg fare</th><th class="py-2 text-left font-semibold">Deviation</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100" id="backtestBody">
          <tr><td colspan="4" class="py-4 text-center text-slate-400">Loading backtest data&hellip;</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</section>

</main>

<footer class="py-8 text-center text-xs text-slate-500 border-t border-slate-200 mt-8">Ministry of Statistics and Programme Implementation &middot; SIH 2026 SIH26056 &middot; Faresight</footer>

<script>
const ROUTES = ['DEL/BOM','DEL/BLR','BOM/BLR','DEL/CCU','BLR/HYD','MAA/DEL'];
const DGCA = {'DEL/BOM':28.5,'DEL/BLR':21.2,'BOM/BLR':18.4,'DEL/CCU':12.6,'BLR/HYD':10.8,'MAA/DEL':8.5};
const LABELS = {'DEL/BOM':'DEL &harr; BOM','DEL/BLR':'DEL &harr; BLR','BOM/BLR':'BOM &harr; BLR','DEL/CCU':'DEL &harr; CCU','BLR/HYD':'BLR &harr; HYD','MAA/DEL':'MAA &harr; DEL'};
const WINDOWS = [1,7,15,30,45];
const WINDOW_LABELS = {'1':'T+1','7':'T+7','15':'T+15','30':'T+30','45':'T+45'};

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) return null;
  return r.json();
}

function trendIcon(points) {
  if (!points || points.length < 2) return '<span class="text-slate-400">&mdash;</span>';
  const first = points[0].median_total_fare;
  const last = points[points.length - 1].median_total_fare;
  const diff = ((last - first) / first * 100).toFixed(1);
  if (diff > 0) return '<span class="text-rose-600">&uarr; ' + Math.abs(diff) + '%</span>';
  if (diff < 0) return '<span class="text-emerald-600">&darr; ' + Math.abs(diff) + '%</span>';
  return '<span class="text-slate-400">&mdash; flat</span>';
}

function renderRoutes() {
  const promises = ROUTES.map(async (key) => {
    const [o, d] = key.split('/');
    const data = await fetchJSON('/v1/routes/' + o + '/' + d + '?days=7');
    return { key, data };
  });
  const results = await Promise.all(promises);
  const tbody = document.getElementById('routeBody');
  tbody.innerHTML = '';
  results.forEach(({ key, data }) => {
    const latest = data && data.points && data.points.length > 0 ? data.points[data.points.length - 1].median_total_fare : null;
    const trend = trendIcon(data && data.points ? data.points : null);
    const fareHtml = latest !== null ? 'Rs ' + Math.round(latest).toLocaleString() : '<span class="text-slate-400">N/A</span>';
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="py-3 font-medium">' + LABELS[key] + '</td><td class="py-3">' + DGCA[key] + '%</td><td class="py-3 mono">' + fareHtml + '</td><td class="py-3">' + trend + '</td><td class="py-3 text-emerald-700 font-medium">Active</td>';
    tbody.appendChild(tr);
  });
}

function renderHeatmap(data) {
  const grid = document.getElementById('heatmapGrid');
  if (!data || data.length === 0) { grid.innerHTML = '<div class="text-center text-slate-400 py-8">No heatmap data</div>'; return; }
  const fares = data.map(function(d) { return d.median_total_fare; });
  const mn = Math.min.apply(null, fares);
  const mx = Math.max.apply(null, fares);
  const origins = [];
  ROUTES.forEach(function(k) { const parts = k.split('/'); const found = data.find(function(d) { return d.origin === parts[0] && d.destination === parts[1]; }); if (found && !origins.includes(parts[0] + ' &harr; ' + parts[1])) origins.push(parts[0] + ' &harr; ' + parts[1]); });
  const uniqueOrigins = [];
  const seen = {};
  data.forEach(function(d) { const label = d.origin + ' &harr; ' + d.destination; if (!seen[label]) { seen[label] = true; uniqueOrigins.push(label); } });
  function heatColor(val) {
    const t = mx === mn ? 0.5 : (val - mn) / (mx - mn);
    const r = Math.round(219 + (14 - 219) * t);
    const g = Math.round(234 + (74 - 234) * t);
    const b = Math.round(254 + (122 - 254) * t);
    return 'rgb(' + r + ',' + g + ',' + b + ')';
  }
  let html = '<div style="display:grid;grid-template-columns:140px repeat(' + WINDOWS.length + ',1fr);gap:3px;min-width:600px">';
  html += '<div></div>';
  WINDOWS.forEach(function(w) { html += '<div class="text-center text-xs font-semibold text-slate-500 py-2">' + WINDOW_LABELS[String(w)] + '</div>'; });
  uniqueOrigins.forEach(function(label) {
    html += '<div class="text-xs font-medium text-slate-600 py-2 flex items-center">' + label + '</div>';
    WINDOWS.forEach(function(w) {
      const cell = data.find(function(d) { const parts = label.split(' &harr; '); return d.origin === parts[0] && d.destination === parts[1] && d.advance_purchase_days === w; });
      if (cell) {
        const bg = heatColor(cell.median_total_fare);
        const txt = cell.median_total_fare > (mn + mx) / 2 ? 'rgba(255,255,255,.9)' : 'rgba(15,23,42,.8)';
        html += '<div class="heat-cell rounded-lg py-3 text-center text-xs font-semibold" style="background:' + bg + ';color:' + txt + '">Rs ' + Math.round(cell.median_total_fare).toLocaleString() + '</div>';
      } else {
        html += '<div class="heat-cell rounded-lg py-3 text-center text-xs" style="background:#f1f5f9;color:#cbd5e1">&mdash;</div>';
      }
    });
  });
  html += '</div>';
  grid.innerHTML = html;
}

function renderBacktest(data) {
  const tbody = document.getElementById('backtestBody');
  if (!data || data.length === 0) { tbody.innerHTML = '<tr><td colspan="4" class="py-4 text-center text-slate-400">No backtest data</td></tr>'; return; }
  tbody.innerHTML = '';
  data.forEach(function(row) {
    const dev = row.pct_deviation;
    const devColor = dev > 0 ? 'text-rose-600' : dev < 0 ? 'text-emerald-600' : 'text-slate-500';
    const devSign = dev > 0 ? '+' : '';
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="py-3 mono">' + row.period + '</td><td class="py-3 mono">' + row.apix_value.toFixed(2) + '</td><td class="py-3 mono">Rs ' + Math.round(row.dgca_avg_fare).toLocaleString() + '</td><td class="py-3 mono ' + devColor + '">' + devSign + dev.toFixed(1) + '%</td>';
    tbody.appendChild(tr);
  });
}

function renderIndex(data) {
  if (!data || data.length === 0) return;
  const latest = data[data.length - 1];
  const first = data[0];
  const delta = latest.index_value - first.index_value;
  const deltaPct = ((delta / first.index_value) * 100).toFixed(2);
  const deltaColor = delta >= 0 ? 'text-emerald-700' : 'text-rose-600';
  const deltaSign = delta >= 0 ? '+' : '';
  document.getElementById('heroIndex').innerHTML = latest.index_value.toFixed(2) + ' <span class="text-sm text-slate-500 font-normal">/ 100</span>';
  document.getElementById('heroDelta').innerHTML = '<span class="' + deltaColor + '">' + deltaSign + deltaPct + '%</span> vs base week Jan 6 2026';
  document.getElementById('statIndex').textContent = latest.index_value.toFixed(2);
  document.getElementById('statRoutes').textContent = latest.route_count || ROUTES.length;
  document.getElementById('statQuotes').textContent = latest.quote_count != null ? latest.quote_count.toLocaleString() : '&mdash;';
  if (window.indexChartInstance) window.indexChartInstance.destroy();
  const ctx = document.getElementById('indexChart');
  if (!ctx) return;
  window.indexChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(function(d) { return d.index_date; }),
      datasets: [{
        label: 'APIX',
        data: data.map(function(d) { return d.index_value; }),
        borderColor: '#0e4a7a',
        backgroundColor: 'rgba(14,74,122,0.08)',
        fill: true,
        tension: 0.4,
        borderWidth: 2.5,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: '#0e4a7a'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#64748b', font: { size: 11 } } },
        y: { grid: { color: '#f1f5f9' }, ticks: { color: '#64748b', font: { size: 11 } } }
      }
    }
  });
}

async function init() {
  const [indexData, heatData, btData] = await Promise.all([
    fetchJSON('/v1/index?frequency=daily'),
    fetchJSON('/v1/heatmap'),
    fetchJSON('/v1/backtest')
  ]);
  renderIndex(indexData);
  renderRoutes();
  renderHeatmap(heatData);
  renderBacktest(btData);
}

init();
</script>
</body>
</html>"""