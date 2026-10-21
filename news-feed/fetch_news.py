#!/usr/bin/env python3
"""War Events: automatic news feed.

Pulls world-affairs headlines from RSS feeds, GDELT and (if keys are set)
NewsAPI / GNews. Keeps stories about conflict, diplomacy, trade/sanctions and
energy, pins each to a place, merges the same story across outlets, and writes
key_developments.json in the format the homepage globe already reads.
Only the headline and a link to the source are published. Standard library only.
"""
import hashlib, html, json, os, re, sys, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gazetteer import PLACES, locate  # noqa: E402
import outlets as ranking  # noqa: E402  (outlet tiers + per-outlet caps)

ROOT = os.path.dirname(HERE)
OUTPUT = os.environ.get("OUTPUT_PATH") or os.path.join(ROOT, "key_developments.json")
STORE = os.path.join(HERE, "seen_articles.json")
REMOVE = os.path.join(HERE, "remove.txt")

# ---- tuning ----
ROLL_HOURS = 12      # a cluster spanning more than this is shown by its newest 12 hours
MAX_AGE_HOURS = 48     # stories older than this drop off the globe
STORE_HOURS = 72       # how long fetched articles are remembered
MAX_STORIES = 30       # auto stories written to the feed (homepage shows the newest 10)
NEW_HOURS = 3          # "NEW" pill for stories younger than this
BREAK_WINDOW_H = 3     # breaking news: many outlets reporting the same event inside this window...
BREAK_OUTLETS = 5      # ...at least this many different outlets...
BREAK_MAJOR = 2        # ...of which at least this many are major (tier 1-2) newsrooms
BREAK_BOOST = 3.0      # breaking stories rank as if this many times more important (and sit at the top)
FRESH_HALF_LIFE = 18   # hours: how fast an older story gives up its place to newer ones
MIN_SCORE = 6          # outlet credit (tier 1 = 4, tier 2 = 3, tier 3 = 1.5 each), +2 if a major outlet, +topic strength (max 4)
USE_COVERS = os.environ.get("USE_COVERS", "1") != "0"
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "").strip()
GNEWS_KEY = os.environ.get("GNEWS_KEY", "").strip()
UA = "WarEventsNewsBot/1.0 (+https://www.warevents.com)"

GN = ("https://news.google.com/rss/search?q=site:{}+(war+OR+military+OR+troops+OR+missile+OR+sanctions"
      "+OR+ceasefire+OR+minister+OR+president+OR+election+OR+attack)+when:1d&hl=en-US&gl=US&ceid=US:en")
RSS_FEEDS = [
    ("BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("NPR", "https://feeds.npr.org/1004/rss.xml"),
    ("DW", "https://rss.dw.com/rdf/rss-en-world"),
    ("France 24", "https://www.france24.com/en/rss"),
    ("Politico Europe", "https://www.politico.eu/feed/"),
    # regional outlets -- catch big stories the Western wires miss
    ("Arab News", "https://www.arabnews.com/rss.xml"),
    ("The National", "https://www.thenationalnews.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("Asharq Al-Awsat", "https://english.aawsat.com/feed"),
    ("Middle East Eye", "https://www.middleeasteye.net/rss"),
    ("Times of Israel", "https://www.timesofisrael.com/feed/"),
    ("Al-Monitor", "https://www.al-monitor.com/rss"),
    ("Daily Sabah", "https://www.dailysabah.com/rssFeed/world"),
    ("Yonhap", "https://en.yna.co.kr/RSS/news.xml"),
    ("NK News", "https://www.nknews.org/feed/"),
    ("Japan Times", "https://www.japantimes.co.jp/feed/"),
    ("SCMP", "https://www.scmp.com/rss/91/feed"),
    ("The Diplomat", "https://thediplomat.com/feed/"),
    ("Dawn", "https://www.dawn.com/feeds/home"),
    ("The Hindu", "https://www.thehindu.com/news/international/feeder/default.rss"),
    ("RFI Africa", "https://www.rfi.fr/en/africa/rss"),
    ("France 24 Africa", "https://www.france24.com/en/africa/rss"),
    ("Le Monde", "https://www.lemonde.fr/en/international/rss_full.xml"),
    ("Africanews", "https://www.africanews.com/feed/rss"),
    ("Kyiv Independent", "https://kyivindependent.com/news-archive/rss/"),
    ("Sky News", "https://feeds.skynews.com/feeds/rss/world.xml"),
    # added Oct 2026: regions the list above barely covered
    ("Meduza", "https://meduza.io/rss/en/all"),
    ("The Moscow Times", "https://www.themoscowtimes.com/rss/news"),
    ("Ukrainska Pravda", "https://www.pravda.com.ua/eng/rss/"),
    ("Iran International", "https://www.iranintl.com/en/feed"),
    ("The New Arab", "https://www.newarab.com/rss"),
    ("Jerusalem Post", "https://www.jpost.com/rss/rssfeedsfrontpage.aspx"),
    ("Radio Dabanga", "https://www.dabangasudan.org/en/feed"),
    ("Premium Times", "https://www.premiumtimesng.com/feed"),
    ("Daily Maverick", "https://www.dailymaverick.co.za/dmrss/"),
    ("CNA", "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6311"),
    ("Taipei Times", "https://www.taipeitimes.com/xml/index.rss"),
    ("The Irrawaddy", "https://www.irrawaddy.com/feed"),
    ("Rappler", "https://www.rappler.com/feed/"),
    ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/english.elpais.com/portada"),
    ("Mexico News Daily", "https://mexiconewsdaily.com/feed/"),
    ("Buenos Aires Times", "https://www.batimes.com.ar/feed"),
    ("Balkan Insight", "https://balkaninsight.com/feed/"),
    ("Notes from Poland", "https://notesfrompoland.com/feed/"),
    ("OC Media", "https://oc-media.org/feed/"),
    ("Euronews", "https://www.euronews.com/rss"),
    # Reuters and AP have no public RSS: Google News search feeds limited to their sites, last 24 hours.
    # Titles end in " - Reuters" / " - AP News" (trimmed when read); links go via news.google.com.
    ("Reuters", GN.format("reuters.com")),
    ("AP", GN.format("apnews.com")),
    # state media, Oct 2026: China and Iran. Xinhua's and China Daily's own feeds are dead (2018 items / 404),
    # People's Daily's stopped in 2025 and Fars blocks foreign readers, so those four come via Google News.
    ("Xinhua", GN.format("english.news.cn")),
    ("People's Daily", GN.format("en.people.cn")),
    ("China Daily", GN.format("chinadaily.com.cn")),
    ("CGTN", "https://www.cgtn.com/subscribe/rss/section/world.xml"),
    ("Press TV", "https://www.presstv.ir/rss.xml"),
    ("Fars", GN.format("farsnews.ir")),
]
# Reuters and AP have no public RSS; they arrive through GDELT (and NewsAPI if a key is set).
GDELT_DOMAINS = ["reuters.com", "apnews.com", "ft.com", "bloomberg.com", "aljazeera.com", "bbc.com", "bbc.co.uk"]
GDELT_TERMS = ["sanctions", "tariffs", "troops", "missile", "ceasefire", "military", "\"peace talks\"",
               "summit", "\"foreign minister\"", "OPEC", "pipeline", "\"oil prices\"", "airstrike", "NATO", "embargo"]

OUTLETS = {
    "reuters.com": "Reuters", "apnews.com": "AP", "bbc.co.uk": "BBC News", "bbc.com": "BBC News",
    "aljazeera.com": "Al Jazeera", "theguardian.com": "The Guardian", "ft.com": "Financial Times",
    "bloomberg.com": "Bloomberg", "dw.com": "DW", "france24.com": "France 24", "npr.org": "NPR",
    "politico.eu": "Politico Europe", "politico.com": "Politico", "nytimes.com": "The New York Times",
    "washingtonpost.com": "The Washington Post", "wsj.com": "The Wall Street Journal",
    "economist.com": "The Economist", "cnn.com": "CNN", "scmp.com": "South China Morning Post",
    "asia.nikkei.com": "Nikkei Asia", "arabnews.com": "Arab News", "thenationalnews.com": "The National",
    "aawsat.com": "Asharq Al-Awsat", "middleeasteye.net": "Middle East Eye", "timesofisrael.com": "Times of Israel",
    "al-monitor.com": "Al-Monitor", "dailysabah.com": "Daily Sabah", "yna.co.kr": "Yonhap", "nknews.org": "NK News",
    "japantimes.co.jp": "Japan Times", "thediplomat.com": "The Diplomat", "dawn.com": "Dawn", "thehindu.com": "The Hindu",
    "rfi.fr": "RFI Africa", "lemonde.fr": "Le Monde", "africanews.com": "Africanews", "kyivindependent.com": "Kyiv Independent",
    "news.sky.com": "Sky News", "meduza.io": "Meduza", "themoscowtimes.com": "The Moscow Times",
    "pravda.com.ua": "Ukrainska Pravda", "iranintl.com": "Iran International", "newarab.com": "The New Arab",
    "jpost.com": "Jerusalem Post", "dabangasudan.org": "Radio Dabanga", "premiumtimesng.com": "Premium Times",
    "dailymaverick.co.za": "Daily Maverick", "channelnewsasia.com": "CNA", "taipeitimes.com": "Taipei Times",
    "irrawaddy.com": "The Irrawaddy", "rappler.com": "Rappler", "elpais.com": "El País",
    "mexiconewsdaily.com": "Mexico News Daily", "batimes.com.ar": "Buenos Aires Times", "balkaninsight.com": "Balkan Insight",
    "notesfrompoland.com": "Notes from Poland", "oc-media.org": "OC Media", "euronews.com": "Euronews",
    "news.cn": "Xinhua", "xinhuanet.com": "Xinhua", "people.cn": "People's Daily", "chinadaily.com.cn": "China Daily",
    "cgtn.com": "CGTN", "presstv.ir": "Press TV", "presstv.co.uk": "Press TV", "farsnews.ir": "Fars",
}
TIER1 = {"Reuters", "AP", "BBC News", "Al Jazeera", "The Guardian", "Financial Times", "Bloomberg"}
PRIORITY = ["Reuters", "AP", "BBC News", "Al Jazeera", "The Guardian", "Financial Times", "Bloomberg",
            "DW", "France 24", "NPR", "Politico Europe"]

TOPICS = {
    "conflict": ["war", "troop", "soldier", "military", "missile", "drone", "airstrike", "air strike", "strike",
                 "ceasefire", "truce", "offensive", "shelling", "artillery", "insurgent", "rebel", "militia",
                 "army", "navy", "warship", "invasion", "frontline", "front line", "battle", "bombing",
                 "bombardment", "attack", "hostage", "nuclear weapon", "ballistic", "fighter jet", "defence",
                 "defense", "armed forces", "coup", "junta"],
    "diplomacy": ["summit", "talks", "diplomat", "diplomatic", "ambassador", "embassy", "foreign minister",
                  "foreign secretary", "secretary of state", "treaty", "alliance", "nato", "security council",
                  "united nations", "g7", "g20", "brics", "asean", "peace deal", "peace plan", "negotiation",
                  "negotiator", "envoy", "bilateral", "accord", "normalisation", "normalization"],
    "trade": ["tariff", "sanction", "export control", "export ban", "trade deal", "trade war", "embargo", "wto",
              "supply chain", "semiconductor", "chip export", "rare earth", "import ban", "customs dut"],
    "energy": ["oil", "gas", "opec", "lng", "pipeline", "crude", "nuclear plant", "power plant", "energy",
               "refinery", "power grid", "uranium", "enrichment", "oilfield", "gas field"],
}
TOPIC_RX = {k: re.compile(r"\b(?:" + "|".join(re.escape(w) for w in v) + r")(?:s|es|ies|y)?\b", re.I)
            for k, v in TOPICS.items()}
EXCLUDE_RX = re.compile(r"\b(?:" + "|".join([
    r"the couples?",
    r"couples",
    r"families kept",
    r"kept apart",
    r"love stor(?:y|ies)",
    r"in love",
    r"fell in love",
    r"wedding",
    r"weddings",
    r"newlyweds",
    r"meet the",
    r"my life",
    r"my family",
    r"my son",
    r"my daughter",
    r"my husband",
    r"my wife",
    r"i was",
    r"i survived",
    r"we were",
    r"diary",
    r"letters? from",
    r"voices from",
    r"life under",
    r"life in",
    r"daily life",
    r"what it(?:'|’)s like",
    r"how it feels",
    r"a day in",
    r"portrait of",
    r"the woman who",
    r"the man who",
    r"the boy who",
    r"the girl who",
    r"the family who",
    r"the people who",
    r"the doctor who",
    r"the teacher who",
    r"stories of",
    r"human stories",
    r"heartbreak",
    r"grief",
    r"reunited",
    r"reunion",
    r"the artist",
    r"artists",
    r"poets?",
    r"poetry",
    r"musicians?",
    r"chefs?",
    r"bakery",
    r"football team",
    r"orphans? who",
    r"children who",
    r"five things",
    r"quiz",
    r"anniversary",
    r"years on",
    r"remembering",
    r"in memoriam",
    r"tribute",
    r"football",
    r"soccer",
    r"cricket",
    r"tennis",
    r"golf",
    r"rugby",
    r"boxing",
    r"ufc",
    r"formula 1",
    r"f1",
    r"grand prix",
    r"olympics?",
    r"paralympics?",
    r"world cup",
    r"euro 20\d\d",
    r"premier league",
    r"champions league",
    r"la liga",
    r"nba",
    r"nfl",
    r"mlb",
    r"nhl",
    r"wimbledon",
    r"marathon",
    r"transfer window",
    r"manager sacked",
    r"fixtures?",
    r"semi-final",
    r"quarter-final",
    r"final score",
    r"celebrity",
    r"celebrities",
    r"oscars?",
    r"baftas?",
    r"emmys?",
    r"grammys?",
    r"eurovision",
    r"film",
    r"movie",
    r"box office",
    r"album",
    r"singer",
    r"rapper",
    r"tv show",
    r"netflix",
    r"streaming",
    r"series finale",
    r"reality tv",
    r"royal baby",
    r"prince harry",
    r"meghan",
    r"influencers?",
    r"tiktok star",
    r"recipe",
    r"cooking",
    r"restaurants?",
    r"fashion",
    r"beauty",
    r"wellness",
    r"diet",
    r"fitness",
    r"horoscope",
    r"quiz",
    r"crossword",
    r"puzzle",
    r"travel guide",
    r"holiday deals?",
    r"property market",
    r"dating",
    r"wedding",
    r"obituary",
    r"dies aged",
    r"died aged",
    r"in pictures",
    r"photos of the",
    r"photo essay",
    r"week in pictures",
    r"long read",
    r"podcast",
    r"live blog",
    r"as it happened",
    r"ofgem",
    r"energy bills?",
    r"energy suppliers?",
    r"price cap",
    r"mortgages?",
    r"house prices",
    r"renters",
    r"landlords?",
    r"interest rates?",
    r"bank of england",
    r"federal reserve rate",
    r"inflation figures",
    r"pensions?",
    r"state pension",
    r"universal credit",
    r"cost of living",
    r"retailers?",
    r"shoppers",
    r"consumers?",
    r"customers",
    r"supermarkets?",
    r"black friday",
    r"sales figures",
    r"quarterly results",
    r"profit warning",
    r"share price",
    r"stock market",
    r"ftse",
    r"dow jones",
    r"nasdaq",
    r"s&p 500",
    r"ipo",
    r"bonuses",
    r"pay rise",
    r"strike action",
    r"rail strike",
    r"junior doctors",
    r"train fares",
    r"flight delays",
    r"budget airline",
    r"nhs",
    r"hospital waiting",
    r"gp appointments",
    r"exam results",
    r"student loans?",
    r"council tax",
    r"bin collections?",
    r"potholes",
    r"planning permission",
    r"local elections?",
    r"by-election",
    r"murder",
    r"murdered",
    r"stabbing",
    r"stabbed",
    r"manslaughter",
    r"burglary",
    r"robbery",
    r"fraud trial",
    r"court hears",
    r"trial hears",
    r"inquest",
    r"police appeal",
    r"missing person",
    r"missing woman",
    r"missing man",
    r"car crash",
    r"road crash",
    r"house fire",
    r"sexual assault",
    r"abuse scandal",
    r"iphone",
    r"samsung",
    r"gadget",
    r"video game",
    r"gaming",
    r"smartphone",
    r"ai chatbot",
    r"chatgpt",
    r"space tourism",
    r"dinosaur",
    r"fossil",
    r"archaeolog\w*",
    r"asteroid",
    r"comet",
    r"weather forecast",
    r"heatwave",
    r"flood warning",
    r"hay fever",
    r"covid jab",
    r"flu jab",
    r"vaccine rollout",
    r"dementia",
    r"obesity",
    r"vaping",
    r"smoking ban"
]) + r")\b", re.I)
SUFFIX_RX = re.compile(r"\s+[-|–—]\s+(Reuters|AP News|AP|Associated Press|BBC News|BBC|Al Jazeera|The Guardian|"
                       r"Financial Times|Bloomberg|DW|France 24|NPR|POLITICO|Politico)\s*$", re.I)
TAG_RX = re.compile(r"<[^>]+>")
STOP = set("the of in on at to for and or as by with from over after amid says say said new is are be will "
           "its it his her their than into out has have who what why how not but more".split())


def log(*a):
    print(*a, flush=True)


def now_utc():
    return datetime.now(timezone.utc)


def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_time(s):
    s = (s or "").strip()
    if not s:
        return None
    for fn in (parsedate_to_datetime,
               lambda x: datetime.fromisoformat(x.replace("Z", "+00:00")),
               lambda x: datetime.strptime(x, "%Y%m%dT%H%M%SZ")):
        try:
            d = fn(s)
        except Exception:
            continue
        if d is None:
            continue
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    return None


def clean(s):
    s = html.unescape(TAG_RX.sub(" ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def url_key(u):
    p = urllib.parse.urlsplit(u.strip())
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query)
         if not k.lower().startswith(("utm_", "at_", "cmp", "ocid", "ref"))]
    host = p.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    return host + p.path.rstrip("/") + ("?" + urllib.parse.urlencode(q) if q else "")


def outlet_for(url):
    host = urllib.parse.urlsplit(url or "").netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    for dom, name in OUTLETS.items():
        if host == dom or host.endswith("." + dom):
            return name
    return host


# ---------------- sources ----------------
def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _image(el):
    best = (-1, None)
    for c in el.iter():
        url = c.get("url")
        if _local(c.tag) in ("content", "thumbnail", "enclosure") and url:
            kind = (c.get("medium") or c.get("type") or "image").lower()
            if "image" not in kind:
                continue
            try:
                w = int(c.get("width") or 0)
            except ValueError:
                w = 0
            if w > best[0]:
                best = (w, url)
    return best[1]


def from_rss(name, url):
    import time as _t, random as _r
    _t.sleep(_r.uniform(1.5, 4))   # polite spacing between sites
    body = http_get(url)
    end = max(body.rfind(b"</rss>"), body.rfind(b"</feed>"), body.rfind(b"</rdf:RDF>"))
    root = ET.fromstring(body[:body.index(b">", end) + 1] if end > 0 else body)   # drop anything a CDN tacks on after the feed
    out = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        a = {"outlet": name}
        for c in el:
            n, t = _local(c.tag), (c.text or "").strip()
            if n == "title":
                a["title"] = t
            elif n == "link":
                href = c.get("href")
                if href:
                    if c.get("rel", "alternate") == "alternate":
                        a.setdefault("url", href)
                elif t:
                    a.setdefault("url", t)
            elif n == "guid" and t.startswith("http"):
                a["guid"] = t
            elif n in ("description", "summary"):
                a.setdefault("desc", t)
            elif n in ("pubDate", "published", "updated", "date") and not a.get("time"):
                a["time"] = parse_time(t)
        if not a.get("url"):
            a["url"] = a.get("guid")
        if "news.google.com" in url and a.get("title"):   # "Headline - Reuters" -> "Headline"
            a["title"] = re.sub(r"\s+-\s+[^-]{2,30}$", "", a["title"])
            a["title"] = re.sub(r"^Farsnews\s*\|\s*", "", a["title"])
        if not a.get("time"):   # undated feeds (Press TV): take the day from links like /2026/10/21/
            m = re.search(r"/(20\d\d)/(\d\d)/(\d\d)/", a.get("url") or "")
            if m:
                a["time"] = parse_time(f"{m.group(1)}-{m.group(2)}-{m.group(3)}T12:00:00Z")
        a["cover"] = _image(el)
        out.append(a)
    return out


def from_gdelt():
    q = "(" + " OR ".join(GDELT_TERMS) + ") sourcelang:english (" + " OR ".join("domain:" + d for d in GDELT_DOMAINS) + ")"
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(
        {"query": q, "mode": "artlist", "format": "json", "maxrecords": "200", "timespan": "6h", "sort": "datedesc"})
    data = json.loads(http_get(url).decode("utf-8", "replace") or "{}")
    return [{"title": x.get("title"), "url": x.get("url"), "time": parse_time(x.get("seendate")),
             "cover": x.get("socialimage") or None, "outlet": outlet_for(x.get("url"))}
            for x in data.get("articles", [])]


def from_newsapi():
    url = "https://newsapi.org/v2/top-headlines?" + urllib.parse.urlencode(
        {"sources": "reuters,associated-press,bbc-news,al-jazeera-english", "pageSize": "100", "apiKey": NEWSAPI_KEY})
    data = json.loads(http_get(url))
    return [{"title": x.get("title"), "desc": x.get("description"), "url": x.get("url"),
             "time": parse_time(x.get("publishedAt")), "cover": x.get("urlToImage"), "outlet": outlet_for(x.get("url"))}
            for x in data.get("articles", [])]


def from_gnews():
    url = "https://gnews.io/api/v4/top-headlines?" + urllib.parse.urlencode(
        {"category": "world", "lang": "en", "max": "50", "apikey": GNEWS_KEY})
    data = json.loads(http_get(url))
    return [{"title": x.get("title"), "desc": x.get("description"), "url": x.get("url"),
             "time": parse_time(x.get("publishedAt")), "cover": x.get("image"),
             "outlet": outlet_for(x.get("url")) if outlet_for(x.get("url")) in TIER1 else (x.get("source") or {}).get("name") or outlet_for(x.get("url"))}
            for x in data.get("articles", [])]


# ---------------- filtering / grouping ----------------
def topic_hits(title, desc):
    hits = {}
    for name, rx in TOPIC_RX.items():
        n = 2 * len(rx.findall(title)) + len(rx.findall(desc))
        if n:
            hits[name] = n
    return hits


def qualify(a, now):
    title = SUFFIX_RX.sub("", clean(a.get("title")))
    url = (a.get("url") or "").strip()
    if len(title) < 15 or not url.startswith("http") or EXCLUDE_RX.search(title):
        return None
    t = a.get("time") or now
    if (t.hour, t.minute, t.second) == (0, 0, 0) and now - t < timedelta(hours=24):
        t = now   # date-only feed time (e.g. Al Jazeera live blogs): use when we first saw it, not midnight
    if t > now + timedelta(minutes=10):
        t = now
    if now - t > timedelta(hours=STORE_HOURS):
        return None
    desc = clean(a.get("desc"))[:600]
    topics = topic_hits(title, desc)
    if not topics:
        return None
    place = locate(title) or locate(desc)
    if not place:
        return None
    cover = a.get("cover") if USE_COVERS else None
    if cover and not cover.startswith("https://"):
        cover = None
    return {"key": url_key(url), "url": url, "title": title, "outlet": a.get("outlet") or outlet_for(url),
            "time": iso(t), "cover": cover, "place": place["label"], "topics": topics}


import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "news-feed" else os.path.dirname(os.path.abspath(__file__)), "news-feed"))
from dedupe import dedupe, same_story, tokens as story_tokens


def tokens(t):
    return {w for w in re.findall(r"[a-z0-9']+", t.lower()) if len(w) > 2 and w not in STOP}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def cluster(arts):
    groups = []
    for a in sorted(arts, key=lambda x: x["time"]):
        tk = story_tokens(a["title"])
        best, best_j = None, 0.0
        for g in groups:
            same_place = a["place"] in g["places"]
            if not any(same_story(tk, m, same_place) for m in g["tokens"]):
                continue
            j = max(jaccard(tk, m) for m in g["tokens"]) + (0.2 if same_place else 0)
            if j > best_j:
                best, best_j = g, j
        if best:
            best["arts"].append(a); best["tokens"].append(tk); best["places"].add(a["place"])
        else:
            groups.append({"arts": [a], "tokens": [tk], "places": {a["place"]}})
    return groups


def rank(a):
    # best-ranked outlet first: tier, then the PRIORITY order within it
    return (ranking.tier(a["outlet"]), PRIORITY.index(a["outlet"]) if a["outlet"] in PRIORITY else len(PRIORITY))


def build_story(g, now):
    arts = g["arts"]
    first = min(arts, key=lambda a: a["time"])
    newest = max(arts, key=lambda a: a["time"])
    # A story still developing a day later (new reports keep joining the cluster) is ranked and
    # shown by its latest reporting, not frozen at the first article, or it sinks off the page.
    rolled = (parse_time(newest["time"]) - parse_time(first["time"])) > timedelta(hours=ROLL_HOURS)
    pool = [a for a in arts if parse_time(newest["time"]) - parse_time(a["time"]) <= timedelta(hours=ROLL_HOURS)] if rolled else arts
    rep = min(pool, key=lambda a: (rank(a), a["time"]))
    if rolled:
        first = min(pool, key=lambda a: a["time"])
    outlets = []
    for a in sorted(arts, key=rank):
        if a["outlet"] not in outlets:
            outlets.append(a["outlet"])
    topics = Counter()
    for a in arts:
        topics.update(a["topics"])
    # Big, established newsrooms count for more; a story only a small outlet carries rarely makes the cut.
    score = round(sum(ranking.weight(o) for o in outlets) + min(4, sum(topics.values()))
                  + (2 if any(ranking.tier(o) == 1 for o in outlets) else 0), 1)
    place = PLACES[Counter(a["place"] for a in arts).most_common(1)[0][0]]
    t = parse_time(first["time"])
    body = "<b>Reported by:</b> " + html.escape(rep["outlet"])
    others = [o for o in outlets if o != rep["outlet"]]
    if others:
        body += ". Also covered by " + html.escape(", ".join(others[:4])) + "."
    s = {
        "id": "auto-" + hashlib.sha1(first["key"].encode()).hexdigest()[:12],
        "auto": True,
        "headline": html.escape(rep["title"], quote=False),
        "body": body,
        "place": place["label"], "cat": place["cat"],
        "lat": place["lat"], "lon": place["lon"],
        "time": iso(t),
        "isNew": now - t < timedelta(hours=NEW_HOURS),
        "sourceUrl": rep["url"], "sourceLabel": "Source",
        # pages enrich_stories.py can read the article from (Google News links for Reuters/AP can't be read)
        "textUrls": [a["url"] for a in sorted(arts, key=rank) if a.get("url") and "news.google.com" not in a["url"]][:3],
        "outlets": outlets,
        "topics": [k for k, _ in topics.most_common()],
        "score": score,
        "_keys": [a["key"] for a in arts],
    }
    # Breaking: a burst of reporting -- many different outlets, several of them major, on the same event in the last few hours.
    recent_cut = now - timedelta(hours=BREAK_WINDOW_H)
    burst = sorted({a["outlet"] for a in arts if (parse_time(a["time"]) or now) >= recent_cut})
    major = [o for o in burst if ranking.tier(o) <= 2]
    if len(burst) >= BREAK_OUTLETS and len(major) >= BREAK_MAJOR:
        s["breaking"] = True
        s["burst"] = len(burst)
    cover = rep.get("cover") or next((a["cover"] for a in arts if a.get("cover")), None)
    if cover:
        s["cover"] = cover
    return s


def load_remove():
    rules = {"keys": set(), "ids": set(), "phrases": []}
    try:
        with open(REMOVE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("http"):
                    rules["keys"].add(url_key(line))
                elif line.startswith("auto-"):
                    rules["ids"].add(line)
                else:
                    rules["phrases"].append(line.lower())
    except FileNotFoundError:
        pass
    return rules


def removed(s, rules):
    if s["id"] in rules["ids"] or rules["keys"] & set(s["_keys"]):
        return True
    head = html.unescape(s["headline"]).lower()
    return any(p in head for p in rules["phrases"])


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def write_if_changed(path, data):
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except FileNotFoundError:
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


# ---------------- main ----------------
def main():
    now = now_utc()
    raw, reached = [], 0
    sources = [(n, (lambda n=n, u=u: from_rss(n, u))) for n, u in RSS_FEEDS]
    sources.append(("GDELT", from_gdelt))
    if NEWSAPI_KEY:
        sources.append(("NewsAPI", from_newsapi))
    if GNEWS_KEY:
        sources.append(("GNews", from_gnews))
    for name, fn in sources:
        try:
            items = fn()
            raw += items
            reached += 1
            log(f"  {name}: {len(items)} items")
        except Exception as e:
            log(f"  {name}: FAILED ({e})")
    if not reached:
        log("No source reachable; leaving files untouched.")
        return 1

    store = {a["key"]: a for a in load_json(STORE, []) if isinstance(a, dict) and "key" in a}
    added = 0
    for a in raw:
        q = qualify(a, now)
        if q and q["key"] not in store:
            store[q["key"]] = q
            added += 1
    keep_after = now - timedelta(hours=STORE_HOURS)
    kept = [a for a in store.values()
            if a.get("place") in PLACES and (parse_time(a.get("time")) or now) >= keep_after]
    kept.sort(key=lambda a: a["time"], reverse=True)
    write_if_changed(STORE, kept)

    show_after = now - timedelta(hours=MAX_AGE_HOURS)
    recent = [a for a in kept if parse_time(a["time"]) >= show_after]
    rules = load_remove()
    stories = [build_story(g, now) for g in cluster(recent)]
    stories = [s for s in stories if s["score"] >= MIN_SCORE and not removed(s, rules)]
    # Stories Claude already judged not geopolitical (enrich_stories.py drops them later anyway)
    # must not take one of the slots, or fresh stories get squeezed out.
    try:
        geo_cache = load_json(os.path.join(HERE, "enrich_cache.json"), {})
        min_geo = int(os.environ.get("MIN_GEO", "7"))
        stories = [s for s in stories if (geo_cache.get(s["id"]) or {}).get("geo", 10) >= min_geo]
        # "Worldwide implications": once Claude has scored a burst story, it must be clearly geopolitical (8+) to stay Breaking.
        for s_ in stories:
            if s_.get("breaking") and (geo_cache.get(s_["id"]) or {}).get("geo", 10) < 8:
                s_.pop("breaking", None)
    except Exception:
        pass
    # Rank by importance AND freshness: a story's score halves every FRESH_HALF_LIFE hours, so a
    # big story from yesterday morning no longer blocks today's news, but still beats a minor new one.
    def fresh_rank(s):
        age_h = max(0.0, (now - (parse_time(s["time"]) or now)).total_seconds() / 3600)
        return s["score"] * 0.5 ** (age_h / FRESH_HALF_LIFE) * (BREAK_BOOST if s.get("breaking") else 1)
    stories.sort(key=fresh_rank, reverse=True)
    # Lesser-known / very high-volume outlets (e.g. The Hindu, Dawn) lead at most 2 stories each.
    stories = ranking.apply_caps(stories, lambda s: s["outlets"][0] if s.get("outlets") else "")
    stories = stories[:MAX_STORIES]
    for s in stories:
        del s["_keys"]

    existing = load_json(OUTPUT, [])
    manual = [p for p in existing if isinstance(p, dict) and not p.get("auto")] if isinstance(existing, list) else []
    final = manual + stories
    final.sort(key=lambda p: parse_time(p.get("time")) or now, reverse=True)
    changed = write_if_changed(OUTPUT, final)
    log(f"{added} new articles, {len(recent)} recent, {len(stories)} auto stories, "
        f"{len(manual)} hand-made kept. Feed {'updated' if changed else 'unchanged'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
