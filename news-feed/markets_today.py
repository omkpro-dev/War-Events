#!/usr/bin/env python3
"""War Events: "Markets today" for the Economy page.

Reads the market headlines the Economy fetcher stored in the last 24 hours (news-feed/economy_seen.json),
asks Claude Haiku for one short sentence per market topic using only facts in those headlines and
descriptions, checks every sentence (known topic, topic once, cited headlines exist, every number appears
in the cited sources) and writes markets_today.json. When the selected headlines are the same as last run
no request is made and the previous file stays. Without ANTHROPIC_API_KEY nothing is written.
Standard library only.
"""
import hashlib, json, os, re, sys, urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import usage  # noqa: E402

ROOT = os.path.dirname(HERE)
SEEN = os.path.join(HERE, "economy_seen.json")
OUTPUT = os.path.join(ROOT, "markets_today.json")
CACHE = os.path.join(HERE, "markets_cache.json")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")

TOPICS = ["stocks", "europe", "asia", "bonds", "oil", "currencies", "crypto"]
MARKET_RX = re.compile(
    r"\b(stocks?|shares?|wall street|nasdaq|dow|s&p|ftse|nikkei|hang seng|stoxx|bonds?|yields?|treasur(?:y|ies)|"
    r"oil|brent|crude|dollar|euro|yen|sterling|currenc(?:y|ies)|bitcoin|crypto(?:currenc(?:y|ies))?)\b", re.I)
NUM_RX = re.compile(r"\d[\d.,]*%?")
# Not market reports: questions, explainers, forecasts, strategist views, history pieces. Left out of the roundup.
OPINION_RX = re.compile(
    r"\?|\b(why|how|what|could|might|may|should|would|risks?|strategists?|analysts? (?:say|see|warn)|outlook|explainer|"
    r"analysis|opinion|lessons?|history|matters|guide|to buy|ways to|19\d\d)\b", re.I)
# Not articles: quote pages and topic hubs that searches return, and markets outside Economy (no India or Pakistan).
JUNK_RX = re.compile(
    r"stock price &|latest news$|not available at this time|stock grades|\bindustry$|^prediction:|^\d+ [^,]*stocks?\b|"
    r"\bindia|\bindian\b|pakistan|sensex|nifty", re.I)
MIN_WORDS = 2   # a single word is a tag page, not a report
# A line must report a move (or a level held), not a background fact.
MOVE_RX = re.compile(
    r"\b(rose|rises?|risen|fell|falls?|fallen|gain(?:ed|s)?|lost|loses?|climb(?:ed|s)?|slid|slides?|slip(?:ped|s)?|"
    r"drop(?:ped|s)?|jump(?:ed|s)?|edged|rall(?:ied|ies|y)|slump(?:ed|s)?|surg(?:ed|es)|tumbl(?:ed|es)|soar(?:ed|s)|"
    r"sank|sinks?|stead(?:y|ied|ies)|flat|unchanged|firmed|weakened|strengthened|eased|advanced|declined|retreated|rebounded|"
    r"hit|closed|ended|traded)\b", re.I)
# Market reports from the wires and market desks first; other outlets fill the rest.
WIRE_ORDER = ["Reuters", "AP", "Bloomberg", "CNBC", "MarketWatch", "Financial Times", "The Wall Street Journal",
              "Barron's", "Nikkei Asia"]
PROMPT_V = "2"   # part of the cache key: a new prompt writes a new roundup


def log(*a):
    print(*a, flush=True)


def now_utc():
    return datetime.now(timezone.utc)


def _time(s):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def select_articles(articles, now, hours=24, limit=60):
    """Market headlines inside the window, newest first, each with a short id a1, a2, ..."""
    rows = []
    for a in articles:
        t = _time(a.get("time"))
        title = a.get("title") or ""
        if (t is None or not MARKET_RX.search(title) or OPINION_RX.search(title) or JUNK_RX.search(title)
                or len(title.split()) < MIN_WORDS):
            continue
        if timedelta(0) <= now - t <= timedelta(hours=hours) or (t > now and t - now < timedelta(minutes=10)):
            rows.append((t, a))
    rows.sort(key=lambda r: r[0], reverse=True)
    rank = {o: n for n, o in enumerate(WIRE_ORDER)}
    rows.sort(key=lambda r: rank.get(r[1].get("outlet"), len(WIRE_ORDER)))   # stable: newest first within a rank
    return [dict(a, id=f"a{n}") for n, (_, a) in enumerate(rows[:limit], 1)]


def build_prompt(selected):
    lst = "\n".join(f"{a['id']}. {a['title']} ({a.get('outlet', '')})"
                    + (f" - {a['desc']}" if a.get("desc") else "") for a in selected)
    return ("You write the \"Markets today\" box of a news app from the market reports below.\n\n"
            f"{lst}\n\n"
            "For each topic the reports clearly cover, write ONE short sentence reporting one market move from the "
            "last day: what moved, which way, and by how much when the report says (e.g. \"Wall Street fell 1.2% as "
            "Nvidia slid.\"). Topics: " + ", ".join(TOPICS) + " (stocks = US shares, europe = European shares, "
            "asia = shares in Japan, China and Hong Kong, South Korea, Taiwan or Australia, bonds = government bond "
            "yields, oil = oil and gas prices, currencies = the dollar, euro, yen or sterling, crypto = bitcoin and "
            "crypto). Each topic at most once.\n"
            "Rules: one move per sentence, never two stories joined with \"while\" or \"and\"; no forecasts, views, "
            "background, history or company profiles; skip a topic rather than fill it. Use only facts stated in the "
            "items above, no other knowledge, and no number that is not in the cited items. Cite the ids used.\n"
            "Return ONLY JSON: {\"items\": [{\"topic\": \"stocks\", \"text\": \"...\", \"ids\": [\"a1\"]}]}")


def _numbers(text):
    return {n.rstrip(".,%").replace(",", "") for n in NUM_RX.findall(text or "") if n.rstrip(".,%")}


def validate(items, selected):
    by_id = {a["id"]: a for a in selected}
    done = {}
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        topic, text = it.get("topic"), it.get("text")
        text = text.strip() if isinstance(text, str) else ""
        if not isinstance(topic, str) or topic not in TOPICS or topic in done or not text:
            continue
        ids = [i for i in it["ids"] if isinstance(i, str)] if isinstance(it.get("ids"), list) else []
        cited = [by_id[i] for i in dict.fromkeys(ids) if i in by_id]
        if not cited:
            continue
        source = " ".join(f"{a.get('title', '')} {a.get('desc', '')}" for a in cited)
        if not _numbers(text) <= _numbers(source):
            continue
        if not MOVE_RX.search(text):
            continue   # a background fact, not a market move
        outlets = list(dict.fromkeys(a.get("outlet") for a in cited if a.get("outlet")))
        done[topic] = {"topic": topic, "text": text, "outlets": outlets}
    return [done[t] for t in TOPICS if t in done]


def input_key(selected):
    return hashlib.sha1((PROMPT_V + "\n" + "\n".join(a["key"] for a in selected)).encode()).hexdigest()


def ask(prompt):
    body = json.dumps({"model": MODEL, "max_tokens": 900,
                       "thinking": {"type": "disabled"}, "output_config": {"effort": "low"},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        out = json.loads(r.read())
        usage.record(out)
    return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def _write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main():
    if not ANTHROPIC_KEY:
        log("markets: no ANTHROPIC_API_KEY, nothing written")
        return 0
    now = now_utc()
    store = _load(SEEN, [])
    selected = select_articles([a for a in store if isinstance(a, dict)], now)
    if not selected:
        log("markets: no market headlines in the last 24 hours, previous file kept")
        return 0
    key = input_key(selected)
    cache = _load(CACHE, {})
    if cache.get("key") == key and os.path.exists(OUTPUT):
        log("markets: same headlines as last run, previous file kept")
        return 0
    try:
        txt = ask(build_prompt(selected))
        mt = re.search(r"\{.*\}", txt, re.S)
        parsed = json.loads(mt.group(0)) if mt else {}
        items = parsed.get("items", []) if isinstance(parsed, dict) else []
    except Exception as ex:
        log(f"markets: request failed ({str(ex)[:80]}), previous file kept")
        return 0
    good = validate(items, selected)
    if not good:
        log("markets: no sentence passed the checks, previous file kept")
        return 0
    outlets = list(dict.fromkeys(o for i in good for o in i["outlets"]))
    _write(OUTPUT, {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "items": good, "outlets": outlets})
    _write(CACHE, {"key": key})
    log(f"markets: wrote {len(good)} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
