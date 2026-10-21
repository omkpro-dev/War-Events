"""Claude review of the Logistics view (data/logistics.json): statuses, notes and sources.

  python news-feed/review_logistics.py --weekly    one pass over every layer (Mondays)
  python news-feed/review_logistics.py --outages   check strong new IODA outages found by
                                                   logistics_numbers.py (no-op when there are none)

Claude checks current sources with web search and may only PROPOSE changes; this script applies
the ones that pass the rules below and logs every change in "reviewLog":
  * existing items only (plus new cable incidents and confirmed shutdowns); map lines -- lanes,
    cables and pipeline paths, coordinates -- are never touched
  * statuses must be one of the values the map already knows
  * a status/level change needs 2+ sources from different outlets; other edits need 1+
  * no Wikipedia, plain text, short notes
Needs the ANTHROPIC_API_KEY secret. Standard library only.
"""
import datetime as dt
import json, os, re, sys, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from update_elections import KEY, MODEL, ask, parse_json   # same Claude + web search call as the Elections bot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "logistics.json")
SEARCHES = int(os.environ.get("LOGISTICS_SEARCHES", "6"))
NOTE_WORDS = 60
LOG_KEEP = 80
# Sources the review never accepts: SEO/AI content farms, aggregators and social posts. Add more as they turn up.
BLOCKED = {"wikipedia.org", "referently.com", "niftytrader.in", "aihorizonnetwork.com", "tech-insider.org", "technology.org",
           "medium.com", "blogspot.com", "quora.com", "reddit.com", "facebook.com", "x.com", "twitter.com", "youtube.com",
           "tiktok.com", "linkedin.com", "scribd.com"}

# layer -> (status field, allowed values, other editable fields, what one item is)
LAYERS = {
    "chokepoints": ("status", ["open", "disrupted", "closed"], ["since", "latest", "note"], "a shipping chokepoint"),
    "lanes": ("status", ["open", "disrupted", "diverted", "closed", "sanctioned"], ["note"], "a main sea route"),
    "cableIncidents": ("status", ["at risk", "damaged", "cut", "repaired"], ["date", "note"], "an undersea cable incident"),
    "pipelines": ("status", ["operating", "reduced", "damaged", "halted"], ["note"], "an oil or gas pipeline"),
    "lng": ("status", ["operating", "reduced", "halted"], ["note"], "an LNG export terminal"),
    "sanctions": ("level", ["targeted", "sectoral", "comprehensive"], ["by", "note"], "sanctions on a country"),
    "exportControls": (None, [], ["note"], "an export control"),
    "starlink": ("status", ["licensed", "restricted", "unlicensed use", "banned"], ["note"], "Starlink's status in a country"),
    "blackouts": (None, [], ["since", "note"], "a country with internet shutdowns or heavy filtering"),
}
KEY_OF = lambda layer: "cc" if layer in ("sanctions", "starlink", "blackouts") else ("name" if layer == "lng" else "id")
SLIM_SKIP = {"path", "via", "lat", "lng", "km", "counts", "iodaAt"}

def rules(today, status, key, add):
    return (f"Rules:\n"
            f"- Check every item against CURRENT sources found with web search; do not rely on memory. Today is {today}.\n"
            "- Only propose a change when something has actually changed or the text is now wrong or out of date. Most items need no change.\n"
            "- Never cite Wikipedia, social media, blogs, SEO/AI content sites or aggregators. Use established news outlets, official bodies, "
            "shipping/insurance/telecoms trackers. Only cite pages you actually opened.\n"
            f"- Plain text, no HTML or markdown. Notes: at most {NOTE_WORDS} words, neutral, same style as the existing notes, with dates.\n"
            f'- A change of "{status}" needs at least two independent outlets agreeing.\n'
            'Return ONLY JSON: {"changes": [{"key": "<the item\'s ' + key + '>", "field": "<field>", "value": "<new value>", '
            '"why": "<10 words>", "sources": ["https://..."]}]' + add + "}")


def domain(u):
    d = urllib.parse.urlparse(u).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def blocked(u):
    d = domain(u)
    return any(d == b or d.endswith("." + b) for b in BLOCKED)


def good_sources(srcs):
    out = []
    for u in srcs or []:
        if isinstance(u, str) and re.match(r"https?://[^\s]+$", u) and not blocked(u) and u not in out:
            out.append(u)
    return out


def clean_text(v):
    v = re.sub(r"<[^>]+>|[*_`#]", "", str(v or "")).strip()
    return " ".join(v.split()[:NOTE_WORDS])


def iso_date(v):
    try:
        return dt.date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        return None


def slim(item):
    return {k: v for k, v in item.items() if k not in SLIM_SKIP}


def apply_change(layer, items, ch, log, today):
    st, allowed, fields, _ = LAYERS[layer]
    key = KEY_OF(layer)
    it = next((i for i in items if str(i.get(key)) == str(ch.get("key"))), None)
    field, srcs = ch.get("field"), good_sources(ch.get("sources"))
    if not it or field not in ([st] if st else []) + fields or not srcs:
        return print("  rejected (unknown item/field or no sources):", ch)
    val = ch.get("value")
    if field == st:
        val = str(val).strip().lower()
        if val not in allowed:
            return print("  rejected (status not allowed):", ch)
        if len({domain(u) for u in srcs}) < 2:
            return print("  rejected (status change needs 2 outlets):", ch)
    elif field in ("since", "date"):
        val = iso_date(val)
    elif field == "by":
        val = [s.strip().upper() for s in (val if isinstance(val, list) else str(val).split(",")) if s.strip()][:8]
    else:
        val = clean_text(val)
    if not val or val == it.get(field):
        return
    log.append({"at": today, "layer": layer, "item": it.get(key), "field": field, "old": it.get(field), "new": val,
                "why": clean_text(ch.get("why"))[:120], "sources": srcs[:4]})
    it[field] = val
    it["sources"] = (srcs + [u for u in it.get("sources", []) if u not in srcs])[:4]
    print("  changed", layer, it.get(key), field, "->", val if field != "note" else val[:60] + "...")


def add_cable(items, a, log, today):
    srcs = good_sources(a.get("sources"))
    try:
        lat, lng = float(a["lat"]), float(a["lng"])
    except (KeyError, TypeError, ValueError):
        return print("  rejected new cable incident (no position):", a)
    status = str(a.get("status", "")).lower()
    if status not in LAYERS["cableIncidents"][1] or len({domain(u) for u in srcs}) < 2 or not a.get("name"):
        return print("  rejected new cable incident (status/sources/name):", a)
    iid = re.sub(r"[^a-z0-9]+", "-", str(a["name"]).lower()).strip("-")[:40]
    if any(i.get("id") == iid for i in items):
        return
    item = {"id": iid, "name": clean_text(a["name"])[:120], "status": status, "date": iso_date(a.get("date")) or today,
            "lat": round(lat, 2), "lng": round(lng, 2), "note": clean_text(a.get("note")), "sources": srcs[:4]}
    items.append(item)
    log.append({"at": today, "layer": "cableIncidents", "item": iid, "field": "added", "old": None, "new": item["name"], "sources": srcs[:4]})
    print("  added cable incident", iid)


def review_layer(data, layer, today, log):
    st, allowed, fields, what = LAYERS[layer]
    items = data.get(layer, [])
    if not items:
        return True
    key = KEY_OF(layer)
    editable = ([f'"{st}" (one of: {", ".join(allowed)})'] if st else []) + [f'"{f}"' + (" (YYYY-MM-DD)" if f in ("since", "date") else "") for f in fields]
    add = ""
    if layer == "cableIncidents":
        add = ', "add": [{"name": "...", "status": "cut|damaged|at risk", "date": "YYYY-MM-DD", "lat": 0.0, "lng": 0.0, "note": "...", "sources": ["https://...", "https://..."]}]'
    extra = "\nAlso list NEW cable cuts or damage since the latest date above under \"add\" (two outlets each, position of the damage)." if add else ""
    if layer == "chokepoints":
        extra = "\n\"traffic\" is measured daily by IMF PortWatch and updated by code: use it, never change it. \"latest\" is the editorial line beside it: the newest notable event (an attack, a rule change, a reopening), never ship counts."
    prompt = (f"You keep a world logistics map current. Each item below is {what}. Today is {today}.\n"
              f"Editable fields: {', '.join(editable)}. Do not touch anything else.{extra}\n\n"
              f"ITEMS:\n{json.dumps([slim(i) for i in items], ensure_ascii=False)}\n\n"
              + rules(today, st or "status", key, add))
    print(layer, f"({len(items)} items)")
    try:
        out = parse_json(ask(prompt, searches=SEARCHES, max_tokens=6000), "obj") or {}
    except Exception as e:
        print("  claude failed:", e)
        return False
    for ch in out.get("changes") or []:
        apply_change(layer, items, ch, log, today)
    for a in (out.get("add") or []) if layer == "cableIncidents" else []:
        add_cable(items, a, log, today)
    return True


def check_outages(data, today, log):
    sig = data.setdefault("signals", {})
    checked = set(sig.get("checked", []))
    todo = [o for o in sig.get("outages", []) if f"{o['cc']}@{o['since'][:10]}" not in checked]
    for o in todo:
        checked.add(f"{o['cc']}@{o['since'][:10]}")
        prompt = (f"IODA (Georgia Tech) is measuring a major national internet outage in the country with ISO code {o['cc']} "
                  f"since {o['since']} ({o['hours']} hours so far). Today is {today}. Use web search to find out why.\n"
                  "It belongs on a map of internet SHUTDOWNS only if a government or armed group ordered or caused it, or it is "
                  "conflict damage (strikes, sabotage). Power cuts, storms, earthquakes and accidental cable faults do NOT count.\n"
                  'Return ONLY JSON: {"shutdown": true|false, "country": "<English name>", "note": "<at most 40 words, plain text, with dates>", '
                  '"sources": ["https://..."]}  -- news sources you opened; at least one if shutdown is true. Never Wikipedia.')
        try:
            r = parse_json(ask(prompt, searches=4, max_tokens=2000), "obj") or {}
        except Exception as e:
            print("  claude failed:", e)
            continue
        srcs = good_sources(r.get("sources"))
        if r.get("shutdown") is True and srcs and r.get("country") and not any(b["cc"] == o["cc"] for b in data["blackouts"]):
            data["blackouts"].append({"cc": o["cc"], "country": clean_text(r["country"])[:60], "since": o["since"][:10],
                                      "note": clean_text(r.get("note")), "sources": (srcs + [o["source"]])[:4], "auto": True})
            log.append({"at": today, "layer": "blackouts", "item": o["cc"], "field": "added", "old": None,
                        "new": clean_text(r.get("note")), "sources": srcs[:4]})
            print("  added shutdown", o["cc"])
        else:
            print("  not a shutdown:", o["cc"], clean_text(r.get("note"))[:80])
    sig["checked"] = sorted(checked)[-60:]
    return len(todo)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--weekly"
    path = sys.argv[2] if len(sys.argv) > 2 else DATA
    if not KEY:
        print("ANTHROPIC_API_KEY not set; skipping review")
        return
    data = json.load(open(path, encoding="utf-8"))
    today, log = dt.date.today().isoformat(), []
    for layer in LAYERS:   # drop sources that are on the block list (also ones cited before it existed)
        for it in data.get(layer, []):
            if it.get("sources"):
                it["sources"] = [u for u in it["sources"] if not blocked(u)]
    if mode == "--outages":
        if not check_outages(data, today, log):
            print("no new outages to check")
    else:
        done = [review_layer(data, layer, today, log) for layer in LAYERS]
        if all(done):   # "as of" only moves forward when every layer was really checked
            data["asOf"] = data["updated"] = today
        data["reviewedAt"], data["reviewModel"] = today, MODEL
    data["reviewLog"] = (log + data.get("reviewLog", []))[:LOG_KEEP]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    json.load(open(tmp, encoding="utf-8"))
    os.replace(tmp, path)
    print("changes this run:", len(log))


if __name__ == "__main__":
    main()
