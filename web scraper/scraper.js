/**
 * Faresight Live Scraper — uses FaresightCrawler (Crawlee fork) + SerpApi
 * Each route/window is isolated: errors are buried, pipeline never stops.
 * 5 routes × 7 windows = 35 SerpApi calls, round-robin over 5 keys.
 */
import { FaresightCrawler, Dataset, Log } from './faresight_crawler.js';

const ROUTES = [
  { origin: 'DEL', dest: 'BOM', label: 'DEL → BOM' },
  { origin: 'BLR', dest: 'DEL', label: 'BLR → DEL' },
  { origin: 'MAA', dest: 'DEL', label: 'MAA → DEL' },
  { origin: 'CCU', dest: 'BOM', label: 'CCU → BOM' },
  { origin: 'HYD', dest: 'DEL', label: 'HYD → DEL' },
];
const WINDOWS = [1, 3, 5, 7, 15, 30, 45];
const API_KEYS = [
  process.env.SERP_API_KEY_1,
  process.env.SERP_API_KEY_2,
  process.env.SERP_API_KEY_3,
  process.env.SERP_API_KEY_4,
  process.env.SERP_API_KEY_5,
].filter(Boolean);

let keyIdx = 0;
function nextKey() {
  if (!API_KEYS.length) return '';
  const k = API_KEYS[keyIdx % API_KEYS.length];
  keyIdx = (keyIdx + 1) % API_KEYS.length;
  return k;
}

function serpApiUrl(origin, dest, outboundDate, apiKey) {
  const p = new URLSearchParams({
    engine: 'google_flights',
    departure_id: origin,
    arrival_id: dest,
    outbound_date: outboundDate,
    type: '2',
    currency: 'INR',
    hl: 'en',
    api_key: apiKey,
  });
  return `https://serpapi.com/search?${p.toString()}`;
}

function extractBestFlight(payload) {
  const candidates = [
    ...(payload.best_flights || []),
    ...(payload.other_flights || []),
  ];
  let best = null;
  let bestPrice = Infinity;
  for (const opt of candidates) {
    const price = Number(String(opt.price || '').replace(/[^0-9.]/g, ''));
    if (price && price < bestPrice) {
      bestPrice = price;
      const seg = opt.flights?.[0] || {};
      best = {
        price: price,
        airline: seg.airline || 'Unknown',
        duration: opt.total_duration || seg.duration || '',
        stops: opt.layovers?.length || 0,
      };
    }
  }
  // legacy nested shape fallback
  if (!best && Array.isArray(payload.flights)) {
    for (const g of payload.flights) {
      for (const r of g.routes || []) {
        for (const fg of r.fare_groups || []) {
          for (const f of fg.flights || []) {
            const price = Number(String(f.price || '').replace(/[^0-9.]/g, ''));
            if (price && price < bestPrice) { bestPrice = price; best = { price, airline: f.airline || r.airline, duration: f.duration }; }
          }
        }
      }
    }
  }
  return best;
}

const crawler = new FaresightCrawler({
  maxRequestsPerCrawl: 35,
  maxConcurrency: 2,
  requestHandler: async ({ request, page, log }) => {
    // This handler is for direct site Crawlee (MakeMyTrip/ixigo) — SerpApi is done via plain fetch below
    log.info(`Crawlee page: ${request.url}`);
  },
});

async function serpApiRoundRobin() {
  const log = new Log({ prefix: 'FaresightSerpApi' });
  const today = new Date();
  const fmt = (d) => d.toISOString().slice(0, 10);

  for (const r of ROUTES) {
    for (const w of WINDOWS) {
      const outDate = new Date(Date.now() + w * 864e5);
      const outbound = fmt(outDate);
      const capture = fmt(today);
      const flightDate = outbound;
      const url = serpApiUrl(r.origin, r.dest, outbound, nextKey());
      try {
        const res = await fetch(url, { signal: AbortSignal.timeout(25000) });
        const payload = await res.json();
        if (!res.ok || payload.error) {
          log.warning(`SerpApi ${r.label} T+${w}: ${res.status} ${payload.error || res.statusText} — buried`);
          continue;
        }
        const best = extractBestFlight(payload);
        if (!best) { log.warning(`SerpApi ${r.label} T+${w}: no price — buried`); continue; }
        const record = {
          origin_code: r.origin,
          destination_code: r.dest,
          capture_date: capture,
          flight_date: flightDate,
          lead_time_days: w,
          airline_name: best.airline,
          price: best.price,
          currency: 'INR',
          data_source: 'SERPAPI',
        };
        await Dataset.pushData(record);
        log.info(`✓ ${r.label} T+${w}: ₹${best.price} ${best.airline} — stored`);

        // also POST to backend so Vercel SQLite and Supabase both get it (best-effort, buried on failure)
        try {
          await fetch(`${process.env.FARESIGHT_API_URL || 'https://faresight-sih.vercel.app'}/api/v1/ingest`, {
            method: 'POST',
            headers: { 'content-type': 'application/json', 'x-api-key': process.env.FARESIGHT_API_KEY || '' },
            body: JSON.stringify(record),
          });
        } catch {}

        await new Promise(r => setTimeout(r, 2100)); // polite delay
      } catch (e) {
        log.warning(`SerpApi ${r.label} T+${w} exception buried: ${e.message}`);
      }
    }
  }
  const { itemsCount } = await Dataset.getInfo();
  log.info(`SerpApi run complete — ${itemsCount} records in Dataset`);
  await Dataset.exportToCSV('faresight_live_fares');
  log.info('Exported faresight_live_fares.csv');
}

serpApiRoundRobin().catch(e => { console.error('Faresight scraper fatal (buried):', e); process.exit(0); });
