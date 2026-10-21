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

// Token use for this run, printed by extractClaims in the same [usage] format as the Python bots.
const PRICES = { 'claude-haiku-5-5': [0.10, 0.50], 'claude-sonnet-5-5': [2, 10], 'claude-opus-5-5': [4, 20] };
const usage = { calls: 0, inp: 0, read: 0, write: 0, out: 0 };
function addUsage(u = {}) {
  usage.calls++; usage.inp += u.input_tokens || 0; usage.read += u.cache_read_input_tokens || 0;
  usage.write += u.cache_creation_input_tokens || 0; usage.out += u.output_tokens || 0;
}
function usageLine() {
  const [pi, po] = Object.entries(PRICES).find(([k]) => MODEL.startsWith(k))?.[1] ?? [0, 0];
  const cost = (usage.inp * pi + usage.read * pi * 0.1 + usage.write * pi * 1.25 + usage.out * po) / 1e6;
  return `[usage] war_claims ${MODEL} calls=${usage.calls} in=${usage.inp} cache_read=${usage.read} cache_write=${usage.write} out=${usage.out} searches=0 cost=$${cost.toFixed(4)}`;
}

// Claude Sonnet 5.5 rejects thinking "disabled": "between_tools" is its lowest setting (no thinking
// here, as there are no tools). It also gets Anthropic's server-side fallback for declined requests.
const SONNET_55 = MODEL.startsWith('claude-sonnet-5-5');

async function callModel(article, conflict) {
  const actors = conflict.actors.map((a) => `${a.id} = ${a.name} (also: ${a.aliases.join(', ')})`).join('\n');
  const user = `Outlet: ${article.outlet}\nPublished: ${article.publishedAt}\nTitle: ${article.title}\nText: ${article.summary || '(none)'}`;
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': process.env.ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
      ...(SONNET_55 ? { 'anthropic-beta': 'server-side-fallback-2026-07-01' } : {}),
    },
    body: JSON.stringify({
      model: MODEL, max_tokens: 800,
      // instructions + this conflict's actors are the same for every article about it: cache them
      system: [{ type: 'text', text: SYSTEM },
               { type: 'text', text: `Conflict: ${conflict.name}\nActors:\n${actors}`, cache_control: { type: 'ephemeral' } }],
      messages: [{ role: 'user', content: user }],
      thinking: { type: SONNET_55 ? 'between_tools' : 'disabled' }, output_config: { effort: 'low' },
      ...(SONNET_55 ? { fallbacks: 'default' } : {}),
    }),
    signal: AbortSignal.timeout(45000),
  });
  if (!res.ok) throw new Error(`Anthropic API ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const data = await res.json();
  addUsage(data.usage);
  if (data.stop_reason === 'refusal') {
    console.warn('[claims] declined:', article.title.slice(0, 80), data.stop_details?.category ?? '');
    return [];
  }
  const raw = data.content?.find((b) => b.type === 'text')?.text ?? '[]';
  const json = raw.slice(raw.indexOf('['), raw.lastIndexOf(']') + 1);
  const parsed = JSON.parse(json || '[]');
  return Array.isArray(parsed) ? parsed : [];
}

/** One call on a made-up article, nothing saved: checks the model settings work (workflow "selftest"). */
export async function selfTest() {
  const conflict = CONFLICTS[0];
  const found = await callModel({ outlet: 'Test', publishedAt: new Date().toISOString(),
    title: `${conflict.actors[0].name} forces say they captured a village near the front line`, summary: '' }, conflict);
  console.log('selftest', conflict.id, JSON.stringify(found).slice(0, 300));
  console.log(usageLine());
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
  if (usage.calls) console.log(usageLine());
  return stored;
}
