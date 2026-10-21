"""Adds a written summary and country-impact data to each War Events story using Claude.

Runs hourly right after fetch_news.py (see .github/workflows/update-news.yml).
Needs the repo secret ANTHROPIC_API_KEY. Optional: CLAUDE_MODEL (default below).
Each story is only sent to Claude once; results are cached in news-feed/enrich_cache.json.
Standard library only.
"""
import html, json, os, re, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORIES = os.path.join(ROOT, os.environ.get("OUTPUT_PATH", "key_developments.json"))
CACHE = os.path.join(ROOT, "news-feed", "enrich_cache.json")
KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
MAX_NEW = int(os.environ.get("ENRICH_MAX", "20"))  # cap API calls per run
PROMPT_V = 5                                        # bump to re-ask Claude for every cached story
MIN_GEO = int(os.environ.get("MIN_GEO", "7"))       # stories Claude scores below this (0-10) are dropped from the site
UA = {"User-Agent": "Mozilla/5.0 (WarEvents enrich bot)"}

PROMPT = """You are a geopolitical news editor for the site War Events.
Story headline: {headline}
Location: {place}
Reported by: {outlets}
Article text (may be partial or empty):
{text}

Return ONLY a JSON object, no prose, with:
- "summary": 2-3 plain sentences (max 70 words) explaining what happened and why it matters geopolitically. Neutral, factual, no speculation beyond the reporting.
- "points": exactly 3 bullet points on what happened. Very basic, plain English a 12-year-old understands, max 14 words each, no jargon, no repeating the headline word for word.
- "impact_points": 2-4 bullet points on the potential geopolitical impact: who is affected and how. Same style: very basic, max 14 words each, grounded in the reporting.
- "geo": integer 0-10, how geopolitical this story is. 8-10 = wars, military action between or inside states, international crises, sanctions, major diplomacy, state-level energy/trade conflicts. 5-7 = significant security or political events with clear international consequences. 0-4 = domestic regulation, consumer/business news, markets, local crime, courts, elections with no international angle, human-interest. Judge the substance, not the keywords. Human-interest and personal stories score 0-3 EVEN IF set in a war zone: individual or family experiences, couples, love stories, profiles, "life under" pieces, diaries, testimonies, culture, food, sport or art in wartime, anniversaries and explainers with no new event. Score the EVENT and its consequences for states, not the setting.
- "actors": the impact of THIS story on each country, worked out from what the article actually says.
  Step 1, WHO: every country that is a direct party (attacker and target, both sides of talks or a deal, the sanctioner and the sanctioned, the country it happens in, a country sending help), then any country the article says is clearly affected. At least 2 whenever two or more countries are involved; max 6; most affected first. Use the country, not a group (Houthis -> YE, Hezbollah -> LB, Hamas/Gaza/West Bank -> PS).
  Step 2, WHY: for each country write one short reason (max 12 words) from the article: what this story does to that country.
  Step 3, SCORE: from that reason, an integer from -5 to +5 for that country:
    -5 attacked / casualties / major losses; -3 clear setback, pressure, costs, isolation; -1 slightly worse off;
     0 ONLY if genuinely balanced or not really affected;
    +1 slightly better off; +3 clear gain (support, leverage, a deal, relief); +5 major win.
  Judge each country from ITS OWN point of view; sides usually score differently. Do not default to 0. Do not give every country the same score.
  Format: {{"code": ISO 3166-1 alpha-2 uppercase, "why": "...", "score": -5..5}}
  RULE: the map shows exactly these countries, so readers must see WHY each one is there. Include BOTH the countries at the centre of the story AND any other country the FULL ARTICLE says could be affected (knock-on effects, allies, neighbours, markets). Then make sure every one of them is explained in the text: name it (by country, people or capital, e.g. "Russia", "Russian", "Moscow") in the "summary" or in an "impact_points" line. Use up to 4 impact_points so the wider effects are covered.
  The European Union as a bloc (EU institutions, EU sanctions, EU policy) uses the code "EU" instead of listing member states; name "the EU" or "the European Union" in the summary.
"""


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
        "messages": [{"role": "user", "content": PROMPT.format(
            headline=html.unescape(story.get("headline", "")), place=story.get("place", ""),
            outlets=", ".join(story.get("outlets", [])[:5]),
            text=article_text(story.get("sourceUrl", "")) or "(not available)")}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
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
    def bullets(v, n):
        if not isinstance(v, list):
            return []
        out = [re.sub(r"^[\s\-\u2022*]+", "", str(x)).strip() for x in v]
        return [x for x in out if x][:n]
    return {"v": PROMPT_V, "summary": str(data.get("summary", "")).strip(), "actors": actors, "geo": geo,
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
        if (sid not in cache or cache[sid].get("v") != PROMPT_V) and new < MAX_NEW:
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
        if e.get("summary"):
            s["body"] = "<b>What happened:</b> " + html.escape(e["summary"]) + ("<br><br>" + reported if reported else "")
        if e.get("actors"):
            s["impact"] = {"actors": e["actors"]}
        if e.get("points"):
            s["points"] = e["points"]
            s["impactPoints"] = e.get("impact_points", [])
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
