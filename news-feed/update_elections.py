"""Keeps data/elections.json (the Elections page) current, using Claude with web search.

Scope: NATIONAL elections and national referendums only, in Europe, North America
(United States, Canada, Mexico), Brazil and Argentina, East Asia (Japan, the Koreas, Taiwan,
China, Mongolia), Australia and New Zealand, Iran, Israel, Turkey, Egypt and North Africa.

Each run (daily, from .github/workflows/update-elections.yml):
  1. Re-checks the elections that need it most -- every day for anything within 7 days or
     whose date has passed without a result, and once a week for everything else -- up to
     MAX_UPDATES per run: date, candidates, polls, compass positions, result.
  2. Once a week, looks for newly called national elections (snap votes etc.) and adds them.
  3. Drops results older than 60 days.

Needs the ANTHROPIC_API_KEY secret. Standard library only.
"""
import datetime as dt
import html as htmllib
import json, os, re, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "elections.json")
KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
MAX_UPDATES = int(os.environ.get("ELECTIONS_MAX", "6"))

EUROPE = set("AL AD AM AT AZ BY BE BA BG HR CY CZ DK EE FI FR GE DE GR HU IS IE IT XK LV LI LT LU MT MD MC ME NL MK NO PL PT RO RU SM RS SK SI ES SE CH TR UA GB VA".split())
AMERICAS = {"US", "CA", "MX", "BR", "AR"}
EAST_ASIA = {"CN", "JP", "KR", "KP", "TW", "MN", "HK", "MO"}
OCEANIA = {"AU", "NZ"}
MIDDLE_EAST = {"IR", "IL", "TR"}
NORTH_AFRICA = {"EG", "MA", "DZ", "TN", "LY", "MR", "SD"}
MAJOR = {"US", "CA", "MX", "BR", "AR", "AU", "NZ", "IR", "IL", "TR", "EG", "MA", "DZ", "TN", "JP", "KR", "TW", "FR", "DE", "GB", "IT", "ES", "PL", "UA", "RU", "TR",
         "NL", "SE", "RO", "HU", "CZ", "GR", "RS", "BG", "FI", "EE", "LV", "LT", "SK", "PT", "AT", "BE",
         "DK", "NO", "IE", "BA", "ME", "MD", "GE", "AM", "CH", "MN"}

SCHEMA = """{
 "id": "fr-2027-pres",                 // keep the same id when updating
 "country": "France", "code": "FR",    // ISO 3166-1 alpha-2
 "type": "Presidential, 1st round",    // Presidential / Parliamentary / General / Referendum ..., with round if any
 "date": "2027-04-11",                 // ISO date; if only the month is known use day 01 and approx true
 "approx": false,
 "dateNote": "",                       // short, e.g. "Runoff 25 Apr if needed" or "Due by Aug 2027; date not set"
 "status": "upcoming",                 // "upcoming" or "result" (only once the vote has happened and a result is known)
 "seats": "577 seats",                 // what is being elected, short, or ""
 "stakes": "One or two plain-English sentences (max 40 words): why it matters, neutral.",
 "contenders": [                       // 2-6 main parties or candidates, biggest first
   {"name": "National Rally", "leader": "Jordan Bardella", "short": "RN",
    "pos": 0.88,          // economic/overall left-right: 0 far left, 0.5 centre, 1 far right (standard classifications, e.g. Wikipedia, Chapel Hill Expert Survey)
    "auth": 0.85,         // 0 libertarian, 0.5 centre, 1 authoritarian (social values + attitude to checks and balances, e.g. CHES GAL-TAN)
    "posLabel": "Far right",   // Far left, Left, Centre-left, Centre, Centre-right, Right, Far right, or Big tent / Nonpartisan
    "poll": 33,           // latest polling average (%), or projected seats if polls are reported that way (say so in pollNote), or null. For results: vote %.
    "seatsWon": null,     // for results, seats won if relevant
    "incumbent": false,   // governing party / sitting office-holder
    "color": "#0d378a"}   // party's usual colour
 ],
 "pollNote": "Average of 6 polls, 28 Sep – 6 Oct 2026",   // exactly this short form (or "1 poll, <date>", "No polls yet", "Final result"); no pollster names, no explanations
 "winner": null,                       // name, only for status "result"
 "sources": ["https://..."]            // 1-3 URLs you actually used: pollsters, election authorities or news outlets -- never Wikipedia
}"""

RULES = """Rules: be factual and neutral; check everything with current sources found by web search, do not rely on memory.
Do not use or cite Wikipedia: use pollsters' own releases, official election authorities and news outlets.
Plain text only (no HTML, no markdown). Keep pos/auth placements consistent with standard classifications and
unchanged unless the party has clearly moved. Return ONLY the JSON, no commentary."""


def region(code):
    c = (code or "").upper()
    if c in EUROPE:
        return "Europe"
    if c in AMERICAS:
        return "Americas"
    if c in EAST_ASIA:
        return "East Asia"
    if c in OCEANIA:
        return "Oceania"
    if c in MIDDLE_EAST:
        return "Middle East"
    if c in NORTH_AFRICA:
        return "North Africa"
    return None


def ask(prompt, searches=5, max_tokens=4000):
    """One Claude call with the web search tool; returns the final text."""
    messages = [{"role": "user", "content": prompt}]
    for _ in range(4):   # follow 'pause_turn' continuations of long searches
        body = json.dumps({
            "model": MODEL, "max_tokens": max_tokens, "messages": messages,
            **({"tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": searches}]} if searches else {}),
        }).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=240) as r:
            out = json.loads(r.read())
        if out.get("stop_reason") == "pause_turn":
            messages.append({"role": "assistant", "content": out["content"]})
            continue
        return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
    return ""


def parse_json(txt, kind):
    """Pull the first JSON object/array out of the model's reply."""
    open_c, close_c = ("{", "}") if kind == "obj" else ("[", "]")
    i, j = txt.find(open_c), txt.rfind(close_c)
    if i < 0 or j <= i:
        return None
    s = re.sub(r"//[^\n\"]*\n", "\n", txt[i:j + 1])   # tolerate // comments copied from the schema
    try:
        return json.loads(s)
    except ValueError:
        return None


def num(v, lo=None, hi=None):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v


def clean(e, old=None):
    """Validate an entry from the model; returns a tidy dict or None."""
    if not isinstance(e, dict):
        return None
    code = str(e.get("code") or "").upper()
    if not region(code):
        return None
    try:
        dt.date.fromisoformat(str(e.get("date")))
    except ValueError:
        return None
    cons, seen = [], set()
    for c in (e.get("contenders") or [])[:8]:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        key = str(c.get("short") or c["name"]).strip().lower()
        if key in seen:              # the model sometimes lists a party twice: keep the first
            continue
        seen.add(key)
        cons.append({
            "name": str(c["name"])[:80], "leader": str(c.get("leader") or "")[:80],
            "short": str(c.get("short") or c["name"])[:24],
            "pos": num(c.get("pos"), 0, 1), "auth": num(c.get("auth"), 0, 1),
            "posLabel": str(c.get("posLabel") or "")[:24],
            "poll": num(c.get("poll"), 0), "seatsWon": num(c.get("seatsWon"), 0),
            "incumbent": bool(c.get("incumbent")),
            "color": c.get("color") if re.match(r"^#[0-9a-fA-F]{6}$", str(c.get("color") or "")) else "#8e98ab",
        })
    status = "result" if e.get("status") == "result" else "upcoming"
    out = {
        "id": (old or {}).get("id") or str(e.get("id") or "")[:40] or f"{code.lower()}-{str(e['date'])[:4]}",
        "country": str(e.get("country") or "")[:60], "code": code,
        "type": str(e.get("type") or "")[:60], "date": str(e["date"]), "approx": bool(e.get("approx")),
        "dateNote": str(e.get("dateNote") or "")[:160], "status": status,
        "seats": str(e.get("seats") or "")[:80], "stakes": str(e.get("stakes") or "")[:400],
        "contenders": cons, "pollNote": "",   # set below by code, never from model text
        "winner": (str(e["winner"])[:80] if e.get("winner") and status == "result" else None),
        "sources": [str(u) for u in (e.get("sources") or []) if str(u).startswith("http") and "wikipedia.org" not in str(u)][:3],
        "region": region(code), "major": bool((old or {}).get("major", code in MAJOR)),
    }
    if "local" in out["type"].lower():
        return None
    # Poll note: written only by code (fetch_polls.py builds "Average of N polls, <dates>").
    # Model text is never shown here, so nothing odd can appear on the card.
    if status == "result":
        out["pollNote"] = "Final result" if (old or {}).get("pollNote") != "Preliminary result" or (old or {}).get("status") == "result" else "Preliminary result"
    elif old and old.get("pollNote") and old.get("status") != "result":
        out["pollNote"] = old["pollNote"]
    else:
        out["pollNote"] = "No polls yet" if not any(c.get("poll") is not None for c in cons) else ""
    if old and not cons:            # never wipe a good candidate list with an empty one
        out["contenders"] = old.get("contenders", [])
    if old:                         # keep the fields owned by fetch_polls.py (Wikipedia polling averages)
        if old.get("polling"):
            out["polling"] = old["polling"]
        prev = {c.get("short"): c for c in old.get("contenders", [])}
        for c in out["contenders"]:
            for k in ("trend", "series"):
                if k in prev.get(c["short"], {}):
                    c[k] = prev[c["short"]][k]
            # Poll numbers belong to the poll bot (fetch_polls.py) once it has an average: never overwrite them.
            if status == "upcoming" and (old.get("polling") or {}).get("method") == "pollsters" and c["short"] in prev:
                c["poll"] = prev[c["short"]].get("poll")
    return out


def slim(e):
    """The entry without the polling machinery (config, trend, weekly series) to keep prompts short."""
    e = {k: v for k, v in e.items() if k != "polling"}
    e["contenders"] = [{k: v for k, v in c.items() if k not in ("trend", "series")} for c in e.get("contenders", [])]
    return e


def refresh(e, today, searches=2):
    prompt = (f"Today is {today.isoformat()}. Update this entry for a world-affairs site's Elections page. "
              f"Search the web for the latest on the {e['country']} {e['type']} ({e['date']}): confirm the date, "
              "the main contenders and their latest polling average (only if none is given yet); if the vote has taken place, set status "
              "\"result\" with final vote shares, seats and the winner (if a runoff is still to come, keep status "
              "\"upcoming\", update this entry with the first-round result in pollNote/dateNote).\n\n"
              f"Current entry:\n{json.dumps(slim(e), ensure_ascii=False)}\n\nReturn the updated entry as one JSON object "
              f"in this format:\n{SCHEMA}\n\n{RULES}")
    return clean(parse_json(ask(prompt, searches=searches), "obj"), old=e)


# ---------------------------------------------------------------- news triage (the cost saver)
# A full refresh costs web searches. Most weeks nothing changes, so first we read the latest headlines
# about the election for free (Bing News RSS, GDELT as backup) and ask Claude -- without web search, a
# fraction of a cent -- whether anything in them would change the card. Only then do we pay for a refresh.
UA = "Mozilla/5.0 (compatible; WarEventsElections/1.0; +https://www.warevents.com)"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def headlines(e, since_days):
    """Headlines about this election from the last few days, or None if no news source answered."""
    days = max(2, min(since_days, 14))
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    out, ok = [], False
    for q in (f"{e['country']} election", f"{e['country']} {e['type'].split(',')[0]} election"):
        try:
            xml = _get("https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": q, "format": "rss"}))
            ok = True
        except Exception:
            continue
        for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
            t = re.search(r"<title>(.*?)</title>", item, re.S)
            d = re.search(r"<pubDate>(.*?)</pubDate>", item)
            try:
                when = dt.datetime.strptime(d[1].strip(), "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc) if d else None
            except ValueError:
                when = None
            if t and (when is None or when >= cutoff):
                out.append(htmllib.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", t[1])).strip())
        time.sleep(1)
    if not ok:                                     # backup: GDELT (one request per 5 s, often busy)
        try:
            time.sleep(6)
            q = f'"{e["country"]}" election sourcelang:english'
            js = json.loads(_get("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(
                {"query": q, "mode": "artlist", "format": "json", "maxrecords": "50", "timespan": f"{days}d"})) or "{}")
            out = [a["title"] for a in js.get("articles", []) if e["country"].lower() in a.get("title", "").lower()]
            ok = True
        except Exception:
            return None
    seen, res = set(), []
    for t in out:
        if t.lower() not in seen:
            seen.add(t.lower())
            res.append(t)
    return res[:30]


def needs_refresh(e, heads):
    """Cheap check: do these headlines change anything on the card? -> (bool, reason)"""
    if not heads:
        return False, "no news"
    card = (f"{e['country']} {e['type']} on {e['date']}{' (date approximate)' if e.get('approx') else ''}. "
            "Contenders: " + "; ".join(f"{c['name']}" + (f" ({c['leader']})" if c.get("leader") else "") for c in e["contenders"])
            + f". Summary: {e.get('stakes', '')}")
    prompt = ("An elections page shows this card:\n" + card + "\n\nRecent headlines:\n- " + "\n- ".join(heads) +
              "\n\nDo any headlines mean the card is now out of date: date moved or set, election called off or called early, "
              "a main candidate/party entered, withdrew, merged or was barred, a new leader, or the summary is clearly overtaken "
              "by events? Ordinary campaigning and polls do NOT count. "
              'Return ONLY JSON: {"refresh": true or false, "why": "max 12 words"}')
    r = parse_json(ask(prompt, searches=0, max_tokens=120), "obj") or {}
    return bool(r.get("refresh")), str(r.get("why") or "")[:80]


# ---------------------------------------------------------------- ElectionGuide (IFES) calendar
# electionguide.org lists every national election in the next six months with its date and whether it's
# confirmed. The bot reads it every run (free, no Claude) to spot new and snap elections and confirmed dates.
EG_URL = "https://www.electionguide.org/elections/type/upcoming/"
EG_NAMES = {
    "Albania": "AL", "Andorra": "AD", "Armenia": "AM", "Austria": "AT", "Azerbaijan": "AZ", "Belarus": "BY",
    "Belgium": "BE", "Bosnia and Herzegovina": "BA", "Bulgaria": "BG", "Croatia": "HR", "Cyprus": "CY",
    "Czech Republic": "CZ", "Czechia": "CZ", "Denmark": "DK", "Estonia": "EE", "Finland": "FI", "France": "FR",
    "Georgia": "GE", "Germany": "DE", "Greece": "GR", "Hungary": "HU", "Iceland": "IS", "Ireland": "IE",
    "Italy": "IT", "Kosovo": "XK", "Latvia": "LV", "Liechtenstein": "LI", "Lithuania": "LT", "Luxembourg": "LU",
    "Malta": "MT", "Moldova": "MD", "Moldova, Republic of": "MD", "Monaco": "MC", "Montenegro": "ME",
    "Netherlands": "NL", "North Macedonia": "MK", "Macedonia": "MK", "Norway": "NO", "Poland": "PL",
    "Portugal": "PT", "Romania": "RO", "Russia": "RU", "Russian Federation": "RU", "San Marino": "SM",
    "Serbia": "RS", "Slovakia": "SK", "Slovenia": "SI", "Spain": "ES", "Sweden": "SE", "Switzerland": "CH",
    "Turkey": "TR", "Türkiye": "TR", "Turkiye": "TR", "Ukraine": "UA", "United Kingdom": "GB",
    "United States of America": "US", "United States": "US", "Canada": "CA", "Mexico": "MX", "Brazil": "BR",
    "Argentina": "AR", "China": "CN", "Japan": "JP", "Korea, Republic of": "KR", "South Korea": "KR",
    "Korea, Democratic People's Republic of": "KP", "North Korea": "KP", "Taiwan": "TW", "Mongolia": "MN",
    "Australia": "AU", "New Zealand": "NZ", "Iran": "IR", "Iran, Islamic Republic of": "IR", "Israel": "IL",
    "Egypt": "EG", "Morocco": "MA", "Algeria": "DZ", "Tunisia": "TN", "Libya": "LY", "Mauritania": "MR", "Sudan": "SD",
}
EG_SKIP = re.compile(r"senate|council of states|upper house|bundesrat|national council of provinces|governor|"
                     r"regional|municipal|local|provincial|state |mayor", re.I)


def electionguide(today):
    """[{code, country, name, date, confirmed}] for in-scope national votes, one per country and date."""
    req = urllib.request.Request(EG_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; WarEventsElections/1.0)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        page = r.read().decode("utf-8", "replace")
    rows = re.findall(r'<strong>\s*([A-Z][a-z]{2} \d{1,2} \d{4})\s*</strong>\s*<small>\((\w)\)</small>.*?'
                      r'<a href="/elections/id/\d+/">([^<]+)</a>\s*<br>\s*<a href="/countries/id/\d+/">([^<]+)</a>',
                      page, re.S)
    out = {}
    for d, flag, name, country in rows:
        name, country = htmllib.unescape(name).strip(), htmllib.unescape(country).strip()
        code = EG_NAMES.get(country)
        try:
            day = dt.datetime.strptime(d, "%b %d %Y").date()
        except ValueError:
            continue
        if not code or not region(code) or day < today or EG_SKIP.search(name):
            continue
        k = (code, day)
        if k in out:
            out[k]["name"] += " + " + name
        else:
            out[k] = {"code": code, "country": country, "name": name, "date": day.isoformat(), "confirmed": flag == "d"}
    return list(out.values())


def build(item, today):
    """Create a full entry for one election ElectionGuide lists and we don't have yet."""
    prompt = (f"Today is {today.isoformat()}. Create an entry for a world-affairs site's Elections page for this national "
              f"vote: {item['country']}, {item['name']}, on {item['date']}"
              f"{'' if item['confirmed'] else ' (date not yet confirmed)'}. Search the web for the main contenders and "
              f"the latest polls. Return ONE JSON object in this format:\n{SCHEMA}\n\n{RULES}")
    e = clean(parse_json(ask(prompt, searches=5), "obj"))
    if e:
        e["date"], e["approx"] = item["date"], not item["confirmed"]
    return e


def discover(items, today):
    known = "; ".join(f"{e['country']} {e['type']} {e['date']}" for e in items)
    until = (today + dt.timedelta(days=460)).isoformat()
    prompt = (f"Today is {today.isoformat()}. List NATIONAL elections and national referendums in Europe, North America "
              "(United States, Canada, Mexico only), Brazil, Argentina, East Asia (China, Japan, North and South Korea, Taiwan, "
              "Mongolia), Australia, New Zealand, Iran, Israel, Turkey, Egypt and North Africa (Morocco, Algeria, Tunisia, Libya, Mauritania, Sudan) "
              f"scheduled or legally due between today and {until} that are NOT already in this list: {known}. "
              "Include newly called snap elections. No local, regional or indirect (parliament-chosen) votes. "
              "If there are none, return []. Otherwise return a JSON array of entries in this format:\n"
              f"{SCHEMA}\n\n{RULES}")
    arr = parse_json(ask(prompt, searches=8, max_tokens=8000), "arr") or []
    new = []
    for raw in arr:
        e = clean(raw)
        if not e:
            continue
        d = dt.date.fromisoformat(e["date"])
        dup = any(x["code"] == e["code"] and abs((dt.date.fromisoformat(x["date"]) - d).days) < 75 for x in items + new)
        if not dup:
            new.append(e)
    return new


def main():
    if not KEY:
        print("ANTHROPIC_API_KEY not set; skipping elections")
        return
    data = json.load(open(DATA, encoding="utf-8"))
    items = data.get("elections", [])
    today = dt.date.today()

    for n, e in enumerate(items):     # older entries: their last check was a full refresh; never-checked
        if not e.get("refreshed"):     # ones are spread over 6 weeks so they don't all refresh at once
            e["refreshed"] = e.get("checked") or (today - dt.timedelta(days=7 * (n % 6))).isoformat()

    def since(e, k):
        return (today - dt.date.fromisoformat(e.get(k) or "2000-01-01")).days

    def plan(e):
        """-> (order, kind, searches). kind 'full' = paid refresh, 'triage' = free headlines + tiny check first."""
        d = dt.date.fromisoformat(e["date"])
        to_vote = (d - today).days
        if e["status"] == "upcoming" and d <= today and since(e, "checked") >= 1:
            return (0, d), "full", 4            # vote happened: get the result (worth the searches)
        if e["status"] == "result" and (today - d).days <= 10 and since(e, "checked") >= 3:
            return (3, d), "full", 2            # firm up a fresh result for a few days
        if e["status"] != "upcoming":
            return None
        if to_vote <= 7 and since(e, "checked") >= 1:
            # final week: daily check; one full refresh guaranteed in the last week
            return (1, d), ("full" if since(e, "refreshed") > 7 else "triage"), 2
        if since(e, "checked") >= 7:
            # otherwise weekly; full refresh anyway every 6 weeks (every 3 if the vote is within 2 months)
            every = 21 if to_vote <= 60 else 42
            return (2, d), ("full" if since(e, "refreshed") >= every else "triage"), 2
        return None

    todo = sorted((p[0], i, p[1], p[2]) for i, e in enumerate(items) for p in [plan(e)] if p)
    changed = full = 0
    for _, i, kind, searches in todo:
        e = items[i]
        if kind == "triage":
            heads = headlines(e, since(e, "checked"))
            if heads is None:                 # news source down: only refresh if it's been a while
                kind = "full" if since(e, "refreshed") >= 14 else "skip"
                why = "news unavailable"
            else:
                try:
                    go, why = needs_refresh(e, heads)
                except Exception as ex:
                    go, why = False, f"check failed ({str(ex)[:40]})"
                kind = "full" if go else "skip"
            print(f"{e['id']}: {len(heads or [])} headlines -> {'refresh' if kind == 'full' else 'no change'} ({why})")
            if kind == "skip":
                e["checked"] = today.isoformat()
                continue
        if full >= MAX_UPDATES:
            print("refresh next run:", e["id"])
            continue
        try:
            new = refresh(e, today, searches)
            full += 1
        except Exception as ex:   # network / API errors: try again next run
            print("failed", e["id"], ex)
            time.sleep(3)
            continue
        if new:
            new["checked"] = new["refreshed"] = today.isoformat()
            items[i] = new
            changed += 1
            print("updated", e["id"], f"({searches} searches)")
        time.sleep(1)

    # 1) ElectionGuide calendar (every run, free): add missing national votes, firm up dates.
    eg_ok = False
    try:
        cal = electionguide(today)
        eg_ok = bool(cal)
        print(f"ElectionGuide: {len(cal)} national votes in scope in the next six months")
        added = 0
        for it in cal:
            d = dt.date.fromisoformat(it["date"])
            mine = [x for x in items if x["code"] == it["code"] and x["status"] == "upcoming"
                    and abs((dt.date.fromisoformat(x["date"]) - d).days) < 75]
            if mine:
                x = min(mine, key=lambda x: abs((dt.date.fromisoformat(x["date"]) - d).days))
                if x.get("approx") and it["confirmed"] and x["date"] != it["date"]:
                    print(f"date confirmed {x['id']}: {x['date']} -> {it['date']}")
                    x["date"], x["approx"] = it["date"], False
                continue
            if any(x["code"] == it["code"] and abs((dt.date.fromisoformat(x["date"]) - d).days) < 75 for x in items):
                continue                       # e.g. a runoff of a vote we already show as a result
            if added >= 3:                     # a few new ones per run keeps the cost down
                print("to add next run:", it["country"], it["name"], it["date"])
                continue
            try:
                e = build(it, today)
            except Exception as ex:
                print("could not build", it["country"], it["name"], ex)
                continue
            if e:
                e["checked"] = e["refreshed"] = today.isoformat()
                items.append(e)
                added += 1
                print("added", e["id"], "(from ElectionGuide)")
    except Exception as ex:
        print("ElectionGuide unavailable:", str(ex)[:120])

    # 2) Votes further than six months out: an open web search, monthly (weekly if ElectionGuide is down).
    every = 30 if eg_ok else 7
    if (today - dt.date.fromisoformat(data.get("discovered", "2000-01-01"))).days >= every:
        try:
            new = discover(items, today)
            for e in new:
                e["checked"] = e["refreshed"] = today.isoformat()
                print("added", e["id"])
            items += new
            data["discovered"] = today.isoformat()
        except Exception as ex:
            print("discovery failed", ex)

    # tidy: in-scope only, results kept for 60 days, sorted by date (key votes first on a tie)
    items = [e for e in items if region(e.get("code")) and not (
        e["status"] == "result" and (today - dt.date.fromisoformat(e["date"])).days > 60)]
    for e in items:
        e["region"] = region(e["code"])
    items.sort(key=lambda e: (e["date"], not e.get("major")))
    data["elections"] = items
    data["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"elections: {changed} updated ({full} paid refreshes), {len(items)} total")


if __name__ == "__main__":
    main()
