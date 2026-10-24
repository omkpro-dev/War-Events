"""Adds a written summary and country-impact data to each War Events story using Claude.

Runs hourly right after fetch_news.py (see .github/workflows/update-news.yml).
Needs the repo secret ANTHROPIC_API_KEY. Optional: CLAUDE_MODEL (default below).
Each story is only sent to Claude once; results are cached in news-feed/enrich_cache.json.
Standard library only.
"""
import html, json, os, re, urllib.request
import usage   # prints this run's token use and cost to the log

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORIES = os.path.join(ROOT, os.environ.get("OUTPUT_PATH", "key_developments.json"))
CACHE = os.path.join(ROOT, "news-feed", "enrich_cache.json")
KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
MAX_NEW = int(os.environ.get("ENRICH_MAX", "20"))  # cap API calls per run
PROMPT_V = 11                                        # bump to re-ask Claude for every cached story
MIN_GEO = int(os.environ.get("MIN_GEO", "7"))       # stories Claude scores below this (0-10) are dropped from the site
UA = {"User-Agent": "Mozilla/5.0 (WarEvents enrich bot)"}

# Fixed instructions go in the (cached) system prompt and the story in the user turn, so every call
# after the first in an hour reads the instructions from the prompt cache at a tenth of the price.
SYSTEM = """You are a geopolitical news editor for the site War Events. War Events is an aggregator: it does not republish articles. It writes its own short summary of the ONE article the site links to, and the reader can click through to that article.

You are given that article's outlet, its headline and, where we could read it, its text. Summarise THIS article only: do not bring in reporting from other outlets and do not combine sources. If the text is missing, work from the headline and never mention to readers that text was unavailable.

HOW TO WRITE (applies to "headline", "summary" and "impact_points"):
- Original wording only. Never reuse a sentence or a distinctive phrase from the article or its headline. Rebuild every sentence from the facts, and do not follow the order or structure of the article.
- No direct quotes. If the exact words are the news, quote at most four words, in quotation marks, attributed.
- Attribute claims to whoever made them ("Iran says...", "officials said...") and say when something could not be verified.
- Wire services (Reuters, AP, AFP, Bloomberg): rewrite especially heavily. Make sure nothing reads like their copy.
- Be accurate to the article: names, numbers, places and dates. Add nothing it does not support.
- Never describe your own sourcing in the text (no "reporting was drawn from Reuters", "according to the article provided").

Return ONLY a JSON object, no prose, with:
- "headline": your own headline for this article: accurate, neutral and specific, max 15 words, sentence case, no quotation marks, no clickbait, and not the original headline's wording.
- "summary": 50 to 100 plain words in one or two short paragraphs separated by a blank line: what happened, who, where, and the most important detail, in your own words. Neutral and factual, no speculation beyond the reporting.
- "points": always an empty list [].
- "impact_points": exactly 2 sentences on why it matters, naming who is affected and how. Each begins with the main country, group or organisation affected, then what happens to it. Plain English, max 20 words each, grounded in the reporting.
- "geo": integer 0-10, how geopolitical this story is. 8-10 = wars, military action between or inside states, international crises, sanctions, major diplomacy, state-level energy/trade conflicts. 5-7 = significant security or political events with clear international consequences. 0-4 = domestic regulation, consumer/business news, markets, local crime, courts, elections with no international angle, human-interest. Judge the substance, not the keywords. Human-interest and personal stories score 0-3 EVEN IF set in a war zone: individual or family experiences, couples, love stories, profiles, "life under" pieces, diaries, testimonies, culture, food, sport or art in wartime, anniversaries and explainers with no new event. Score the EVENT and its consequences for states, not the setting.
- "severity": integer 1-5, how serious the EVENT itself is, on this scale: 1 = statements, diplomacy, talks or votes; 2 = protests, unrest, sanctions or threats; 3 = disruption or a non-lethal attack (infrastructure, cyber, blockade, seizure, arrests); 4 = a lethal attack or fighting; 5 = mass casualties, or a strategic shock (a major chokepoint closed, a capital attacked, a new war). Judge what happened, not the tone of the coverage. If unsure between two levels, choose the lower.
- "actors": the impact of THIS story on each country, worked out from what the article actually says.
  Step 1, WHO: every country that is a direct party (attacker and target, both sides of talks or a deal, the sanctioner and the sanctioned, the country it happens in, a country sending help), then any country the article says is clearly affected. At least 2 whenever two or more countries are involved; max 6; most affected first. Use the country, not a group (Houthis -> YE, Hezbollah -> LB, Hamas/Gaza/West Bank -> PS).
  Step 2, WHY: for each country write one short reason (max 12 words) from the article: what this story does to that country.
  Step 3, SCORE: from that reason, an integer from -5 to +5 for that country:
    -5 attacked / casualties / major losses; -3 clear setback, pressure, costs, isolation; -1 slightly worse off;
     0 ONLY if genuinely balanced or not really affected;
    +1 slightly better off; +3 clear gain (support, leverage, a deal, relief); +5 major win.
  Judge each country from ITS OWN point of view; sides usually score differently. Do not default to 0. Do not give every country the same score.
  Format: {"code": ISO 3166-1 alpha-2 uppercase, "why": "...", "score": -5..5}
  RULE: the map shows exactly these countries, so readers must see WHY each one is there. Include BOTH the countries at the centre of the story AND any other country the FULL ARTICLE says could be affected (knock-on effects, allies, neighbours, markets). Then make sure every one of them is explained in the text: name it (by country, people or capital, e.g. "Russia", "Russian", "Moscow") in the "summary" or in an "impact_points" line. Use up to 4 impact_points so the wider effects are covered.
  The European Union as a bloc (EU institutions, EU sanctions, EU policy) uses the code "EU" instead of listing member states; name "the EU" or "the European Union" in the summary.
"""

STORY = """Outlet: {outlet}
Location: {place}
Headline: {headline}
Article text (may be partial or empty):
{text}"""


def story_text(story):
    """The article text: from the source link the site shows, else (when that page cannot be read) from another outlet's page on the same story."""
    for url in [story.get("sourceUrl", "")] + story.get("textUrls", []):
        if url and "news.google.com" not in url:
            text = article_text(url)
            if len(text) > 300:
                return text
    return ""


def article_text(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            raw = r.read(400000).decode("utf-8", "replace")
    except Exception:
        return ""
    raw = re.sub(r"(?is)<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", " ", raw)
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", raw)
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", "", p)).strip() for p in paras)
    return re.sub(r"\s+", " ", text)[:5000]


def ask_claude(story):
    body = json.dumps({
        "model": MODEL, "max_tokens": 1200,
        # Haiku 5.5: simple extraction task, so no thinking and low effort keeps it cheap + fast.
        "thinking": {"type": "disabled"}, "output_config": {"effort": "low"},
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
        "messages": [{"role": "user", "content": STORY.format(
            outlet=(story.get("outlets") or [""])[0], place=story.get("place", ""),
            headline=html.unescape(story.get("headline", "")),
            text=story_text(story) or "(not available)")}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
        usage.record(out)
    txt = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", txt, re.S)
    data = json.loads(m.group(0)) if m else {}
    actors, seen = [], set()
    for a in data.get("actors", [])[:8]:
        code = str(a.get("code", "")).upper()
        if not (re.fullmatch(r"[A-Z]{2}", code)) or code in seen:
            continue
        try:
            score = max(-5.0, min(5.0, float(a.get("score", 0))))
        except Exception:
            score = 0.0
        seen.add(code)
        # -5..+5 -> 0..1 on the site's Negative / Mixed / Positive scale
        actors.append({"code": code, "pos": round((score + 5) / 10, 3), "why": str(a.get("why", "")).strip()[:120]})
    actors = actors[:6]
    try:
        geo = max(0, min(10, int(data.get("geo", 10))))
    except Exception:
        geo = 10
    sev = data.get("severity")
    severity = sev if isinstance(sev, int) and not isinstance(sev, bool) and 1 <= sev <= 5 else None
    def bullets(v, n):
        if not isinstance(v, list):
            return []
        out = [re.sub(r"^[\s\-\u2022*]+", "", str(x)).strip() for x in v]
        return [x for x in out if x][:n]
    return {"v": PROMPT_V, "headline": re.sub(r"\s+", " ", str(data.get("headline", ""))).strip().strip("\"\u201c\u201d"), "summary": str(data.get("summary", "")).strip(), "actors": actors, "geo": geo, "severity": severity,
            "points": bullets(data.get("points"), 3), "impact_points": bullets(data.get("impact_points"), 4)}


def main():
    if not KEY:
        print("ANTHROPIC_API_KEY not set; skipping enrichment")
        return
    try:
        stories = json.load(open(STORIES, encoding="utf-8"))
    except Exception as e:
        print("no stories:", e)
        return
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        cache = {}
    new = 0
    for s in stories:
        sid = s.get("id")
        if not sid:
            continue
        # Re-ask once for stories cached before the bullet points existed.
        # also redo summaries written without the article text once another outlet's page can be read
        notext = "not available" in cache.get(sid, {}).get("summary", "") and s.get("textUrls")
        if (sid not in cache or cache[sid].get("v") != PROMPT_V or notext) and new < MAX_NEW:
            try:
                cache[sid] = ask_claude(s)
                new += 1
            except Exception as e:
                print("claude failed for", sid, e)
                continue
        e = cache.get(sid)
        if not e:
            continue
        reported = s.get("body", "")
        if "Reported by" in reported:
            reported = reported[reported.index("<b>Reported by"):]
        if e.get("headline") and len(e["headline"]) > 12:
            # War Events' own headline; the outlets' wording is not republished. Kept for reference only.
            s.setdefault("sourceHeadline", s.get("headline", ""))
            s["headline"] = html.escape(e["headline"], quote=False)
        if e.get("summary"):
            paras = [html.escape(x.strip()) for x in re.split(r"\n\s*\n", e["summary"]) if x.strip()]
            s["body"] = "<b>What happened:</b> " + "<br><br>".join(paras) + ("<br><br>" + reported if reported else "")
        if e.get("actors"):
            s["impact"] = {"actors": e["actors"]}
        if e.get("points"):
            s["points"] = e["points"]
        else:
            s.pop("points", None)   # the newer summaries are written as one piece, with no separate key-point list
        if e.get("impact_points"):
            s["impactPoints"] = e["impact_points"]
        if e.get("severity"):
            s["severity"] = e["severity"]   # Vandict's 1-5 scale; the site ignores it
    live = {s.get("id") for s in stories}
    before = len(stories)
    stories = [s for s in stories if cache.get(s.get("id"), {}).get("geo", 10) >= MIN_GEO]
    print("dropped as not geopolitical:", before - len(stories))
    cache = {k: v for k, v in cache.items() if k in live or len(cache) < 400}
    json.dump(stories, open(STORIES, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    print("enriched new:", new)


if __name__ == "__main__":
    main()
