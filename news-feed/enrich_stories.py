"""Adds a written summary and country-impact data to each War Events story using Claude.

Runs hourly right after fetch_news.py (see .github/workflows/update-news.yml).
Needs the repo secret ANTHROPIC_API_KEY. Optional: CLAUDE_MODEL (default below).
Each story is only sent to Claude once; results are cached in news-feed/enrich_cache.json.
Standard library only.
"""
import html, json, os, re, tempfile, time, urllib.request
import sourcing
from gazetteer import place_for_iso2
import usage   # prints this run's token use and cost to the log

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORIES = os.path.join(ROOT, os.environ.get("OUTPUT_PATH", "key_developments.json"))
SECTION = os.environ.get("SECTION", "war")           # "war" or "economy": picks the instructions and the filters
CACHE = os.environ.get("ENRICH_CACHE_PATH") or os.path.join(ROOT, "news-feed", "enrich_cache.json")
KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
MAX_NEW = int(os.environ.get("ENRICH_MAX", "20"))  # cap API calls per run
BUDGET_S = float(os.environ.get("ENRICH_BUDGET_S", "150"))   # no new Claude asks after this many seconds (job timeout is 8 min)
PROMPT_V = 12                                        # bump to re-ask Claude for every cached story
MIN_GEO = int(os.environ.get("MIN_GEO", "7"))       # stories Claude scores below this (0-10) are dropped from the site
MAX_FETCHES = 6                                      # page reads per story, failed ones included (each can take 15 s)
SECTIONS = ("war", "economy")
UA = {"User-Agent": "Mozilla/5.0 (WarEvents enrich bot)"}

# Fixed instructions go in the (cached) system prompt and the story in the user turn, so every call
# after the first in an hour reads the instructions from the prompt cache at a tenth of the price.
WAR_INTRO = """You are a geopolitical news editor for the site War Events. War Events is an aggregator: it does not republish articles. It writes its own short summary of a story that several outlets cover, and the reader can click through to the articles.

You are given the story's headline and the text of up to three articles from different outlets, then the other outlets' headlines. Write ONE summary of the story from all the article texts you are given, combining what they report. Never copy any one outlet's structure or wording. If no text is given, work from the headlines and never mention to readers that text was unavailable.

"""

WRITING_RULES = """HOW TO WRITE (applies to "headline", "summary" and "impact_points"):
- Original wording only. Never reuse a sentence or a distinctive phrase from any article or headline. Rebuild every sentence from the facts, and do not follow the order or structure of any article.
- No direct quotes. If the exact words are the news, quote at most four words, in quotation marks, attributed.
- Attribute claims to whoever made them ("Iran says...", "officials said...") and say when something could not be verified.
- Wire services (Reuters, AP, AFP, Bloomberg): rewrite especially heavily. Make sure nothing reads like their copy.
- Be accurate to the articles: names, numbers, places and dates. Add nothing they do not support.
- Never describe your own sourcing in the text (no "reporting was drawn from Reuters", "according to the article provided").

"""

WAR_JSON = """Return ONLY a JSON object, no prose, with:
- "headline": your own headline for this story: accurate, neutral and specific, max 15 words, sentence case, no quotation marks, no clickbait, and not the original headline's wording.
- "summary": 50 to 100 plain words in one or two short paragraphs separated by a blank line: what happened, who, where, and the most important detail, in your own words. Neutral and factual, no speculation beyond the reporting.
- "points": always an empty list [].
- "impact_points": exactly 2 sentences on why it matters, naming who is affected and how. Each begins with the main country, group or organisation affected, then what happens to it. Plain English, max 20 words each, grounded in the reporting.
- "geo": integer 0-10, how geopolitical this story is. 8-10 = wars, military action between or inside states, international crises, sanctions, major diplomacy, state-level energy/trade conflicts. 5-7 = significant security or political events with clear international consequences. 0-4 = domestic regulation, consumer/business news, markets, local crime, courts, elections with no international angle, human-interest. Judge the substance, not the keywords. Human-interest and personal stories score 0-3 EVEN IF set in a war zone: individual or family experiences, couples, love stories, profiles, "life under" pieces, diaries, testimonies, culture, food, sport or art in wartime, anniversaries and explainers with no new event. Score the EVENT and its consequences for states, not the setting.
- "severity": integer 1-5, how serious the EVENT itself is, on this scale: 1 = statements, diplomacy, talks or votes; 2 = protests, unrest, sanctions or threats; 3 = disruption or a non-lethal attack (infrastructure, cyber, blockade, seizure, arrests); 4 = a lethal attack or fighting; 5 = mass casualties, or a strategic shock (a major chokepoint closed, a capital attacked, a new war). Judge what happened, not the tone of the coverage. If unsure between two levels, choose the lower.
- "actors": the impact of THIS story on each country, worked out from what the reporting actually says.
  Step 1, WHO: every country that is a direct party (attacker and target, both sides of talks or a deal, the sanctioner and the sanctioned, the country it happens in, a country sending help), then any country these reports say is clearly affected. At least 2 whenever two or more countries are involved; max 6; most affected first. Use the country, not a group (Houthis -> YE, Hezbollah -> LB, Hamas/Gaza/West Bank -> PS).
  Step 2, WHY: for each country write one short reason (max 12 words) from the reporting: what this story does to that country.
  Step 3, SCORE: from that reason, an integer from -5 to +5 for that country:
    -5 attacked / casualties / major losses; -3 clear setback, pressure, costs, isolation; -1 slightly worse off;
     0 ONLY if genuinely balanced or not really affected;
    +1 slightly better off; +3 clear gain (support, leverage, a deal, relief); +5 major win.
  Judge each country from ITS OWN point of view; sides usually score differently. Do not default to 0. Do not give every country the same score.
  Format: {"code": ISO 3166-1 alpha-2 uppercase, "why": "...", "score": -5..5}
  RULE: the map shows exactly these countries, so readers must see WHY each one is there. Include BOTH the countries at the centre of the story AND any other country the FULL REPORTING says could be affected (knock-on effects, allies, neighbours, markets). Then make sure every one of them is explained in the text: name it (by country, people or capital, e.g. "Russia", "Russian", "Moscow") in the "summary" or in an "impact_points" line. Use up to 4 impact_points so the wider effects are covered.
  The European Union as a bloc (EU institutions, EU sanctions, EU policy) uses the code "EU" instead of listing member states; name "the EU" or "the European Union" in the summary.
"""

ECONOMY_INTRO = """You are an economics and markets news editor for the site War Events. War Events is an aggregator: it does not republish articles. It writes its own short summary of a story that several outlets cover, and the reader can click through to the articles.

You are given the story's headline and the text of up to three articles from different outlets, then the other outlets' headlines. Write ONE summary of the story from all the article texts you are given, combining what they report. Never copy any one outlet's structure or wording. If no text is given, work from the headlines and never mention to readers that text was unavailable.

"""

ECONOMY_JSON = """Return ONLY a JSON object, no prose, with:
- "headline": your own headline for this story: accurate, neutral and specific, max 15 words, sentence case, no quotation marks, no clickbait, and not any original headline's wording.
- "summary": 50 to 100 plain words in one or two short paragraphs separated by a blank line: what happened, who is affected, and the market impact, in your own words. Neutral and factual, no speculation beyond the reporting.
- "points": always an empty list [].
- "impact_points": exactly 2 sentences on who is affected and how. Each begins with the main country, group, company or sector affected, then what happens to it. Plain English, max 20 words each, grounded in the reporting.
- "country": the ISO 3166-1 alpha-2 uppercase code of the country the story is mainly about. When no place is given, use the country of the institution, company, regulator or market named (Federal Reserve -> US, University of Cambridge -> GB). Use "EU" for EU institutions as a bloc.
- "actors": the economic impact of THIS story on each country, worked out from what the articles actually say.
  Step 1, WHO: every country directly involved (the country whose institution, company or market acts, the countries trading, taxed, sanctioned or lending), then any country the articles say is clearly affected. At least 1; max 6; most affected first. Use the country, not a group.
  Step 2, WHY: for each country write one short reason (max 12 words) from the articles: what this story does to that country's economy, businesses or households.
  Step 3, SCORE: from that reason, an integer from -5 to +5 for that country's economic effect:
    -5 severe harm (crash, default, mass job losses); -3 clear setback, higher costs, losses; -1 slightly worse off;
     0 ONLY if genuinely balanced or not really affected;
    +1 slightly better off; +3 clear gain (growth, relief, a deal); +5 major boost.
  Judge each country from ITS OWN point of view; countries usually score differently. Do not default to 0.
  Format: {"code": ISO 3166-1 alpha-2 uppercase, "why": "...", "score": -5..5}
  RULE: name every country you list (by country, people or capital) in the "summary" or in an "impact_points" line. Use up to 4 impact_points so the wider effects are covered. The EU as a bloc uses the code "EU"; name "the EU" in the summary.
"""

SYSTEM = WAR_INTRO + WRITING_RULES + WAR_JSON
ECONOMY_SYSTEM = ECONOMY_INTRO + WRITING_RULES + ECONOMY_JSON


def check_section(section):
    if section not in SECTIONS:
        raise ValueError("unknown SECTION %r: use one of %s" % (section, ", ".join(SECTIONS)))


def system_prompt(section):
    check_section(section)
    return ECONOMY_SYSTEM if section == "economy" else SYSTEM


def story_texts(story, fetch=None):
    """Up to 3 (outlet, text) pairs from different outlets, read from the source link first, then the other outlets' pages."""
    fetch = fetch or article_text
    outlet_of = {c.get("u"): c.get("o", "") for c in story.get("coverage", []) if c.get("u")}
    first = (story.get("outlets") or [""])[0]
    urls = [story.get("sourceUrl", "")] + list(story.get("textUrls", [])) + [c.get("u", "") for c in story.get("coverage", [])]
    out, families, tried, fetches = [], [], set(), 0
    for url in urls:
        if len(out) >= 3 or fetches >= MAX_FETCHES:
            break
        if not url or url in tried or "news.google.com" in url:
            continue
        tried.add(url)
        outlet = outlet_of.get(url) or first
        fam = sourcing.outlet_family(outlet)
        if fam in families:
            continue
        fetches += 1
        text = fetch(url)
        if len(text) > 300:
            families.append(fam)
            out.append((outlet, text))
    return out


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


def user_message(story, texts):
    parts = []
    for outlet, text in texts:
        parts.append("Article from %s:\n%s" % (outlet, text))
    heads = [html.unescape(c.get("h", "")) for c in story.get("coverage", []) if c.get("h")]
    parts.append("Headline: " + html.unescape(story.get("headline", "")))
    if heads:
        parts.append("Other outlets' headlines:\n" + "\n".join("- " + h for h in heads))
    if story.get("place"):
        parts.append("Location: " + story["place"])
    return "\n\n".join(parts)


def parse_reply(text, section):
    m = re.search(r"\{.*\}", text, re.S)
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
    country = str(data.get("country") or "").strip().upper()
    country = country if re.fullmatch(r"[A-Z]{2}", country) else None
    def bullets(v, n):
        if not isinstance(v, list):
            return []
        out = [re.sub(r"^[\s\-\u2022*]+", "", str(x)).strip() for x in v]
        return [x for x in out if x][:n]
    return {"v": PROMPT_V, "headline": re.sub(r"\s+", " ", str(data.get("headline", ""))).strip().strip("\"\u201c\u201d"), "summary": str(data.get("summary", "")).strip(), "actors": actors, "geo": geo, "severity": severity,
            "points": bullets(data.get("points"), 3), "impact_points": bullets(data.get("impact_points"), 4),
            "country": country}


def keep_story(entry, section):
    check_section(section)
    return section == "economy" or entry.get("geo", 10) >= MIN_GEO


def ask_claude(story):
    texts = story_texts(story)
    body = json.dumps({
        "model": MODEL, "max_tokens": 1200,
        # Haiku 5.5: simple extraction task, so no thinking and low effort keeps it cheap + fast.
        "thinking": {"type": "disabled"}, "output_config": {"effort": "low"},
        "system": [{"type": "text", "text": system_prompt(SECTION), "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
        "messages": [{"role": "user", "content": user_message(story, texts)}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
        usage.record(out)
    txt = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
    return parse_reply(txt, SECTION)


def apply_country(story, country):
    """Economy: a story with no place gets the pin of the country Claude named. True when it has a place."""
    if story.get("place"):
        return True
    p = place_for_iso2(country)
    if not p:
        return False
    story["place"], story["cat"], story["lat"], story["lon"] = p["label"], p["cat"], p["lat"], p["lon"]
    return True


def save_json(path, data, **kw):
    """Write JSON atomically: a temp file in the same folder, then os.replace, so a killed job never leaves half a file."""
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".enrich-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, **kw)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def main(ask=None, clock=None):
    """ask(story) -> cache entry and clock() -> seconds can be swapped in by tests."""
    try:
        check_section(SECTION)
    except ValueError as e:
        raise SystemExit(str(e))
    ask = ask or ask_claude
    clock = clock or time.monotonic
    start = clock()
    if not KEY:
        if SECTION != "economy":
            print("ANTHROPIC_API_KEY not set; skipping enrichment")
            return
        # Economy still runs the place filter below: a story with no pin must never be published.
        print("ANTHROPIC_API_KEY not set; no new summaries, cached ones and the place filter still apply")
    try:
        with open(STORIES, encoding="utf-8") as f:
            stories = json.load(f)
    except Exception as e:
        print("no stories:", e)
        return
    try:
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    new, out_of_time = 0, False
    for s in stories:
        sid = s.get("id")
        if not sid:
            continue
        # Re-ask once for stories cached before the bullet points existed.
        # also redo summaries written without the article text once another outlet's page can be read
        notext = "not available" in cache.get(sid, {}).get("summary", "") and s.get("textUrls")
        wants = sid not in cache or cache[sid].get("v") != PROMPT_V or notext
        if wants and KEY and new < MAX_NEW and not out_of_time and clock() - start >= BUDGET_S:
            out_of_time = True   # the rest wait for the next run; stories already cached still go out
            print("time budget of %.0f s used; no more asks this run" % BUDGET_S)
        if wants and KEY and new < MAX_NEW and not out_of_time:
            try:
                cache[sid] = ask(s)
                new += 1
            except Exception as e:
                print("claude failed for", sid, e)
                continue
            save_json(CACHE, cache)   # keep each answer even if the job is killed before the end
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
        if SECTION == "economy":
            apply_country(s, e.get("country"))
    live = {s.get("id") for s in stories}
    before = len(stories)
    stories = [s for s in stories if keep_story(cache.get(s.get("id"), {}), SECTION)]
    print("dropped as not geopolitical:", before - len(stories))
    if SECTION == "economy":
        n = len(stories)
        stories = [s for s in stories if s.get("place")]   # every story needs a pin
        print("dropped for no place:", n - len(stories))
    cache = {k: v for k, v in cache.items() if k in live or len(cache) < 400}
    save_json(STORIES, stories, separators=(",", ":"))
    save_json(CACHE, cache)
    print("enriched new:", new)


if __name__ == "__main__":
    main()
