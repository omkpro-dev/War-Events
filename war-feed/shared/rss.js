// Fetches and parses RSS 2.0, Atom and RSS 1.0 (RDF) feeds into one item shape.
import { XMLParser } from 'fast-xml-parser';
import crypto from 'node:crypto';

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: '@',
  textNodeName: '#text',
  removeNSPrefix: true, // dc:date -> date, media:content -> content
  processEntities: false, // some feeds exceed the entity limit; decoded in stripHtml
});

const UA = 'Mozilla/5.0 (compatible; NewsFeedBot/1.0; +https://yoursite.example/about)';

const text = (v) => {
  if (v == null) return '';
  if (typeof v === 'string' || typeof v === 'number') return String(v);
  if (Array.isArray(v)) return text(v[0]);
  return v['#text'] ?? v['@href'] ?? '';
};

export const stripHtml = (s = '') =>
  s.replace(/<!\[CDATA\[|\]\]>/g, '')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>') // escaped HTML inside descriptions
    .replace(/<[^>]*>/g, ' ')
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/\s+/g, ' ').trim();

const toArray = (v) => (v == null ? [] : Array.isArray(v) ? v : [v]);

function linkOf(entry) {
  const links = toArray(entry.link);
  const alt = links.find((l) => typeof l === 'object' && (l['@rel'] ?? 'alternate') === 'alternate');
  return text(alt ?? links[0]) || text(entry.guid);
}

function imageOf(entry) {
  const media = toArray(entry.content).concat(toArray(entry.thumbnail), toArray(entry.enclosure));
  const m = media.find((x) => x && x['@url'] && !/audio|video/.test(x['@type'] ?? ''));
  return m ? m['@url'] : null;
}

export const hashId = (s) => crypto.createHash('sha1').update(s).digest('hex').slice(0, 16);

// Strip tracking params so the same story from two feeds dedupes.
export function canonicalUrl(u) {
  u = String(u ?? '').trim().replace(/&amp;/g, '&');
  try {
    const url = new URL(u);
    for (const k of [...url.searchParams.keys()]) {
      if (/^(utm_|ref|cmpid|ito|mod|guccounter)/i.test(k)) url.searchParams.delete(k);
    }
    url.hash = '';
    return url.toString();
  } catch {
    return u;
  }
}

/**
 * Fetch one feed. Returns { items, error }. Never throws, so one dead feed
 * doesn't stop the run.
 * @param {{id:string,name:string,url:string,category?:string,outlet?:string}} feed
 */
export async function fetchFeed(feed, { timeoutMs = 15000 } = {}) {
  try {
    const res = await fetch(feed.url, {
      headers: { 'User-Agent': UA, Accept: 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*' },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) return { items: [], error: `HTTP ${res.status}` };
    const xml = await res.text();
    const doc = parser.parse(xml);

    const channel = doc.rss?.channel ?? doc.RDF?.channel ?? null;
    const entries = toArray(doc.rss?.channel?.item ?? doc.RDF?.item ?? doc.feed?.entry);
    if (!entries.length && !channel && !doc.feed) return { items: [], error: 'not a feed' };

    const items = entries.map((e) => {
      const url = canonicalUrl(linkOf(e));
      const title = stripHtml(text(e.title));
      const summary = stripHtml(text(e.description ?? e.summary ?? e.encoded ?? e.content)).slice(0, 400);
      const date = text(e.pubDate ?? e.published ?? e.updated ?? e.date);
      const ts = Date.parse(date);
      // Google News titles end in " - Outlet Name"; keep the real outlet.
      let outlet = feed.outlet ?? feed.name;
      let cleanTitle = title;
      const src = e.source && stripHtml(text(e.source));
      if (src) {
        outlet = src;
        cleanTitle = title.replace(new RegExp(`\\s+-\\s+${src.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`), '');
      }
      return {
        id: hashId(url || title),
        url,
        title: cleanTitle,
        summary: summary.startsWith(cleanTitle) ? '' : summary, // Google News repeats the title
        outlet,
        feedId: feed.id,
        category: feed.category ?? null,
        image: imageOf(e),
        publishedAt: Number.isFinite(ts) ? new Date(ts).toISOString() : new Date().toISOString(),
      };
    }).filter((i) => i.url && i.title);

    return { items, error: null };
  } catch (err) {
    return { items: [], error: err.name === 'TimeoutError' ? 'timeout' : err.message };
  }
}

/** Run async jobs with a concurrency limit. */
export async function pool(list, limit, fn) {
  const out = new Array(list.length);
  let i = 0;
  const workers = Array.from({ length: Math.min(limit, list.length) }, async () => {
    while (i < list.length) {
      const idx = i++;
      out[idx] = await fn(list[idx], idx);
    }
  });
  await Promise.all(workers);
  return out;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// GDELT allows one request every 5 seconds, so queries are spaced out.
let lastGdelt = 0;
/**
 * Search GDELT's DOC 2.0 API (free, no key). Returns items in the same shape.
 * @param {string} query e.g. '(captured OR seized) (Yemen OR Houthi)'
 */
export async function fetchGdelt(query, { timespan = '1h', max = 75, category = null, id = 'gdelt' } = {}) {
  const wait = lastGdelt + 6000 - Date.now();
  if (wait > 0) await sleep(wait);
  lastGdelt = Date.now();
  const url = `https://api.gdeltproject.org/api/v2/doc/doc?query=${encodeURIComponent(query + ' sourcelang:english')}` +
    `&mode=ArtList&format=json&maxrecords=${max}&timespan=${timespan}&sort=DateDesc`;
  try {
    const res = await fetch(url, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(20000) });
    const body = await res.text();
    if (!res.ok || !body.startsWith('{')) return { items: [], error: `GDELT ${res.status}: ${body.slice(0, 80)}` };
    const data = JSON.parse(body);
    const items = (data.articles ?? []).map((a) => {
      // seendate looks like 20261016T141500Z
      const d = a.seendate?.replace(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/, '$1-$2-$3T$4:$5:$6Z');
      const u = canonicalUrl(a.url);
      return {
        id: hashId(u),
        url: u,
        title: stripHtml(a.title),
        summary: '',
        outlet: a.domain,
        feedId: id,
        category,
        image: a.socialimage || null,
        publishedAt: d && !Number.isNaN(Date.parse(d)) ? d : new Date().toISOString(),
        sourceCountry: a.sourcecountry || null,
      };
    });
    return { items, error: null };
  } catch (err) {
    return { items: [], error: err.message };
  }
}
