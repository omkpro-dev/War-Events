"""Poll averages for the Elections page, straight from the polling companies.

For every upcoming election in data/elections.json this reads the latest publications of that
country's main polling companies (data/pollsters.json: the firms whose polls Wikipedia's polling
pages are built from, each with its RSS feed or news page), spots new voting-intention polls,
pulls the numbers out with Claude, keeps every poll in data/polls.json, and writes a weighted
average, a 2-week trend and a 12-week series onto each contender.

Schedule (the workflow runs daily): each election is checked once a week, and every day once
the vote is 7 days away or less.

Average: polls from the last 45 days (else the latest 6), only the newest poll per pollster,
weighted by recency (half-life 10 days) x sqrt(sample size). Existing numbers are never wiped:
if nothing new is found, the card keeps what it had.

Needs ANTHROPIC_API_KEY. Standard library only.
  python news-feed/fetch_polls.py                       # normal run
  python news-feed/fetch_polls.py --only fr-2027-pres --force --verbose
  python news-feed/fetch_polls.py --candidates          # no Claude calls: list what each pollster offers
  python news-feed/fetch_polls.py --recompute           # rebuild averages from data/polls.json only
"""
import datetime as dt
import html as htmllib
import json, math, unicodedata, os, re, sys, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ELECTIONS = os.path.join(ROOT, "data", "elections.json")
POLLSTERS = os.path.join(ROOT, "data", "pollsters.json")
POLLS = os.path.join(ROOT, "data", "polls.json")
KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
UA = "Mozilla/5.0 (compatible; WarEventsPolls/1.0; +https://www.warevents.com)"
WINDOW_DAYS, HALF_LIFE, LOOKBACK_DAYS = 45, 10.0, 60
MAX_ARTICLES = int(os.environ.get("POLLS_MAX_ARTICLES", "5"))   # articles read per election per run
MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

ARGS = sys.argv[1:]
VERBOSE = "--verbose" in ARGS
FORCE = "--force" in ARGS
ONLY = ARGS[ARGS.index("--only") + 1] if "--only" in ARGS else None


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- fetching

def get(url, timeout=25):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en,*;q=0.5"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(4_000_000)
                return raw.decode(r.headers.get_content_charset() or "utf-8", "replace")
        except urllib.error.HTTPError as ex:
            if ex.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise
        except Exception:
            if attempt < 2:
                time.sleep(2)
                continue
            raise


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M %z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s.replace("Z", "+0000") if s.endswith("Z") else s, fmt).date()
        except ValueError:
            pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    return dt.date(int(m[1]), int(m[2]), int(m[3])) if m else None


class _Text(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg", "form", "aside"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag in ("p", "br", "tr", "li", "h1", "h2", "h3", "h4", "div", "table"):
            self.out.append("\n")
        if tag in ("td", "th"):
            self.out.append(" | ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d)


def strip_html(s):
    if "<" not in (s or ""):
        return htmllib.unescape(s or "").strip()
    p = _Text()
    p.feed(s)
    t = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.out))
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def feed_items(xml):
    """RSS 2.0 / Atom -> [{title, link, date, summary}]"""
    xml = re.sub(r"^[^<]+", "", xml)
    root = ET.fromstring(xml.encode("utf-8", "replace"))
    out = []
    for it in root.iter():
        if it.tag.split("}")[-1] not in ("item", "entry"):
            continue
        f = {c.tag.split("}")[-1]: c for c in it}
        link = ""
        for c in it:
            if c.tag.split("}")[-1] == "link":
                link = (c.text or "").strip() or c.get("href", "")
                if link:
                    break
        date = None
        for k in ("pubDate", "published", "updated", "date"):
            if k in f and f[k].text:
                date = parse_date(f[k].text)
                break
        summ = ""
        for k in ("description", "summary", "content", "encoded"):
            if k in f and f[k].text:
                summ = strip_html(f[k].text)[:400]
                break
        title = f["title"].text if "title" in f and f["title"].text else ""
        out.append({"title": strip_html(title), "link": link, "date": date.isoformat() if date else None, "summary": summ})
    return out


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self._href, self._txt = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._txt = dict(attrs).get("href"), []

    def handle_data(self, d):
        if self._href is not None:
            self._txt.append(d)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            t = re.sub(r"\s+", " ", "".join(self._txt)).strip()
            if len(t) > 20:
                self.links.append((self._href, t))
            self._href = None


def page_items(url):
    """A pollster's news / publications page without a feed: its article-looking links."""
    p = _Links()
    p.feed(get(url))
    host = urllib.parse.urlparse(url).netloc
    seen, out = set(), []
    for href, text in p.links:
        full = urllib.parse.urljoin(url, href).split("#")[0]
        if urllib.parse.urlparse(full).netloc != host or full in seen or full.rstrip("/") == url.rstrip("/"):
            continue
        seen.add(full)
        d = None
        m = re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", full)
        if m:
            try:
                d = dt.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
            except ValueError:
                pass
        out.append({"title": text[:200], "link": full, "date": d, "summary": ""})
    return out[:60]


# ---------------------------------------------------------------- Claude

def claude(prompt, max_tokens=1500):
    body = json.dumps({"model": MODEL, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")


def json_in(txt, open_c="{", close_c="}"):
    i, j = txt.find(open_c), txt.rfind(close_c)
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(txt[i:j + 1])
    except ValueError:
        return None


def contenders_txt(e):
    return "\n".join(f'- "{c["short"]}": {c["name"]}' + (f' (leader/party: {c["leader"]})' if c.get("leader") else "")
                     for c in e["contenders"])


POLL_WORDS = (r"poll|survey|voting intention|sond|umfrage|enquête|encuesta|pesquisa|turno|inquérito|sondaggio|"
              r"peiling|kannatus|mätning|måling|meningsmåling|anket|нагласи|проучване|опрос|anketa|kutatás|"
              r"δημοσκόπηση|סקר|מנדטים|استطلاع|نظرسنجی|anket|seçim|世論調査|여론조사|民調|民调|curia|newshub|"
              r"\d{1,2}[.,]?\d?\s?%|seats")


def kw_score(it, kw):
    t = (it["title"] + " " + it["summary"][:300]).lower()
    sc = 2 if re.search(POLL_WORDS, t, re.I) else 0
    sc += sum(1 for k in kw if k and k.lower() in t)
    sc += len(re.findall(r"\d{1,2}(?:[.,]\d)?\s?%", t))
    return sc


def pick_articles(e, items, kw):
    """Which of the pollsters' recent items report a voting-intention poll for this election?
    Claude chooses; if Claude returns nothing (or fails), fall back to the best keyword matches."""
    ranked = sorted(items, key=lambda it: (kw_score(it, kw), it["date"] or ""), reverse=True)
    items = ranked[:80]
    lst = "\n".join(f'{i}. [{it["pollster"]}] {it["title"]}' + (f' ({it["date"]})' if it["date"] else "")
                    + (f' -- {it["summary"][:160]}' if it["summary"] else "") for i, it in enumerate(items))
    prompt = (f"These are recent publications by polling companies or news outlets. Which ones most likely report a NATIONAL "
              f"voting-intention poll (or seat projection) for the {e['country']} {e['type']} on {e['date']}? "
              "Headlines may be in any language. Ignore approval ratings, consumer/brand research, other countries and local races. "
              f"Words that often appear in the right ones: {', '.join(kw) or 'none given'}.\n\n{lst}\n\n"
              f"Return ONLY a JSON array of up to {MAX_ARTICLES} item numbers, best first, e.g. [3, 0]. Return [] if none.")
    picks = []
    try:
        arr = json_in(claude(prompt, 200), "[", "]") or []
        picks = [items[i] for i in arr if isinstance(i, int) and 0 <= i < len(items)][:MAX_ARTICLES]
    except Exception as ex:
        log("  choosing articles failed:", str(ex)[:120])
    if not picks:
        picks = [it for it in items if kw_score(it, kw) >= 2][:3]
        if picks:
            log(f"  Claude picked none; trying {len(picks)} keyword matches")
    return picks


def extract_poll(e, it, text):
    prompt = (f"Below is a publication found on the feed of {it['pollster']} ({it['link']}). It may be in any language.\n"
              f"If it reports a national voting-intention poll (or seat projection) for the {e['country']} {e['type']} ({e['date']}), "
              "extract it. Contenders we track (use these keys exactly):\n" + contenders_txt(e) +
              "\n\nRules: use the headline voting-intention figures (first round / main scenario; with undecided "
              "excluded if both are given; for a runoff use the runoff figures); for seat projections use seats. "
              "Only include contenders that appear. Numbers only, no % signs. "
              "fieldwork_end is the last day of fieldwork (else the publication date). "
              "pollster is the company that carried out the poll (e.g. Datafolha, Curia, Maariv/Lazar), not the outlet, if named.\n"
              'Return ONLY JSON: {"is_poll": true, "pollster": "Name" or null, "fieldwork_end": "YYYY-MM-DD", "sample": 1000 or null, '
              '"unit": "pct" or "seats", "values": {"KEY": 31.5}} or {"is_poll": false, "why": "short reason"}.\n\n'
              f"--- PUBLICATION ---\n{it['title']}\n{it['summary'][:1500]}\n{text[:14000]}")
    return json_in(claude(prompt, 600))


def norm(t):
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode() or str(t)
    return re.sub(r"[^\w ]+", " ", t.lower()).strip()


def match_values(e, raw):
    """Map Claude's keys onto our contender shorts: exact, then accent/case-insensitive short/name/leader,
    then a shared distinctive word (e.g. 'Flávio Bolsonaro' -> 'F. Bolsonaro')."""
    look, words = {}, {}
    for c in e["contenders"]:
        for n in (c.get("short"), c.get("name"), c.get("leader")):
            if n:
                look.setdefault(norm(n), c["short"])
                for w in norm(n).split():
                    if len(w) > 3:
                        words.setdefault(w, set()).add(c["short"])
    out = {}
    for k, v in (raw or {}).items():
        if isinstance(v, str):
            m = re.search(r"\d+(?:[.,]\d+)?", v)
            v = float(m[0].replace(",", ".")) if m else None
        if not isinstance(v, (int, float)) or not 0 <= v <= 1000:
            continue
        key = k if any(c["short"] == k for c in e["contenders"]) else look.get(norm(k))
        if not key:
            hits = {sh for w in norm(k).split() for sh in words.get(w, ()) if len(words.get(w, ())) == 1}
            key = hits.pop() if len(hits) == 1 else None
        if key and key not in out:
            out[key] = float(v)
    return out


def page_text(it):
    """Article text; Google News / aggregator redirect pages carry nothing, so rely on title + summary there."""
    if "news.google." in it["link"]:
        return ""
    try:
        return strip_html(get(it["link"]))
    except Exception as ex:
        log(f"  page unreadable, using headline only ({str(ex)[:60]})")
        return ""


# ---------------------------------------------------------------- averaging

def avg_on(polls, keys, day):
    """Weighted average as of `day` (only polls up to that date)."""
    ps = [p for p in polls if p["date"] <= day.isoformat()]
    if not ps:
        return None, []
    recent = [p for p in ps if (day - dt.date.fromisoformat(p["date"])).days <= WINDOW_DAYS]
    if len(recent) < 2:
        recent = sorted(ps, key=lambda p: p["date"])[-6:]
    latest = {}
    for p in sorted(recent, key=lambda p: p["date"]):
        latest[p["pollster"]] = p                      # newest poll per pollster only
    use = list(latest.values())
    out = {}
    for k in keys:
        num = den = 0.0
        for p in use:
            v = p["values"].get(k)
            if v is None:
                continue
            age = (day - dt.date.fromisoformat(p["date"])).days
            w = 0.5 ** (age / HALF_LIFE) * math.sqrt(min(max(p.get("sample") or 800, 200), 3000))
            num += w * v
            den += w
        out[k] = round(num / den, 1) if den else None
    return out, use


def fmt(d1, d2):
    a, b = dt.date.fromisoformat(d1), dt.date.fromisoformat(d2)
    if a == b:
        return f"{b.day} {MON[b.month - 1]} {b.year}"
    if a.month == b.month and a.year == b.year:
        return f"{a.day}–{b.day} {MON[b.month - 1]} {b.year}"
    return f"{a.day} {MON[a.month - 1]} – {b.day} {MON[b.month - 1]} {b.year}"


def apply_average(e, polls, today):
    unit = polls[-1].get("unit", "pct")
    polls = [p for p in polls if p.get("unit", "pct") == unit]
    keys = [c["short"] for c in e["contenders"]]
    now, used = avg_on(polls, keys, today)
    if not now or sum(1 for v in now.values() if v is not None) < 2:
        return False
    newest = max(p["date"] for p in used)
    if (today - dt.date.fromisoformat(newest)).days > 120:
        e.setdefault("polling", {})["stale"] = True
        return False
    if unit == "pct" and sum(v for v in now.values() if v) > 110:
        log("  rejected average (adds up to more than 110%)")
        return False
    before, before_used = avg_on(polls, keys, today - dt.timedelta(days=14))
    no_new = before_used and {id(p) for p in before_used} == {id(p) for p in used}
    weeks = [today - dt.timedelta(days=7 * i) for i in range(11, -1, -1)]
    for c in e["contenders"]:
        k = c["short"]
        if now.get(k) is None:
            continue
        c["poll"] = now[k]
        c["trend"] = round(now[k] - before[k], 1) if before and before.get(k) is not None and not no_new else None
        ser = []
        for w in weeks:
            a, _ = avg_on([p for p in polls if (w - dt.date.fromisoformat(p["date"])).days <= WINDOW_DAYS], [k], w)
            if a and a.get(k) is not None:
                ser.append([w.isoformat(), a[k]])
        c["series"] = ser if len(ser) >= 2 else None
    names = sorted({p["pollster"] for p in used})
    d1 = min(p["date"] for p in used)
    what = "seat projections" if unit == "seats" else "polls"
    e["pollNote"] = (f"Average of {len(used)} {what}, {fmt(d1, newest)}" if len(used) > 1
                     else f"1 {'seat projection' if unit == 'seats' else 'poll'}, {fmt(d1, newest)}")
    pol = e.setdefault("polling", {})
    for k in ("wiki", "section", "map", "error", "unmatched", "searched", "stale"):
        pol.pop(k, None)
    pol.update({"method": "pollsters", "n": len(used), "from": d1, "to": newest, "unit": unit, "pollsters": names})
    src = [p["url"] for p in sorted(used, key=lambda p: p["date"], reverse=True) if p.get("url")][:3]
    if src:
        e["sources"] = src
    return True


# ---------------------------------------------------------------- main

def due(e, today):
    if e.get("status") != "upcoming" or len(e.get("contenders") or []) < 2 or "referendum" in e.get("type", "").lower():
        return False
    if FORCE:
        return True
    checked = (e.get("polling") or {}).get("checked")
    since = (today - dt.date.fromisoformat(checked)).days if checked else 999
    to_vote = (dt.date.fromisoformat(e["date"]) - today).days
    return since >= (1 if to_vote <= 7 else 7)


def collect(e, reg, today, cache):
    firms = (reg.get(e["code"]) or {}).get("pollsters", [])
    items = []
    cutoff = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    for f in firms:
        src = f.get("feed") or f.get("list")
        if not src:
            continue
        try:
            if src not in cache:
                cache[src] = feed_items(get(src)) if f.get("feed") else page_items(src)
            got = cache[src]
        except Exception as ex:
            log(f"  {f['name']}: could not read ({str(ex)[:80]})")
            continue
        agg = bool(f.get("aggregator")) or "news.google." in src or "/" in f["name"]
        got = [dict(g, pollster=f["name"], aggregator=agg) for g in got if g["link"] and (not g["date"] or g["date"] >= cutoff)]
        if f.get("match"):
            got = [g for g in got if re.search(f["match"], g["title"] + " " + g["link"] + " " + g["summary"], re.I)]
        if VERBOSE:
            log(f"  {f['name']}: {len(got)} recent items")
        items += got[:25]
    return items


def main():
    today = dt.date.today()
    data = json.load(open(ELECTIONS, encoding="utf-8"))
    reg = json.load(open(POLLSTERS, encoding="utf-8")).get("countries", {}) if os.path.exists(POLLSTERS) else {}
    store = json.load(open(POLLS, encoding="utf-8")) if os.path.exists(POLLS) else {}
    recompute, listing = "--recompute" in ARGS, "--candidates" in ARGS
    if not KEY and not (recompute or listing):
        log("ANTHROPIC_API_KEY not set; only recomputing averages from stored polls")
        recompute = True
    cache = {}
    for e in data.get("elections", []):
        if ONLY and e["id"] != ONLY:
            continue
        polls = store.setdefault(e["id"], [])
        if not recompute and due(e, today):
            log(f"{e['id']}:")
            items = collect(e, reg, today, cache)
            known = {p.get("url") for p in polls}
            items = [it for it in items if it["link"] not in known]
            if listing:
                for it in items[:40]:
                    log(f"   [{it['pollster']}] {it['date']} {it['title'][:100]}")
                continue
            picks = pick_articles(e, items[:200], (reg.get(e["code"]) or {}).get("keywords", [])) if items else []
            log(f"  {len(items)} new items, {len(picks)} chosen")
            for it in picks:
                try:
                    res = extract_poll(e, it, page_text(it))
                except Exception as ex:
                    log(f"  reading failed: {it['title'][:60]} ({str(ex)[:80]})")
                    continue
                if not res or not res.get("is_poll"):
                    log(f"  - not a poll: {it['title'][:70]}" + (f" ({str(res.get('why'))[:60]})" if res and res.get("why") else ""))
                    continue
                vals = match_values(e, res.get("values"))
                try:
                    d = dt.date.fromisoformat(str(res.get("fieldwork_end") or it["date"] or today.isoformat())[:10])
                except ValueError:
                    d = dt.date.fromisoformat(it["date"]) if it["date"] else today
                unit = "seats" if res.get("unit") == "seats" else "pct"
                why = ("fewer than 2 of our contenders" if len(vals) < 2 else "date in the future" if d > today
                       else "too old" if (today - d).days > 180
                       else "adds up to over 105%" if unit == "pct" and sum(vals.values()) > 105 else "")
                if why:
                    log(f"  - skipped ({why}): {it['title'][:60]} {res.get('values')}")
                    continue
                firm = str(res.get("pollster") or "").strip()
                if not it.get("aggregator") or not firm or len(firm) > 40:
                    firm = it["pollster"]      # a pollster's own feed: keep its name; an aggregator feed: name the firm in the story
                rec = {"pollster": firm, "date": d.isoformat(),
                       "sample": res.get("sample") if isinstance(res.get("sample"), int) else None,
                       "unit": unit, "values": vals, "url": it["link"], "added": today.isoformat()}
                dup = [p for p in polls if p["pollster"] == rec["pollster"] and p["date"] == rec["date"]]
                if dup:
                    dup[0].update(rec)
                else:
                    polls.append(rec)
                log(f"  + {firm} {rec['date']}: {vals}")
                time.sleep(0.5)
            e.setdefault("polling", {})["checked"] = today.isoformat()
        if polls:
            polls.sort(key=lambda p: p["date"])
            del polls[:-80]                         # keep the latest 80 per election
            if apply_average(e, polls, today):
                log(f"  {e['id']}: {e['pollNote']}")
    if listing:
        return
    store = {k: v for k, v in store.items() if v}
    with open(POLLS, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=1)
    tmp = ELECTIONS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    json.load(open(tmp, encoding="utf-8"))
    os.replace(tmp, ELECTIONS)
    log("done")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:     # never fail the workflow
        log("fetch_polls failed:", ex)
    sys.exit(0)
