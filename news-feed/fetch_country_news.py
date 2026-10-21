"""Up to five most recent conflict/geopolitics stories per country -> data/country_news.json.

Runs hourly from .github/workflows/update-news.yml. Standard library only, no API key.

Pulls free (non-paywalled) world-news and defence RSS feeds, then matches each
headline to countries by name, demonym, capital or leader. Newest first,
near-duplicates dropped.
If a country has fewer than 5 stories, whatever exists is kept (even one).
"""
import json, os, re, time, html, random, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from datetime import datetime
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "news-feed" else os.path.dirname(os.path.abspath(__file__)), "news-feed"))
from dedupe import dedupe, same_story, tokens as story_tokens

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = json.load(open(os.path.join(ROOT, "news-feed", "country_names.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "data", "country_news.json")
MAX_AGE = 14 * 86400

WIRES = [
    ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("DW", "https://rss.dw.com/rdf/rss-en-world"),
    ("France 24", "https://www.france24.com/en/rss"),
    ("NPR", "https://feeds.npr.org/1004/rss.xml"),
    ("Defense News", "https://www.defensenews.com/arc/outboundfeeds/rss/"),
    ("DefenceTalk", "https://www.defencetalk.com/feed/"),
    ("BBC Middle East", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
    ("BBC Africa", "https://feeds.bbci.co.uk/news/world/africa/rss.xml"),
    ("BBC Asia", "https://feeds.bbci.co.uk/news/world/asia/rss.xml"),
    ("BBC Europe", "https://feeds.bbci.co.uk/news/world/europe/rss.xml"),
    ("BBC Latin America", "https://feeds.bbci.co.uk/news/world/latin_america/rss.xml"),
    ("Sky News", "https://feeds.skynews.com/feeds/rss/world.xml"),
    ("CBS News", "https://www.cbsnews.com/latest/rss/world"),
    ("ABC News", "https://abcnews.go.com/abcnews/internationalheadlines"),
    ("UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
    ("UN News Peace", "https://news.un.org/feed/subscribe/en/news/topic/peace-and-security/feed/rss.xml"),
    ("Euronews", "https://www.euronews.com/rss?format=mrss&level=theme&name=news"),
    ("RFE/RL", "https://www.rferl.org/api/zrqiteuuir"),
    ("Kyiv Independent", "https://kyivindependent.com/news-archive/rss/"),
    ("Times of Israel", "https://www.timesofisrael.com/feed/"),
    ("Middle East Eye", "https://www.middleeasteye.net/rss"),
    ("The Diplomat", "https://thediplomat.com/feed/"),
    ("SCMP Asia", "https://www.scmp.com/rss/3/feed"),
    ("Africanews", "https://www.africanews.com/feed/rss"),
    ("MercoPress", "https://en.mercopress.com/rss/"),
    ("Breaking Defense", "https://breakingdefense.com/feed/"),
    ("The War Zone", "https://www.twz.com/feed"),
    ("Defense One", "https://www.defenseone.com/rss/all/"),
    ("Military Times", "https://www.militarytimes.com/arc/outboundfeeds/rss/"),
    ("UK Defence Journal", "https://ukdefencejournal.org.uk/feed/"),
    ("Army Recognition", "https://www.armyrecognition.com/feed"),
    ("Crisis Group", "https://www.crisisgroup.org/rss.xml"),
    ("ReliefWeb", "https://reliefweb.int/updates/rss.xml"),
    ("RT", "https://www.rt.com/rss/news/"),
    ("Sputnik", "https://sputnikglobe.com/export/rss2/archive/index.xml"),
    ("Xinhua", "https://news.google.com/rss/search?q=site:english.news.cn+(war+OR+military+OR+troops+OR+missile+OR+sanctions"
      "+OR+ceasefire+OR+minister+OR+president+OR+election+OR+attack)+when:1d&hl=en-US&gl=US&ceid=US:en"),   # own feed is dead; Google News site search
    ("China Daily", "https://news.google.com/rss/search?q=site:chinadaily.com.cn+(war+OR+military+OR+troops+OR+missile+OR+sanctions"
      "+OR+ceasefire+OR+minister+OR+president+OR+election+OR+attack)+when:1d&hl=en-US&gl=US&ceid=US:en"),   # own feed is dead; Google News site search
    ("CGTN", "https://www.cgtn.com/subscribe/rss/section/world.xml"),
    ("Global Times", "https://www.globaltimes.cn/rss/outbrain.xml"),
    ("TASS", "https://tass.com/rss/v2.xml"),
]

# Extra words that identify a country in a headline beyond its own name.
ALIASES = {
    "840": "US|U\\.S\\.|USA|American|Americans|Washington|Pentagon|White House|Trump",
    "643": "Russian|Russians|Kremlin|Moscow|Putin", "156": "Chinese|Beijing|Xi Jinping",
    "826": "UK|U\\.K\\.|British|Britain|London|Starmer|Burnham", "804": "Ukrainian|Ukrainians|Kyiv|Kiev|Zelensky|Zelenskyy",
    "376": "Israeli|Israelis|Netanyahu|IDF", "364": "Iranian|Iranians|Tehran", "250": "French|Paris|Macron",
    "276": "German|Germans|Berlin|Merz", "392": "Japanese|Tokyo", "410": "South Korean|Seoul",
    "408": "North Korean|Pyongyang|Kim Jong", "356": "Indian|New Delhi|Modi", "586": "Pakistani|Islamabad",
    "792": "Turkish|Ankara|Erdogan|Türkiye", "682": "Saudi|Riyadh", "760": "Syrian|Syrians|Damascus",
    "422": "Lebanese|Beirut|Hezbollah", "887": "Yemeni|Houthi|Houthis", "275": "Palestinian|Palestinians|Gaza|West Bank|Hamas",
    "158": "Taiwanese|Taipei", "729": "Sudanese|Khartoum|RSF", "4": "Afghan|Kabul|Taliban", "862": "Venezuelan|Caracas|Maduro",
    "484": "Mexican|Mexico City", "76": "Brazilian|Brasilia", "32": "Argentine|Buenos Aires", "124": "Canadian|Ottawa",
    "36": "Australian|Canberra", "380": "Italian|Rome|Meloni", "724": "Spanish|Madrid", "616": "Polish|Warsaw",
    "818": "Egyptian|Cairo", "368": "Iraqi|Baghdad", "434": "Libyan|Tripoli", "566": "Nigerian|Abuja",
    "180": "Congolese|Kinshasa|DRC|M23", "231": "Ethiopian|Addis Ababa", "706": "Somali|Mogadishu|al-Shabab",
    "104": "Myanmar|Burmese|Naypyidaw", "608": "Filipino|Manila", "704": "Vietnamese|Hanoi", "360": "Indonesian|Jakarta",
    "112": "Belarusian|Minsk|Lukashenko", "268": "Georgian|Tbilisi", "31": "Azerbaijani|Baku", "51": "Armenian|Yerevan",
    "398": "Kazakh|Astana", "192": "Cuban|Havana", "170": "Colombian|Bogota", "710": "South African|Pretoria",
    "784": "UAE|Emirati|Abu Dhabi|Dubai", "634": "Qatari|Doha", "400": "Jordanian|Amman", "50": "Bangladeshi|Dhaka",
    "144": "Sri Lankan|Colombo", "524": "Nepali|Kathmandu", "466": "Malian|Bamako", "562": "Nigerien|Niamey",
    "854": "Burkinabe|Ouagadougou", "148": "Chadian|N'Djamena", "728": "South Sudanese|Juba", "332": "Haitian|Port-au-Prince",
}

KEYWORDS = re.compile(r"\b(war|wars|military|army|troops|missiles?|drones?|strikes?|attacks?|sanctions?|"
                      r"diplomat\w*|minister|president|prime minister|summit|treaty|talks|border|"
                      r"election|coup|protests?|ceasefire|nato|un|security|defen[cs]e|navy|"
                      r"nuclear|tariffs?|trade deal|alliance|rebels?|conflict|embassy|envoy|killed|forces|militants?)\b", re.I)
SKIP = re.compile(r"\b(football|soccer|cricket|nba|nfl|match|recipe|celebrity|movie|box office|"
                  r"weather|horoscope|lottery|tennis|golf|olympic)\b", re.I)
UA = {"User-Agent": "Mozilla/5.0 (compatible; WarEventsBot/1.0; +https://warevents.com)"}


def get(url, tries=2):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                return r.read()
        except Exception as e:
            if k == tries - 1:
                raise
            time.sleep(2 + 3 * k)


def ts_of(s):
    try:
        return int(parsedate_to_datetime(s).timestamp())
    except Exception:
        try:
            return int(datetime.fromisoformat((s or "").replace("Z", "+00:00")).timestamp())
        except Exception:
            return 0


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def parse_items(data, default_source=""):
    root = ET.fromstring(data)
    out = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        f = {c.tag.split("}")[-1]: c for c in it}
        title = clean(f["title"].text if "title" in f else "")
        link = ""
        if "link" in f:
            link = (f["link"].text or f["link"].get("href") or "").strip()
        date = ""
        for k in ("pubDate", "date", "updated", "published"):
            if k in f and f[k].text:
                date = f[k].text
                break
        source = default_source
        if "source" in f and f["source"].text:
            source = f["source"].text.strip()
            if title.endswith(" - " + source):
                title = title[: -len(source) - 3].strip()
        if title:
            out.append({"title": title, "source": source, "link": link, "ts": ts_of(date)})
    return out


def is_geo(title):
    return KEYWORDS.search(title) and not SKIP.search(title)


def country_re(cid, name):
    parts = [re.escape(name)]
    if ALIASES.get(cid):
        parts.append(ALIASES[cid])
    return re.compile(r"\b(" + "|".join(parts) + r")\b", re.I)


def one_wire(lw):
    label, url = lw
    time.sleep(random.uniform(0.5, 6))   # stagger requests instead of hitting every site at once
    try:
        items = parse_items(get(url), label)
        print("ok  ", label, len(items))
        return items
    except Exception as e:
        print("FAIL", label, e)
        return []


def wire_pool():
    pool = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for items in ex.map(one_wire, WIRES):
            pool += items
    now = time.time()
    return [s for s in pool if is_geo(s["title"]) and (not s["ts"] or now - s["ts"] < MAX_AGE)]


def top5(stories):
    return dedupe(sorted(stories, key=lambda s: s["ts"], reverse=True), limit=5)


def main():
    try:
        prev = json.load(open(OUT, encoding="utf-8")).get("countries", {})
    except Exception:
        prev = {}
    pool = wire_pool()
    print("wire stories:", len(pool))
    found = {cid: [] for cid in NAMES}
    for cid, name in NAMES.items():
        rx = country_re(cid, name)
        found[cid] = [s for s in pool if rx.search(s["title"])]


    out = {}
    for cid in NAMES:
        picks = top5(found[cid])
        if picks:
            out[cid] = picks
        elif prev.get(cid):
            out[cid] = prev[cid]  # keep the last good stories if nothing new came in
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": int(time.time()), "countries": out}, f, ensure_ascii=False, separators=(",", ":"))
    print("countries with stories:", len(out))


if __name__ == "__main__":
    main()
