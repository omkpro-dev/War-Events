// War news collector: pulls every source, keeps armed-conflict stories,
// tags conflict, incident type and place, flags possible control changes,
// and (if enabled) sends those to the AI claim extractor.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { fetchFeed, fetchGdelt, pool } from '../shared/rss.js';
import { NewsStore } from '../shared/store.js';
import { WAR_FEEDS, WAR_GDELT_QUERIES, WAR_CONTEXT, CONFLICTS, INCIDENT_TYPES, CAPTURE_RE } from './sources.js';
import { PLACES } from './places.js';
import { extractClaims, claimsEnabled } from './claims.js';

const here = path.dirname(fileURLToPath(import.meta.url));
export const warStore = new NewsStore({
  file: process.env.WAR_STORE_FILE ?? path.join(here, '..', 'data', 'war.json'),
  maxItems: 3000,
  maxAgeHours: 72,
});

// Whole-word matcher for a list of phrases (so "war" doesn't match "warning").
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const wordRe = (words) => new RegExp(`(?:^|[^\\p{L}\\p{N}])(${words.map((w) => esc(w.trim())).join('|')})(?:s|es)?(?=$|[^\\p{L}\\p{N}])`, 'iu'); // plurals too

const CONTEXT_RE = wordRe(WAR_CONTEXT);
const CONFLICT_RES = CONFLICTS.map((c) => ({ c, re: wordRe(c.keywords) }));
const TYPE_RES = INCIDENT_TYPES.map((t) => ({ t, re: wordRe(t.words) }));
const PLACE_RES = PLACES.map((p) => ({ p, re: wordRe(p.aliases) }));

export function classifyWar(item, feed) {
  const title = item.title;
  const body = `${item.title} ${item.summary}`;
  if (!CONTEXT_RE.test(body)) return null;

  // Conflict: the feed's own conflict if it has one, else the first that matches.
  const inText = CONFLICT_RES.find(({ re }) => re.test(title)) ?? CONFLICT_RES.find(({ re }) => re.test(body));
  const fromFeed = feed?.conflict ? CONFLICT_RES.find(({ c }) => c.id === feed.conflict) : null;
  const conflict = inText ?? fromFeed;
  if (!conflict) return null;
  const conf = conflict.c;

  const type = (TYPE_RES.find(({ re }) => re.test(title)) ?? TYPE_RES.find(({ re }) => re.test(body)))?.t.id ?? 'other';

  // Place: prefer one named in the title, and one belonging to this conflict.
  const local = PLACE_RES.filter(({ p }) => p.conflict === conf.id);
  const hit = local.find(({ re }) => re.test(title)) ?? local.find(({ re }) => re.test(body));
  const place = hit
    ? { name: hit.p.name, lat: hit.p.lat, lng: hit.p.lng, precision: hit.p.kind }
    : { name: conf.name, lat: conf.center[0], lng: conf.center[1], precision: 'country' };

  return {
    ...item,
    conflict: conf.id,
    type,
    place,
    possibleControlChange: CAPTURE_RE.test(body),
  };
}

let running = false;

/** One collection run. Safe to call on a timer. */
export async function collectWar({ useGdelt = process.env.WAR_USE_GDELT !== '0' } = {}) {
  if (running) return { stats: { skipped: 'previous run still going' } };
  running = true;
  const started = Date.now();
  try {
    const rss = await pool(WAR_FEEDS, 6, async (feed) => {
      const { items, error } = await fetchFeed(feed);
      warStore.feedHealth[feed.id] = { name: feed.name, ok: !error, error, count: items.length, at: new Date().toISOString() };
      return items.map((i) => classifyWar(i, feed)).filter(Boolean);
    });

    const gdelt = [];
    if (useGdelt) {
      for (const g of WAR_GDELT_QUERIES) { // sequential: GDELT rate limit
        const { items, error } = await fetchGdelt(g.q, { timespan: '3h', id: g.id });
        warStore.feedHealth[g.id] = { name: 'GDELT', ok: !error, error, count: items.length, at: new Date().toISOString() };
        gdelt.push(...items.map((i) => classifyWar(i, { conflict: g.conflict })).filter(Boolean));
      }
    }

    const all = rss.flat().concat(gdelt);
    const before = new Set(warStore.items.map((i) => i.id));
    const added = warStore.add(all);
    warStore.lastRun = new Date().toISOString();

    // Only brand-new stories that look like a control change go to the AI.
    let claimsFound = 0;
    if (claimsEnabled()) {
      const fresh = warStore.items.filter((i) => !before.has(i.id) && i.possibleControlChange);
      claimsFound = await extractClaims(fresh);
    }

    return { stats: { fetched: all.length, added, total: warStore.items.length, claimsFound, ms: Date.now() - started } };
  } finally {
    running = false;
  }
}
