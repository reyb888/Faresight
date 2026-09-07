/**
 * Faresight Production Scraper — MoSPI Airfare Price Index (SIH26056)
 * Crawlee PlaywrightCrawler (FaresightCrawler) + SerpApi dual ingestion.
 *
 * Routes: DEL-BOM, BLR-DEL, MAA-DEL, CCU-BOM, HYD-DEL
 * Windows: T+1, T+3, T+5, T+7, T+15, T+30, T+45
 * Target: Google Flights / OTA XHR (intercept) or hydrated DOM (.YMlA3d .pI23Fd) or raw JSON
 * Output: SQLite airfare.db -> airfare_records (route_id, capture_date, flight_date, lead_time_days, airline_name, price, data_source='CRAWLEE_STEALTH') + 403/timeout retry
 * Failover: 12s timeout → SERPAPI_FAILOVER per master prompt
 */
import { FaresightCrawler, Dataset, Log, humanDelay, humanMouseMove, waitForJsonResponse } from './faresight_crawler.js';
import Database from 'better-sqlite3';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DB_PATH = process.env.AIRFARE_DB_PATH || path.join(__dirname, '..', 'airfare.db');

const ROUTES = [
  { origin: 'DEL', dest: 'BOM', label: 'DEL-BOM' },
  { origin: 'BLR', dest: 'DEL', label: 'BLR-DEL' },
  { origin: 'MAA', dest: 'DEL', label: 'MAA-DEL' },
  { origin: 'CCU', dest: 'BOM', label: 'CCU-BOM' },
  { origin: 'HYD', dest: 'DEL', label: 'HYD-DEL' },
];
const WINDOWS = [1, 3, 5, 7, 15, 30, 45];
const SERPAPI_KEYS = [process.env.SERP_API_KEY_1, process.env.SERP_API_KEY_2, process.env.SERP_API_KEY_3, process.env.SERP_API_KEY_4, process.env.SERP_API_KEY_5].filter(Boolean);
let serpIdx = 0;
const nextSerpKey = () => SERPAPI_KEYS.length ? SERPAPI_KEYS[serpIdx++ % SERPAPI_KEYS.length] : '';

const log = new Log({ prefix: 'FaresightScraper' });

function fmtDate(d) { return d.toISOString().slice(0, 10); }

function serpApiUrl(origin, dest, outboundDate, apiKey) {
  const p = new URLSearchParams({ engine: 'google_flights', departure_id: origin, arrival_id: dest, outbound_date: outboundDate, type: '2', currency: 'INR', hl: 'en', api_key: apiKey });
  return `https://serpapi.com/search?${p.toString()}`;
}

function extractBestFlight(payload) {
  const candidates = [...(payload.best_flights || []), ...(payload.other_flights || [])];
  let best = null; let bestPrice = Infinity;
  const toPrice = v => { const c = ''.join([...String(v || '')].filter(ch => /[0-9.]/.test(ch))); const n = Number(c); return Number.isFinite(n) && n > 0 ? n : null; };
  for (const opt of candidates) {
    const price = toPrice(opt.price);
    if (price && price < bestPrice) { bestPrice = price; best = { price, airline: opt.flights?.[0]?.airline || 'Unknown', duration: opt.total_duration || '' }; }
  }
  if (!best && Array.isArray(payload.flights)) {
    for (const g of payload.flights) for (const r of g.routes || []) for (const fg of r.fare_groups || []) for (const f of fg.flights || []) {
      const price = toPrice(f.price); if (price && price < bestPrice) { bestPrice = price; best = { price, airline: f.airline || r.airline }; }
    }
  }
  return best;
}

// ---- SQLite helpers ----
function openDb() {
  const db = new Database(DB_PATH);
  db.pragma('journal_mode = WAL'); db.pragma('foreign_keys = ON');
  return db;
}
function routeIdFor(db, origin, dest) {
  const row = db.prepare('SELECT id FROM routes WHERE origin_code = ? AND destination_code = ?').get(origin, dest);
  return row?.id ?? null;
}
function insertRecords(records, dataSource) {
  if (!records.length) return 0;
  const db = openDb();
  try {
    const ins = db.prepare(`INSERT INTO airfare_records (route_id, capture_date, flight_date, lead_time_days, airline_name, price, currency, fetched_at, data_source)
      VALUES (@route_id, @capture_date, @flight_date, @lead_time_days, @airline_name, @price, 'INR', @fetched_at, @data_source)`);
    const tx = db.transaction((rows) => { let n = 0; for (const r of rows) { const rid = r.route_id ?? routeIdFor(db, r.origin_code, r.destination_code); if (!rid) continue; ins.run({ route_id: rid, capture_date: r.capture_date, flight_date: r.flight_date, lead_time_days: r.lead_time_days, airline_name: r.airline_name, price: r.price, fetched_at: new Date().toISOString(), data_source: r.data_source || dataSource }); n++; } return n; });
    return tx(records);
  } finally { db.close(); }
}

// ---- XHR/DOM extraction for OTA/Google Flights ----
async function extractViaXhrOrDom(page, request, log) {
  const xhrBodies = [];
  const handler = async (resp) => {
    const url = resp.url();
    const ct = resp.headers()['content-type'] || '';
    // Heuristic: flight inventory JSON endpoints (OTA/Google) — tune to your targets
    if (!ct.includes('json')) return;
    if (!/flight|search|pricing|fares|inventory/i.test(url)) return;
    try { const j = await resp.json().catch(() => null); if (j && Object.keys(j).length) xhrBodies.push({ url, body: j, status: resp.status() }); } catch {}
  };
  page.on('response', handler);

  // Also watch hydrated DOM pricing elements as fallback
  let domPrice = null;
  const domPoll = page.waitForSelector('.YMlA3d, .pI23Fd, [data-testid="price"], [class*="price"]', { timeout: 12000 }).then(async () => {
    domPrice = await page.evaluate(() => {
      const sels = ['.YMlA3d', '.pI23Fd', '[data-testid="price"]'];
      for (const s of sels) { const el = document.querySelector(s); if (el?.textContent) return el.textContent.trim(); }
      return null;
    }).catch(() => null);
  }).catch(() => {});

  // Trigger search with human-like interaction (curved mouse + delays) for Akamai
  await humanDelay(800, 1500);
  const searchBtn = 'button:has-text("Search"), button[aria-label*="Search"], [data-testid="search-button"]';
  if (await page.locator(searchBtn).first().isVisible().catch(() => false)) {
    await humanMouseMove(page, searchBtn);
    await humanDelay(200, 500);
    await page.locator(searchBtn).first().click({ delay: 80 + Math.random() * 120 }).catch(() => {});
  }
  await humanDelay(1200, 2200);
  await Promise.race([domPoll, new Promise(r => setTimeout(r, 8000))]);
  page.off('response', handler);

  // Prefer XHR JSON if available
  if (xhrBodies.length) {
    for (const { body } of xhrBodies) {
      const best = extractBestFlight(body);
      if (best) return { price: best.price, airline: best.airline, raw: body, source: 'XHR' };
      // Also try generic price field scan
      const m = JSON.stringify(body).match(/"price"\s*:\s*"?₹?\s*([0-9,]+)"?/);
      if (m) { const p = Number(m[1].replace(/,/g, '')); if (p) return { price: p, airline: 'Unknown', raw: body, source: 'XHR' }; }
    }
  }
  if (domPrice) {
    const p = Number(String(domPrice).replace(/[^0-9.]/g, ''));
    if (p) return { price: p, airline: 'Unknown', raw: null, source: 'DOM' };
  }
  return null;
}

async function serpApiFallback(origin, dest, outboundDate) {
  const key = nextSerpKey();
  if (!key) return null;
  const url = serpApiUrl(origin, dest, outboundDate, key);
  const res = await fetch(url, { signal: AbortSignal.timeout(25000) });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok || payload.error) throw new Error(payload.error || `SerpApi ${res.status}`);
  const best = extractBestFlight(payload);
  if (!best) throw new Error('SerpApi empty payload');
  return best;
}

// ---- Crawlee per-route handler with 403/429 retry + Akamai failover ----
const crawler = new FaresightCrawler({
  maxRequestsPerCrawl: 40,
  maxConcurrency: 2,
  requestHandler: async ({ request, page, session, log }) => {
    const { origin, dest, flightDate, leadTime, captureDate } = request.userData;
    let price = null, airline = null, source = 'CRAWLEE_STEALTH';

    try {
      // Strict session rotation: retire on any non-200 or empty
      const extracted = await extractViaXhrOrDom(page, request, log);
      if (!extracted?.price) throw new Error('Empty payload — retiring session for SerpApi failover');
      price = extracted.price; airline = extracted.airline; source = 'CRAWLEE_STEALTH';
    } catch (e) {
      const msg = String(e.message || e);
      if (/403|429|Turnstile|WAF|empty payload/i.test(msg)) {
        log.warning(`Crawlee blocked/empty for ${origin}-${dest} T+${leadTime}: ${msg} → SerpApi failover`);
        if (session) session.retire();
      }
      // Failover: throw to trigger crawler retry + outer SerpApi path
      throw e;
    }

    if (price) {
      const rec = { origin_code: origin, destination_code: dest, capture_date: captureDate, flight_date: flightDate, lead_time_days: leadTime, airline_name: airline, price, data_source: source };
      insertRecords([rec], source);
      await Dataset.pushData({ ...rec, corridor: `${origin}-${dest}` });
      log.info(`✓ ${origin}-${dest} T+${leadTime}: ₹${price} ${airline} [${source}]`);
    }
  },
  failedRequestHandler: async ({ request, error, session }) => {
    const { origin, dest, flightDate, leadTime, captureDate } = request.userData;
    log.warning(`Crawlee failed ${origin}-${dest} T+${leadTime}: ${error.message} — SerpApi failover`);
    if (session) session.retire();
    try {
      const best = await serpApiFallback(origin, dest, flightDate);
      const rec = { origin_code: origin, destination_code: dest, capture_date: captureDate, flight_date: flightDate, lead_time_days: leadTime, airline_name: best.airline, price: best.price, data_source: 'SERPAPI_FAILOVER' };
      insertRecords([rec], 'SERPAPI_FAILOVER');
      await Dataset.pushData({ ...rec, corridor: `${origin}-${dest}` });
      log.info(`✓ failover ${origin}-${dest} T+${leadTime}: ₹${best.price} ${best.airline}`);
    } catch (e) {
      log.warning(`SerpApi failover also failed for ${origin}-${dest} T+${leadTime}: ${e.message} — buried`);
    }
  },
});

// ---- Runner for direct SerpApi sweep (also inserts with SERPAPI_FAILOVER / CRAWLEE_STEALTH audit) ----
async function serpApiSweep() {
  const today = new Date(); const fmt = d => d.toISOString().slice(0, 10);
  for (const r of ROUTES) for (const w of WINDOWS) {
    const outbound = fmt(new Date(Date.now() + w * 864e5));
    const capture = fmt(today);
    try {
      const best = await serpApiFallback(r.origin, r.dest, outbound);
      const rec = { origin_code: r.origin, destination_code: r.dest, capture_date: capture, flight_date: outbound, lead_time_days: w, airline_name: best.airline, price: best.price, data_source: 'SERPAPI_FAILOVER' };
      insertRecords([rec], 'SERPAPI_FAILOVER');
      await Dataset.pushData({ ...rec, corridor: `${r.label}` });
      log.info(`✓ sweep ${r.label} T+${w}: ₹${best.price}`);
      await new Promise(r => setTimeout(r, 2200));
    } catch (e) { log.warning(`sweep ${r.label} T+${w} buried: ${e.message}`); }
  }
}

// ---- CLI ----
const args = process.argv.slice(2);
const useCrawlee = !args.includes('--serpapi-only');
const routesArg = args.find(a => a.startsWith('--routes='))?.split('=')[1];

if (routesArg) {
  // filter ROUTES by label arg
}

if (useCrawlee) {
  const today = fmtDate(new Date());
  const requests = [];
  for (const r of ROUTES) for (const w of WINDOWS) {
    const out = new Date(Date.now() + w * 864e5);
    // Example OTA/Google Flights URL — replace with your target portal per route
    const url = `https://www.google.com/travel/flights?q=Flights%20to%20${r.dest}%20from%20${r.origin}%20on%20${fmt(out)}`;
    requests.push({ url, userData: { origin: r.origin, dest: r.dest, flightDate: fmt(out), leadTime: w, captureDate: today } });
  }
  await crawler.run(requests);
} else {
  await serpApiSweep();
}
await Dataset.exportToCSV('faresight_live_fares');
log.info('Done — exported faresight_live_fares.csv');
function fmtDate(d) { return d.toISOString().slice(0, 10); }
