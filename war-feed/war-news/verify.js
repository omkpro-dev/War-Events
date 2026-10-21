// Turns stored claims into map marks: confirmed / claimed / contested.
// Rule: a change is CONFIRMED when 2+ independent strong outlets report it in
// their own voice within 72 h and no strong outlet contradicts it. Anything
// less is CLAIMED; any credible contradiction makes it CONTESTED.
import { PLACES } from './places.js';
import { CONFLICTS } from './sources.js';

const WINDOW_MS = 72 * 3600e3;
const KEEP_CONFIRMED_MS = 14 * 864e5;

// Strong outlets. A story credited to a wire (Reuters/AP/AFP) counts as that wire.
export const STRONG = [
  ['reuters', /reuters/i], ['ap', /associated press|apnews|^ap( news)?$/i], ['afp', /\bafp\b|agence france/i],
  ['bbc', /\bbbc\b/i], ['guardian', /guardian/i], ['nyt', /new york times|nytimes/i], ['wapo', /washington post/i],
  ['ft', /financial times|^ft\b/i], ['wsj', /wall street journal|\bwsj\b/i], ['bloomberg', /bloomberg/i],
  ['economist', /economist/i], ['dw', /\bdw\b|deutsche welle/i], ['france24', /france ?24/i],
  ['aljazeera', /al ?jazeera/i], ['mee', /middle east eye/i], ['kyivindependent', /kyiv independent/i],
  ['cnn', /\bcnn\b/i], ['npr', /\bnpr\b/i],
];
// Outlets close to one side: they count only together with an outlet that isn't.
const ALIGNED = { ukraine: ['kyivindependent'] };

const norm = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[’'\u02bc]/g, "'").replace(/\s+/g, ' ').trim();
const ALIAS = new Map();
for (const p of PLACES) for (const a of [p.name, ...p.aliases]) ALIAS.set(p.conflict + '|' + norm(a), p);

function findPlace(c) {
  return ALIAS.get(c.conflict + '|' + norm(c.place)) || (c.adminHint && ALIAS.get(c.conflict + '|' + norm(c.adminHint))) || null;
}
export function sourceKey(c) {
  if (c.wire) { const w = norm(c.wire); return w.includes('reuters') ? 'reuters' : w.includes('afp') ? 'afp' : 'ap'; }
  const hit = STRONG.find(([, re]) => re.test(c.outlet || ''));
  return hit ? hit[0] : null;
}

export function buildControl(allClaims, now = Date.now()) {
  const claims = allClaims.filter((c) => c.place && c.status !== 'none' && c.status !== 'rejected' && c.kind !== 'advance');
  const byPlace = new Map();
  const unmatched = [];
  for (const c of claims) {
    const p = findPlace(c);
    if (!p) { unmatched.push(c.place); continue; }
    const k = p.conflict + '|' + p.name;
    if (!byPlace.has(k)) byPlace.set(k, { p, list: [] });
    byPlace.get(k).list.push(c);
  }
  const marks = [];
  for (const { p, list } of byPlace.values()) {
    list.sort((a, b) => Date.parse(a.publishedAt) - Date.parse(b.publishedAt));
    const latest = list.filter((c) => c.kind === 'capture' || c.kind === 'withdrawal').pop();
    if (!latest) continue;
    // gainer of the most recent change (a withdrawal hands the place to the other side if named)
    const gainer = latest.kind === 'capture' ? latest.gainer : (latest.gainer || null);
    const t0 = Date.parse(latest.publishedAt);
    const recent = list.filter((c) => Math.abs(Date.parse(c.publishedAt) - t0) <= WINDOW_MS);
    const support = recent.filter((c) => (c.kind === 'capture' || c.kind === 'withdrawal') && (c.gainer || null) === gainer);
    const against = recent.filter((c) => c.kind === 'denial' || c.kind === 'contested' || ((c.kind === 'capture') && c.gainer && c.gainer !== gainer));
    const strongReported = new Set(support.filter((c) => c.voice === 'reported').map(sourceKey).filter(Boolean));
    const aligned = ALIGNED[p.conflict] || [];
    const independentCount = [...strongReported].filter((k) => !aligned.includes(k)).length;
    const confirmed = independentCount >= 1 && strongReported.size >= 2;
    const strongAgainst = against.some((c) => sourceKey(c) && (c.voice === 'reported' || c.kind === 'denial'));
    let status = strongAgainst ? 'contested' : confirmed ? 'confirmed' : (against.length ? 'contested' : 'claimed');
    const age = now - t0;
    if (status === 'confirmed' ? age > KEEP_CONFIRMED_MS : age > WINDOW_MS) continue;   // fade out
    const conf = CONFLICTS.find((c) => c.id === p.conflict);
    const actor = conf && conf.actors.find((a) => a.id === gainer);
    const seen = new Set();
    marks.push({
      id: p.conflict + ':' + norm(p.name), conflict: p.conflict, conflictName: conf ? conf.name : p.conflict,
      place: p.name, lat: p.lat, lng: p.lng, status, gainer, gainerName: actor ? actor.name : null,
      colour: actor ? actor.colour : '#d8463c', since: latest.publishedAt, strongSources: strongReported.size,
      sources: recent.filter((c) => c.url && !seen.has(c.url) && seen.add(c.url)).slice(-8).reverse().map((c) => ({
        outlet: c.wire ? c.wire + ' via ' + c.outlet : c.outlet, url: c.url, title: c.title, publishedAt: c.publishedAt, kind: c.kind, voice: c.voice,
      })),
    });
  }
  marks.sort((a, b) => Date.parse(b.since) - Date.parse(a.since));
  return { updated: new Date(now).toISOString(), rule: '2+ independent strong outlets, own reporting, 72 h, no strong contradiction', marks, unmatched: [...new Set(unmatched)].slice(0, 50) };
}
