// AI claim extractor: turns a story like "Houthis capture key district in
// Taiz" into structured claims the Active Wars map can verify and apply.
//
// Off by default. Turn on by setting ANTHROPIC_API_KEY (and optionally
// ANTHROPIC_MODEL; pick a small, cheap model, check current names at
// https://docs.claude.com/en/docs/about-claude/models).
//
// Claims are only stored here with status "pending". Nothing changes on a
// map until the verification step (see the build plan) accepts them.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { CONFLICTS } from './sources.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const FILE = process.env.CLAIMS_FILE ?? path.join(here, '..', 'data', 'claims.json');
const MODEL = process.env.ANTHROPIC_MODEL ?? 'claude-haiku-5-5';
const MAX_PER_RUN = Number(process.env.CLAIMS_MAX_PER_RUN ?? 25);

export const claimsEnabled = () => Boolean(process.env.ANTHROPIC_API_KEY);

let claims = [];
try { claims = JSON.parse(fs.readFileSync(FILE, 'utf8')); } catch { /* first run */ }
const save = () => {
  const cutoff = Date.now() - 14 * 864e5;   // keep two weeks of claims
  claims = claims.filter((c) => !c.extractedAt || Date.parse(c.extractedAt) >= cutoff);
  fs.mkdirSync(path.dirname(FILE), { recursive: true });
  fs.writeFileSync(FILE, JSON.stringify(claims, null, 1));
};

export const listClaims = ({ conflict, status } = {}) =>
  claims.filter((c) => (!conflict || c.conflict === conflict) && (!status || c.status === status));

export function setClaimStatus(id, status, note) {
  const c = claims.find((x) => x.id === id);
  if (!c) return null;
  c.status = status; // pending | approved | rejected | contested
  c.reviewedAt = new Date().toISOString();
  if (note) c.note = note;
  save();
  return c;
}

const SYSTEM = `You extract territorial control claims from war news for a conflict map.
Return ONLY a JSON array (no prose). Each element:
{"place": string, "admin_hint": string|null, "gainer": actor_id|null, "loser": actor_id|null,
 "kind": "capture"|"withdrawal"|"contested"|"advance"|"denial", "claimed_by": "gainer"|"loser"|"third_party"|"unclear",
 "voice": "reported"|"attributed", "wire": "Reuters"|"AP"|"AFP"|null,
 "quote": string (the exact words from the text that state it), "confidence": number 0-1}
Rules:
- Only include a claim if the text says an armed group gained, lost or is fighting for CONTROL of a named place.
- Airstrikes, shelling, drone or missile attacks, raids and casualties alone are NOT control changes: return [].
- "Advance toward" or "near" a place is kind "advance", never "capture".
- If a side announces its own gain and nobody independent confirms it, claimed_by is "gainer".
- Use only the actor ids provided. Unknown actor -> null.
- place = the most specific named place (village, district, city). admin_hint = its district or province if named.
- voice = "reported" only if the outlet itself states the change as fact (its own reporting, or citing independent confirmation). If it only relays what a side says ("X says it captured", "according to the Houthis"), voice = "attributed".
- wire = the news agency if the story is credited to Reuters, AP or AFP (byline, dateline or "(Reuters)"), else null.
- kind "denial" = a side or official denies a reported capture of the place.
- No claims -> [].`;

async function callModel(article, conflict) {
  const actors = conflict.actors.map((a) => `${a.id} = ${a.name} (also: ${a.aliases.join(', ')})`).join('\n');
  const user = `Conflict: ${conflict.name}\nActors:\n${actors}\n\nOutlet: ${article.outlet}\nPublished: ${article.publishedAt}\nTitle: ${article.title}\nText: ${article.summary || '(none)'}`;
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': process.env.ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({ model: MODEL, max_tokens: 800, system: SYSTEM, messages: [{ role: 'user', content: user }],
      thinking: { type: 'disabled' }, output_config: { effort: 'low' } }),
    signal: AbortSignal.timeout(45000),
  });
  if (!res.ok) throw new Error(`Anthropic API ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const data = await res.json();
  const raw = data.content?.find((b) => b.type === 'text')?.text ?? '[]';
  const json = raw.slice(raw.indexOf('['), raw.lastIndexOf(']') + 1);
  const parsed = JSON.parse(json || '[]');
  return Array.isArray(parsed) ? parsed : [];
}

/** Extract claims from new articles. Returns the number of claims stored. */
export async function extractClaims(articles) {
  let stored = 0;
  const seen = new Set(claims.map((c) => c.articleId));
  for (const article of articles.filter((a) => !seen.has(a.id)).slice(0, MAX_PER_RUN)) {
    const conflict = CONFLICTS.find((c) => c.id === article.conflict);
    if (!conflict) continue;
    try {
      const found = await callModel(article, conflict);
      for (const [n, c] of found.entries()) {
        if (!c.place || !c.quote) continue;
        claims.push({
          id: `${article.id}-${n}`,
          articleId: article.id,
          conflict: conflict.id,
          url: article.url,
          outlet: article.outlet,
          publishedAt: article.publishedAt,
          title: article.title,
          place: c.place,
          adminHint: c.admin_hint ?? null,
          gainer: c.gainer ?? null,
          loser: c.loser ?? null,
          kind: c.kind,
          claimedBy: c.claimed_by ?? 'unclear',
          quote: c.quote,
          voice: c.voice === 'reported' ? 'reported' : 'attributed',
          wire: c.wire || null,
          confidence: Number(c.confidence) || 0,
          status: 'pending',
          extractedAt: new Date().toISOString(),
        });
        stored++;
      }
      // Mark the article as processed even with no claims, so it isn't re-sent.
      if (!found.length) claims.push({ id: `${article.id}-none`, articleId: article.id, conflict: conflict.id, status: 'none' });
    } catch (err) {
      console.warn('[claims]', err.message);
    }
  }
  if (articles.length) save();
  return stored;
}
