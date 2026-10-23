"""Topic feeds for the Logistics and Disasters globes (standard library only).

Reads specialist outlets plus a few general ones, keeps ONLY items about the topic: a strict keyword
match first (in the headline for general outlets), then a cheap yes/no check by Claude Haiku on each
NEW headline (answers are cached, so every headline is judged once). Without ANTHROPIC_API_KEY the
keyword match alone decides. Drops duplicates, newest first.
For Logistics it also judges the site's own Key Developments headlines (storyIds), so the stories
panel on the Logistics globe only shows logistics stories.
Writes logistics_feed.json and disasters_feed.json into the folder given as the first argument.
"""
import datetime as dt, html as htmllib, json, os, re, sys, time, urllib.request
from email.utils import parsedate_to_datetime
import usage   # prints this run's token use and cost to the log

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
UA = "Mozilla/5.0 (compatible; WarEventsTopics/1.0; +https://www.warevents.com)"
KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
KEYDEV_URL = "https://raw.githubusercontent.com/omkpro-dev/War-Events/news-data/key_developments.json"
TOPICS = {
 "logistics": ("the geopolitics of logistics: shipping lanes and chokepoints (straits, canals), attacks on or seizures of ships, "
               "blockades, sanctions and shadow fleets, export controls and tariffs that change trade, flows of oil, gas, LNG and grain, "
               "pipelines, undersea data cables, satellite internet such as Starlink, and supply chains disrupted by conflict or politics. "
               "NOT: routine company or market news, earnings, ship deliveries, technology or green-fuel features, crew and safety topics "
               "without a geopolitical angle, or politics that does not affect how goods, energy or data move."),
 "disasters": ("natural hazards and their impact: earthquakes, tsunamis, tropical storms, floods, droughts, heatwaves, wildfires, "
               "volcanoes, landslides, avalanches, extreme weather, air pollution, and climate / CO2 news. "
               "NOT: war, politics, crime, or man-made accidents that were not caused by a natural hazard."),
}
NOW = dt.datetime.now(dt.timezone.utc)
MAX_AGE_H = 96
DIS_MAX_AGE_H = 72   # disaster news older than this is no longer current and drops off

# (outlet, url, specialist?)  specialist = the outlet only covers this topic, so the summary may carry the match
LOGI_FEEDS = [
 ("gCaptain", "https://gcaptain.com/feed/", True), ("Splash247", "https://splash247.com/feed/", True),
 ("Hellenic Shipping News", "https://www.hellenicshippingnews.com/feed/", True), ("FreightWaves", "https://www.freightwaves.com/news/feed", True),
 ("The Loadstar", "https://theloadstar.com/feed/", True), ("Offshore Energy", "https://www.offshore-energy.biz/feed/", True),
 ("SubTel Forum", "https://subtelforum.com/feed/", True), ("Safety4Sea", "https://safety4sea.com/feed/", True),
 ("OilPrice.com", "https://oilprice.com/rss/main", True),
 ("BBC", "https://feeds.bbci.co.uk/news/business/rss.xml", False), ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", False),
]
DIS_FEEDS = [
 ("ReliefWeb", "https://reliefweb.int/updates/rss.xml", True), ("The Watchers", "https://watchers.news/feed/", True),
 ("Severe Weather Europe", "https://www.severe-weather.eu/feed/", True), ("NASA Earth Observatory", "https://earthobservatory.nasa.gov/feeds/natural-hazards.rss", True),
 ("Carbon Brief", "https://www.carbonbrief.org/feed", True), ("The Guardian", "https://www.theguardian.com/world/natural-disasters/rss", True),
 ("The Guardian", "https://www.theguardian.com/environment/rss", False), ("BBC", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", False),
 ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", False),
]
LOGI_RE = re.compile(r"\b(ship|ships|shipping|shipowner|shipyard|tanker|tankers|vessel|vessels|cargo|freight|container|containers|boxship|port|ports|"
    r"strait|straits|hormuz|red sea|bab[ -]el[ -]mandeb|bab al-mandab|suez|panama canal|malacca|bosporus|chokepoint|blockade|maritime|seafarers?|"
    r"supply chains?|logistics|sanction|sanctions|sanctioned|embargo|tariffs?|export controls?|rare earths?|semiconductors?|chips? exports?|"
    r"pipeline|pipelines|lng|crude|oil (price|exports?|imports?|supply|tanker)|opec|brent|refiner(y|ies)|fuel (supply|shortage)|"
    r"(undersea|subsea|submarine) cables?|cable (cut|damage|repair)|internet (outage|shutdown|blackout)|starlink|shadow fleet|war risk|"
    r"insurance premiums?|rerout\w*|diversion|cape of good hope|grain (exports?|corridor|deal)|airspace|air cargo|rail freight|trucking)\b", re.I)
DIS_RE = re.compile(r"\b(earthquakes?|quakes?|aftershocks?|tsunamis?|hurricanes?|typhoons?|cyclones?|tropical (storm|depression)|storm surge|"
    r"floods?|flooding|flash floods?|landslides?|mudslides?|droughts?|heatwaves?|heat wave|extreme heat|wildfires?|bushfires?|forest fires?|"
    r"volcano(es)?|volcanic|eruptions?|erupts?|lava|ash cloud|avalanches?|tornado(es)?|monsoon|blizzards?|hailstorm|natural disasters?|"
    r"disaster (relief|response|zone)|air quality|air pollution|smog|pm2\.5|co2|carbon dioxide|emissions|climate change|el ni(n|ñ)o|la ni(n|ñ)a|"
    r"famine|cholera outbreak|evacuat\w+ (as|after|ahead of) (the )?(storm|flood|fire|eruption|hurricane|typhoon|cyclone))\b", re.I)
# Logistics must be the geopolitical kind: either a headline word that is geopolitical on its own, or a
# shipping / supply word together with a conflict, sanctions or country word.
LOGI_STRONG = re.compile(r"\b(sanction\w*|embargo|blockade|hormuz|red sea|bab[ -]el[ -]mandeb|bab al-mandab|suez|panama canal|malacca|bosporus|"
    r"strait of|chokepoints?|shadow fleet|houthis?|piracy|pirates|seized? (tanker|vessel|ship)|export controls?|rare earths?|tariffs?|"
    r"(undersea|subsea|submarine) cables?|cable (cut|damage)|starlink|war risk|opec\+?|pipeline|nord stream|druzhba|turkstream|"
    r"cape of good hope|rerout\w*|grain corridor|price cap|oil (exports?|imports?|supply|price)|lng (exports?|imports?|supply|cargoes?)|"
    r"gas (supply|exports?|imports?)|fuel shortages?|supply chains?)\b", re.I)
LOGI_GEO = re.compile(r"\b(war|attack\w*|strike[sd]?|drones?|missiles?|navy|naval|military|conflict|ceasefire|iran\w*|russia\w*|china|chinese|"
    r"ukrain\w*|israel\w*|yemen\w*|gaza|taiwan\w*|venezuel\w*|north korea\w*|trump|eu\b|nato|g7|beijing|moscow|tehran|washington)\b", re.I)
# general-outlet headlines that match a word but are about war or politics, not the topic
NOT_LOGI = re.compile(r"\b(storm shadow|missile strike on|election)\b", re.I)
NOT_DIS = re.compile(r"\b(storm shadow|political storm|firestorm of criticism|ceasefire|fire(d)? (at|on) (protesters|troops))\b", re.I)

CC = [(r"\bukrain", "UA"), (r"\brussia", "RU"), (r"\bchina|chinese|beijing", "CN"), (r"\bindia\b|indian\b", "IN"), (r"\biran", "IR"), (r"\bisrael", "IL"),
      (r"\byemen|houthi", "YE"), (r"\bsaudi", "SA"), (r"\bqatar", "QA"), (r"\buae\b|emirat|dubai|fujairah", "AE"), (r"\boman\b", "OM"), (r"\begypt|suez", "EG"),
      (r"\bturk(ey|iye|ish)|bosporus", "TR"), (r"\bjapan", "JP"), (r"\bkorea", "KR"), (r"\btaiwan", "TW"), (r"\bphilippin", "PH"), (r"\bindonesia", "ID"),
      (r"\bvietnam", "VN"), (r"\bmalaysia", "MY"), (r"\bsingapore", "SG"), (r"\bthailand", "TH"), (r"\bbangladesh", "BD"), (r"\bpakistan", "PK"),
      (r"\baustralia", "AU"), (r"\bnew zealand", "NZ"), (r"\bmexic", "MX"), (r"\bbrazil", "BR"), (r"\bargentin", "AR"), (r"\bchile", "CL"), (r"\bperu\b", "PE"),
      (r"\bcanada|canadian", "CA"), (r"\b(u\.s\.|united states|american|us\b)", "US"), (r"\bpanama", "PA"), (r"\bvenezuela", "VE"), (r"\bcuba", "CU"),
      (r"\bhaiti", "HT"), (r"\b(uk|britain|british|england|scotland)\b", "GB"), (r"\bfrance|french", "FR"), (r"\bgerman", "DE"), (r"\bital(y|ian)", "IT"),
      (r"\bspain|spanish", "ES"), (r"\bgreece|greek", "GR"), (r"\bnorway|norwegian", "NO"), (r"\bdenmark|danish", "DK"), (r"\bfinland|finnish", "FI"),
      (r"\bsweden|swedish", "SE"), (r"\bpoland|polish", "PL"), (r"\bnetherlands|dutch|rotterdam", "NL"), (r"\bnigeria", "NG"), (r"\bkenya", "KE"),
      (r"\bethiopia", "ET"), (r"\bsomalia", "SO"), (r"\bsudan", "SD"), (r"\bsouth africa", "ZA"), (r"\bmorocco", "MA"), (r"\balgeria", "DZ"), (r"\blibya", "LY"),
      (r"\biraq", "IQ"), (r"\bsyria", "SY"), (r"\blebanon", "LB"), (r"\bafghan", "AF"), (r"\bnepal", "NP"), (r"\bmyanmar", "MM"), (r"\bmozambique", "MZ"),
      (r"\bmadagascar", "MG"), (r"\bvanuatu", "VU"), (r"\bfiji", "FJ"), (r"\bguam\b", "GU"), (r"\bkazakh", "KZ"), (r"\bazerbaijan", "AZ"), (r"\bgeorgia\b", "GE"),
      (r"\bvenezuel", "VE"), (r"\bcolombia", "CO"), (r"\bguatemala", "GT"), (r"\bhonduras", "HN"), (r"\bnicaragua", "NI"), (r"\bel salvador", "SV")]


def get(url):
    for i in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read(5_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
        except Exception:
            if i:
                raise
            time.sleep(3)


def tag(s, name):
    m = re.search(r"<" + name + r"(?:\s[^>]*)?>(.*?)</" + name + ">", s, re.S)
    return htmllib.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""


def clean(s):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def when(s):
    try:
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        try:
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None


def collect(feeds, rx, bad):
    out, seen = [], set()
    for outlet, url, special in feeds:
        try:
            xml = get(url)
        except Exception as ex:
            print(f"  {outlet}: could not read ({str(ex)[:60]})")
            continue
        n = 0
        for it in re.findall(r"<item[\s>].*?</item>|<entry[\s>].*?</entry>", xml, re.S):
            title = clean(tag(it, "title"))
            link = tag(it, "link") or (re.search(r'<link[^>]+href="([^"]+)"', it) or [None, ""])[1]
            summ = clean(tag(it, "description") or tag(it, "summary") or tag(it, "content"))[:420]
            d = when(tag(it, "pubDate") or tag(it, "published") or tag(it, "updated") or tag(it, "dc:date"))
            if not title or not link or not d or (NOW - d).total_seconds() > MAX_AGE_H * 3600:
                continue
            text = title if not special else title + " " + summ[:200]
            if not rx.search(text) or bad.search(title):
                continue
            if rx is LOGI_RE and not (LOGI_STRONG.search(title) or (LOGI_RE.search(title) and LOGI_GEO.search(title))):
                continue
            key = re.sub(r"[^a-z0-9]", "", title.lower())[:70]
            if key in seen:
                continue
            seen.add(key)
            cc = []
            for p, c in CC:
                if re.search(p, title, re.I) and c not in cc:
                    cc.append(c)
            out.append({"outlet": outlet, "title": title, "summary": summ, "url": link.strip(), "publishedAt": d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "cc": cc[:4]})
            n += 1
        print(f"  {outlet}: {n} on topic")
    out.sort(key=lambda x: x["publishedAt"], reverse=True)
    return out[:80]


def ai_keep(items, topic, cache, text=lambda i: i["title"]):
    """Ask Claude (no web search) which NEW headlines are really on topic; cached answers are reused."""
    def k(i):
        return re.sub(r"[^a-z0-9]", "", text(i).lower())[:90]
    new = [i for i in items if k(i) not in cache]
    if new and KEY:
        for start in range(0, len(new), 60):
            batch = new[start:start + 60]
            lst = "\n".join(f"{n}. {text(i)}" + (f" ({i['outlet']})" if i.get("outlet") else "") for n, i in enumerate(batch))
            prompt = (f"A news site has a page only about {TOPICS[topic]}\n\nWhich of these headlines belong on that page?\n{lst}\n\n"
                      "Return ONLY a JSON array of the numbers that belong, e.g. [0, 3]. Return [] if none.")
            try:
                body = json.dumps({"model": MODEL, "max_tokens": 400, "messages": [{"role": "user", "content": prompt}]}).encode()
                req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
                    "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
                with urllib.request.urlopen(req, timeout=90) as r:
                    out = json.loads(r.read())
                    usage.record(out)
                txt = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
                m = re.search(r"\[[\d,\s]*\]", txt)
                ok = set(json.loads(m.group(0))) if m else None
            except Exception as ex:
                print(f"  AI check failed ({str(ex)[:60]}); keyword match decides for now")
                ok = None
            if ok is None:
                continue
            for n, i in enumerate(batch):
                cache[k(i)] = n in ok
        print(f"  AI check ({topic}): {sum(1 for i in new if cache.get(k(i)))} of {len(new)} new headlines kept")
    elif new:
        print(f"  no ANTHROPIC_API_KEY: keyword match only for {len(new)} new headlines")
    return [i for i in items if cache.get(k(i), True)]


def key_dev_ids(cache):
    """Ids of the site's Key Developments that are logistics stories (for the Logistics stories panel)."""
    try:
        devs = json.loads(get(KEYDEV_URL))
    except Exception as ex:
        print("  Key Developments unavailable:", str(ex)[:60])
        return None
    # with the AI check, look wider (the AI throws out what isn't logistics); without it, headline keywords only
    cand = [d for d in devs if d.get("headline") and (LOGI_STRONG.search(d["headline"]) or (KEY and LOGI_RE.search(d["headline"] + " " + str(d.get("body", ""))[:300])))]
    kept = ai_keep(cand, "logistics", cache, text=lambda d: d["headline"])
    print(f"  Key Developments: {len(kept)} logistics stories of {len(devs)}")
    return [d.get("id") for d in kept if d.get("id") is not None]


def save(name, items, extra=None, allow_empty=False):
    path = os.path.join(OUT, name)
    if not items and os.path.exists(path) and not allow_empty:
        print(f"{name}: nothing new, keeping previous file")
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dict({"updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "items": items}, **(extra or {})), f, ensure_ascii=False, separators=(",", ":"))
    print(f"{name}: {len(items)} items")


def from_alerts():
    """Big events straight from the disaster data (GDACS Orange/Red, M6+ quakes, active storms) as feed items."""
    try:
        d = json.load(open(os.path.join(OUT, "disasters.json"), encoding="utf-8"))
    except Exception:
        return []
    out = []
    for e in d.get("events", []):
        if e.get("alert") in ("Orange", "Red") and e.get("title"):
            out.append({"outlet": "GDACS", "title": e["title"], "summary": (e.get("relief") or {}).get("summary") or e.get("summary", ""),
                        "url": e.get("url"), "publishedAt": (e.get("to") or e.get("from") or d["updated"])[:19].replace("+00:00", "") + "Z", "cc": []})
    for q in d.get("quakes", []):
        if q.get("mag", 0) >= 6:
            out.append({"outlet": q.get("src", "USGS"), "title": f"Magnitude {q['mag']} earthquake — {q.get('place', '')}".strip(" —"),
                        "summary": f"Depth {q.get('depth')} km." + (" A tsunami message was issued." if q.get("tsunami") else ""),
                        "url": q.get("url"), "publishedAt": q["time"][:19] + "Z", "cc": []})
    for s in d.get("storms", []):
        if s.get("wind_kt"):
            out.append({"outlet": s.get("src", "NOAA").split(" (")[0], "title": f"{s.get('cls') or 'Storm'} {s.get('name')}: winds {s['wind_kt']} knots",
                        "summary": ("Affects " + s["country"] + ".") if s.get("country") else "", "url": s.get("url"), "publishedAt": d["updated"], "cc": []})
    return [x for x in out if x.get("url")]


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    cpath = os.path.join(OUT, "topic_ai_cache.json")
    try:
        cache = json.load(open(cpath, encoding="utf-8"))
    except Exception:
        cache = {"logistics": {}, "disasters": {}}
    try:
        print("Logistics:")
        logi = ai_keep(collect(LOGI_FEEDS, LOGI_RE, NOT_LOGI), "logistics", cache["logistics"])
        ids = key_dev_ids(cache["logistics"])
        save("logistics_feed.json", logi, {"storyIds": ids} if ids is not None else None)
        print("Disasters:")
        items = ai_keep(collect(DIS_FEEDS, DIS_RE, NOT_DIS), "disasters", cache["disasters"]) + from_alerts()   # live alerts are on topic by definition
        items = [x for x in items if (NOW - when(x["publishedAt"])).total_seconds() <= DIS_MAX_AGE_H * 3600] if all(when(x["publishedAt"]) for x in items) else items
        items.sort(key=lambda x: x["publishedAt"], reverse=True)
        save("disasters_feed.json", items[:80], allow_empty=True)   # an empty day writes an empty feed rather than keeping stale stories
        for t in cache:                      # keep the cache small
            if len(cache[t]) > 4000:
                cache[t] = dict(list(cache[t].items())[-3000:])
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as ex:
        print("fetch_topic_news failed:", ex)
