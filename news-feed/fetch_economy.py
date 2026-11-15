#!/usr/bin/env python3
"""War Events: automatic Economy feed (a separate copy of fetch_news.py; keep the two in step).

Pulls economy and markets headlines from RSS feeds, Google News site searches, GDELT and (if keys are
set) NewsAPI / GNews business headlines. Keeps stories about markets, central banks and rates, inflation,
jobs, earnings and companies, trade and tariffs, housing, personal finance and energy prices; a cheap
yes/no check by Claude Haiku confirms each NEW headline (cached; without ANTHROPIC_API_KEY the keyword
filter decides alone). Pins each article to a place where it can (institutions such as "the Fed" count),
keeps placeless ones for enrich_stories.py to place, merges the same story across outlets, keeps only
stories reported by at least 3 different outlets, and writes economy_developments.json in the same
shape as key_developments.json. Only the headline and a link to the source are published.
Standard library only.
"""
import hashlib, html, json, os, re, sys, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gazetteer import PLACES, article_place, country_of, institution_place, locate  # noqa: E402
import outlets as ranking  # noqa: E402  (outlet tiers + per-outlet caps)
from sourcing import passes_strict_rule  # noqa: E402  (at least 3 different outlets, sister brands merged)
import usage  # noqa: E402  (prints this run's Claude token use and cost to the log)

ROOT = os.path.dirname(HERE)
OUTPUT = os.environ.get("OUTPUT_PATH") or os.path.join(ROOT, "economy_developments.json")
STORE = os.path.join(HERE, "economy_seen.json")
RELEVANCE = os.path.join(HERE, "economy_relevance.json")   # Haiku's cached yes/no per headline key
REMOVE = os.path.join(HERE, "remove.txt")

# ---- tuning ----
ROLL_HOURS = 12      # a cluster spanning more than this is shown by its newest 12 hours
MAX_AGE_HOURS = 48     # stories older than this drop off the globe
STORE_HOURS = 72       # how long fetched articles are remembered
MAX_STORIES = 30       # auto stories written to the feed (homepage shows the newest 10)
NEW_HOURS = 3          # "NEW" pill for stories younger than this
FRESH_HALF_LIFE = 18   # hours: how fast an older story gives up its place to newer ones
MIN_SCORE = 6          # outlet credit (tier 1 = 4, tier 2 = 3, tier 3 = 1.5 each), +2 if a major outlet, +topic strength (max 4); the outlet rule (sourcing.passes_strict_rule) is applied as well
USE_COVERS = os.environ.get("USE_COVERS", "0") == "1"   # outlets' photos are off: only our own map, flags and emblems are shown
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "").strip()
GNEWS_KEY = os.environ.get("GNEWS_KEY", "").strip()
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
UA = "WarEventsNewsBot/1.0 (+https://www.warevents.com)"

# Google News search limited to one site, economy terms, last 24 hours. Titles end in " - Reuters" etc.
# (trimmed when read); links go via news.google.com.
ECON_TERMS = ('inflation OR rates OR "central bank" OR jobs OR unemployment OR earnings OR markets OR stocks '
              'OR tariff OR GDP OR recession')
GN = ("https://news.google.com/rss/search?q=site:{}+(" + urllib.parse.quote_plus(ECON_TERMS)
      + ")+when:1d&hl=en-US&gl=US&ceid=US:en")
RSS_FEEDS = [
    ("BBC News", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("The Guardian", "https://www.theguardian.com/business/rss"),
    ("The Guardian", "https://www.theguardian.com/business/economics/rss"),
    ("Financial Times", "https://www.ft.com/global-economy?format=rss"),
    ("Financial Times", "https://www.ft.com/markets?format=rss"),
    ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
    ("Bloomberg", "https://feeds.bloomberg.com/economics/news.rss"),
    ("The Wall Street Journal", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain"),
    ("The Wall Street Journal", "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness"),
    ("The Economist", "https://www.economist.com/finance-and-economics/rss.xml"),
    ("CNBC", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),     # economy
    ("CNBC", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),     # finance
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_bulletins"),
    # more established newsrooms' business pages (added in the replay: with only the list above, too few
    # stories reached three different outlets)
    ("The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    ("The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml"),
    ("The Washington Post", "https://feeds.washingtonpost.com/rss/business"),
    ("NPR", "https://feeds.npr.org/1006/rss.xml"),
    ("DW", "https://rss.dw.com/rdf/rss-en-bus"),
    ("Sky News", "https://feeds.skynews.com/feeds/rss/business.xml"),
    ("France 24", "https://www.france24.com/en/business-tech/rss"),
    ("Euronews", "https://www.euronews.com/rss?level=vertical&name=business"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("SCMP", "https://www.scmp.com/rss/92/feed"),
    ("CNA", "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936"),
    # business and markets specialists, and the main business titles of Canada, Australia, India, Singapore, the Gulf
    ("Fortune", "https://fortune.com/feed/fortune-feeds/?id=3230629"),
    ("Forbes", "https://www.forbes.com/business/feed/"),
    ("Business Insider", "https://feeds.businessinsider.com/custom/all"),
    ("Axios", "https://api.axios.com/feed/"),
    ("Fox Business", "https://moxie.foxbusiness.com/google-publisher/economy.xml"),
    ("City AM", "https://www.cityam.com/feed/"),
    ("The Globe and Mail", "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/"),
    ("Australian Financial Review", "https://www.afr.com/rss/feed.xml"),
    ("The Economic Times", "https://economictimes.indiatimes.com/rssfeedsdefault.cms"),
    ("The Business Times", "https://www.businesstimes.com.sg/rss/top-stories"),
    ("The National", "https://www.thenationalnews.com/arc/outboundfeeds/rss/category/business/?outputType=xml"),
    ("The Bell", "https://en.thebell.io/rss/"),                  # Russia's independent business newsroom
    ("DigiTimes Asia", "https://www.digitimes.com/rss/daily.xml"),   # Taiwan's chip and electronics trade paper
    # Reuters and AP have no public RSS; Nikkei Asia's own feed carries no dates. All three via Google News.
    ("Reuters", GN.format("reuters.com")),
    ("AP", GN.format("apnews.com")),
    ("Nikkei Asia", GN.format("asia.nikkei.com")),
    # the other top-tier newsrooms, searched the same way (catches economy stories outside their business feeds)
    ("BBC News", GN.format("bbc.com")),
    ("Al Jazeera", GN.format("aljazeera.com")),
    ("The Guardian", GN.format("theguardian.com")),
    ("Financial Times", GN.format("ft.com")),
    ("Bloomberg", GN.format("bloomberg.com")),
    # no working public feed (blocked, dead, undated or weeks stale): searched the same way
    ("Barron's", GN.format("barrons.com")),
    ("Yahoo Finance", GN.format("finance.yahoo.com")),
    ("CNN", GN.format("cnn.com")),
    ("Financial Post", GN.format("financialpost.com")),
    ("Business Standard", GN.format("business-standard.com")),
    ("Caixin Global", GN.format("caixinglobal.com")),
    ("BusinessLIVE", GN.format("businesslive.co.za")),
    ("Mint", GN.format("livemint.com")),
    ("The Telegraph", GN.format("telegraph.co.uk")),
    # the major economies' own newsrooms in English: China, Japan, South Korea, Russia, India, Taiwan, Canada,
    # Australia, the Gulf, Turkey, Indonesia. State media of one government count once (sourcing.STATE_MEDIA).
    ("China Daily", GN.format("chinadaily.com.cn")),
    ("Xinhua", GN.format("english.news.cn")),
    ("Japan Times", GN.format("japantimes.co.jp")),
    ("Kyodo News", GN.format("english.kyodonews.net")),
    ("NHK World", GN.format("www3.nhk.or.jp")),
    ("Yonhap", GN.format("en.yna.co.kr")),
    ("The Korea Herald", GN.format("koreaherald.com")),
    ("The Moscow Times", GN.format("themoscowtimes.com")),
    ("TASS", GN.format("tass.com")),
    ("The Hindu BusinessLine", GN.format("thehindubusinessline.com")),
    ("Moneycontrol", GN.format("moneycontrol.com")),
    ("Focus Taiwan", GN.format("focustaiwan.tw")),
    ("Taipei Times", GN.format("taipeitimes.com")),
    ("CBC News", GN.format("cbc.ca")),
    ("BNN Bloomberg", GN.format("bnnbloomberg.ca")),
    ("Arab News", GN.format("arabnews.com")),
    ("ABC News (Australia)", GN.format("abc.net.au")),
    ("Daily Sabah", GN.format("dailysabah.com")),
    ("The Jakarta Post", GN.format("thejakartapost.com")),
]
GDELT_DOMAINS = ["reuters.com", "apnews.com", "ft.com", "bloomberg.com", "aljazeera.com", "bbc.com", "bbc.co.uk"]
GDELT_TERMS = ["inflation", "\"interest rates\"", "\"central bank\"", "unemployment", "earnings", "tariffs",
               "GDP", "recession", "\"stock market\"", "\"bond yields\"", "\"oil prices\"", "OPEC", "jobs"]

OUTLETS = {
    "barrons.com": "Barron's", "fortune.com": "Fortune", "forbes.com": "Forbes", "businessinsider.com": "Business Insider",
    "finance.yahoo.com": "Yahoo Finance", "axios.com": "Axios", "foxbusiness.com": "Fox Business",
    "telegraph.co.uk": "The Telegraph", "cityam.com": "City AM", "financialpost.com": "Financial Post",
    "theglobeandmail.com": "The Globe and Mail", "afr.com": "Australian Financial Review",
    "economictimes.indiatimes.com": "The Economic Times", "livemint.com": "Mint",
    "business-standard.com": "Business Standard", "caixinglobal.com": "Caixin Global",
    "businesstimes.com.sg": "The Business Times", "businesslive.co.za": "BusinessLIVE",
    "chinadaily.com.cn": "China Daily", "english.news.cn": "Xinhua", "english.kyodonews.net": "Kyodo News",
    "www3.nhk.or.jp": "NHK World", "koreaherald.com": "The Korea Herald", "tass.com": "TASS",
    "thehindubusinessline.com": "The Hindu BusinessLine", "moneycontrol.com": "Moneycontrol",
    "focustaiwan.tw": "Focus Taiwan", "taipeitimes.com": "Taipei Times", "cbc.ca": "CBC News",
    "bnnbloomberg.ca": "BNN Bloomberg", "abc.net.au": "ABC News (Australia)", "thejakartapost.com": "The Jakarta Post",
    "thebell.io": "The Bell", "digitimes.com": "DigiTimes Asia",
    "reuters.com": "Reuters", "apnews.com": "AP", "bbc.co.uk": "BBC News", "bbc.com": "BBC News",
    "aljazeera.com": "Al Jazeera", "theguardian.com": "The Guardian", "ft.com": "Financial Times",
    "bloomberg.com": "Bloomberg", "dw.com": "DW", "france24.com": "France 24", "npr.org": "NPR",
    "politico.eu": "Politico Europe", "politico.com": "Politico", "nytimes.com": "The New York Times",
    "washingtonpost.com": "The Washington Post", "wsj.com": "The Wall Street Journal",
    "economist.com": "The Economist", "cnn.com": "CNN", "scmp.com": "South China Morning Post",
    "asia.nikkei.com": "Nikkei Asia", "cnbc.com": "CNBC", "marketwatch.com": "MarketWatch",
    "arabnews.com": "Arab News", "thenationalnews.com": "The National",
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
    "cgtn.com": "CGTN", "presstv.ir": "Press TV", "presstv.co.uk": "Press TV", "farsnews.ir": "Fars", "mehrnews.com": "Mehr News",
}
TIER1 = {"Reuters", "AP", "BBC News", "Al Jazeera", "The Guardian", "Financial Times", "Bloomberg"}
PRIORITY = ["Reuters", "AP", "Bloomberg", "Financial Times", "The Wall Street Journal", "BBC News", "The Guardian",
            "The New York Times", "The Economist", "Nikkei Asia", "The Washington Post", "Al Jazeera", "NPR", "DW",
            "France 24", "Sky News", "CNBC", "MarketWatch"]

TOPICS = {
    "markets": ["stock", "stocks", "shares", "equities", "equity market", "bond", "bonds", "bond yield", "treasury",
                "treasuries", "wall street", "dow", "s&p 500", "nasdaq", "ftse", "nikkei", "dax", "hang seng",
                "stock market", "markets", "investor", "selloff", "sell-off", "rally", "currency", "dollar", "euro",
                "yen", "yuan", "sterling", "bitcoin", "crypto", "gold price", "ipo", "hedge fund", "volatility",
                "yields", "credit market", "private credit"],
    "rates": ["central bank", "federal reserve", "fed", "ecb", "bank of england", "bank of japan", "boj", "pboc",
              "reserve bank", "interest rate", "rate cut", "rate hike", "rates", "monetary policy", "powell", "lagarde"],
    "inflation": ["inflation", "cpi", "consumer price", "deflation", "price index", "cost of living", "price rise"],
    "jobs": ["jobs", "job", "unemployment", "jobless", "payroll", "labor market", "labour market", "wage", "layoff",
             "job cut", "hiring", "workforce"],
    "companies": ["earnings", "profit", "revenue", "quarterly", "forecast", "guidance", "merger", "acquisition",
                  "takeover", "buyout", "bankruptcy", "ceo", "shareholder", "dividend", "valuation", "antitrust",
                  "chipmaker", "carmaker", "automaker", "lender", "banks", "investment", "company", "companies",
                  "business", "businesses", "industry", "chief executive", "billion", "trillion", "insurer",
                  "rescue deal", "data center", "data centre",
                  # the biggest listed companies: news about them is business news even without a money word
                  "nvidia", "apple", "microsoft", "tesla", "alphabet", "google", "meta", "openai", "boeing",
                  "airbus", "toyota", "volkswagen", "samsung", "tsmc", "intel", "jpmorgan", "goldman sachs",
                  "berkshire", "walmart", "exxon", "saudi aramco", "alibaba", "tencent", "byd"],
    "trade": ["tariff", "trade deal", "trade war", "export", "import", "trade deficit", "trade surplus", "sanction",
              "wto", "supply chain", "customs dut"],
    "housing": ["housing", "house price", "home price", "home sales", "mortgage", "property market", "rent",
                "real estate", "homebuilder"],
    "finance": ["pension", "tax", "taxes", "budget", "savings", "credit card", "debt", "student loan",
                "social security", "minimum wage", "benefits"],
    "energy": ["oil price", "crude", "brent", "opec", "gas price", "petrol price", "fuel price", "energy price", "diesel",
               "gasoline", "prices",
               "energy bill", "electricity price", "lng", "commodity", "commodities"],
    "macro": ["gdp", "economy", "economic", "economies", "recession", "growth", "deficit", "debt ceiling", "fiscal",
              "imf", "world bank", "stimulus", "manufacturing", "pmi", "retail sales", "consumer spending",
              "consumer confidence"],
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
    r"series finale",
    r"reality tv",
    r"royal baby",
    r"prince harry",
    r"meghan",
    r"influencers?",
    r"tiktok star",
    r"recipe",
    r"cooking",
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
    r"junior doctors",
    r"flight delays",
    r"nhs",
    r"hospital waiting",
    r"gp appointments",
    r"exam results",
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
    r"gadget",
    r"video game",
    r"gaming",
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
    r"smoking ban",
    # Economy additions: stock tips and price targets, product deals and reviews, more sport, celebrity, local crime
    r"price targets?",
    r"stocks? to buy",
    r"shares? to buy",
    r"should you buy",
    r"time to buy",
    r"buy (?:the|this) dip",
    r"best stocks?",
    r"top stocks?",
    r"stock picks?",
    r"penny stocks?",
    r"dividend stocks?",
    r"growth stocks?",
    r"retire early",
    r"motley fool",
    r"zacks",
    r"buy rating",
    r"(?:analyst|analysts) (?:upgrades?|downgrades?)",
    r"best deals?",
    r"deals? of the day",
    r"black friday deals?",
    r"cyber monday",
    r"discount codes?",
    r"promo codes?",
    r"coupons?",
    r"gift guide",
    r"buying guide",
    r"hands-on",
    r"unboxing",
    r"striker",
    r"goalkeeper",
    r"cup final",
    r"super bowl",
    r"playoffs?",
    r"touchdown",
    r"transfer fee",
    r"season tickets?",
    r"kardashians?",
    r"taylor swift",
    r"lottery",
    r"jackpot",
    r"powerball",
    r"fed up",
    r"shot dead",
    r"mass shooting",
    r"fatal shooting",
    r"homicide",
    r"carjacking",
    r"profile and biography"   # Bloomberg's people pages, which its Google News search returns
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
        {"category": "business", "language": "en", "pageSize": "100", "apiKey": NEWSAPI_KEY})
    data = json.loads(http_get(url))
    return [{"title": x.get("title"), "desc": x.get("description"), "url": x.get("url"),
             "time": parse_time(x.get("publishedAt")), "cover": x.get("urlToImage"), "outlet": outlet_for(x.get("url"))}
            for x in data.get("articles", [])]


def from_gnews():
    url = "https://gnews.io/api/v4/top-headlines?" + urllib.parse.urlencode(
        {"category": "business", "lang": "en", "max": "50", "apikey": GNEWS_KEY})
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


def is_economy(title, desc):
    """The keyword pre-filter: an economy topic word, and nothing from the exclude list in the headline."""
    return not EXCLUDE_RX.search(title or "") and bool(topic_hits(title or "", desc or ""))


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
    place = article_place(title, desc, institutions=True)   # may be None: enrich_stories.py places it later or drops it
    place_from = "" if not place else "title" if locate(title) else "inst" if institution_place(title) else "desc"
    cover = a.get("cover") if USE_COVERS else None
    if cover and not cover.startswith("https://"):
        cover = None
    return {"key": url_key(url), "url": url, "title": title, "outlet": a.get("outlet") or outlet_for(url),
            "time": iso(t), "cover": cover, "place": place["label"] if place else "", "placeFrom": place_from, "topics": topics}


TOPIC_DEFINITION = (
    "economy and markets news: stock, bond and currency markets, central banks and interest rates, inflation and "
    "prices, jobs, wages and unemployment, GDP, growth and recessions, company earnings, deals and other big corporate "
    "news, trade and tariffs, housing markets, personal finance policy (taxes, pensions, benefits, debt), and energy "
    "and commodity prices. "
    "NOT: stock tips, price targets or 'stocks to buy' advice, product deals, reviews or launches, sport (including "
    "club finances and transfers), celebrity news, local crime, or war and politics without a clear economic angle.")


def relevance_key(title):
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())[:90]


def ai_relevant(arts, cache):
    """Ask Claude Haiku (no web search) which NEW headlines are really economy news; cached answers are reused.
    Same pattern as fetch_topic_news.ai_keep. Without ANTHROPIC_API_KEY no request is made at all and the
    keyword filter decides alone."""
    new, seen = [], set()
    for a in arts:
        k = relevance_key(a["title"])
        if k not in cache and k not in seen:
            seen.add(k)
            new.append(a)
    if new and ANTHROPIC_KEY:
        for start in range(0, len(new), 60):
            batch = new[start:start + 60]
            lst = "\n".join(f"{n}. {a['title']} ({a['outlet']})" for n, a in enumerate(batch))
            prompt = (f"A news site has a page only about {TOPIC_DEFINITION}\n\nWhich of these headlines belong on that page?\n{lst}\n\n"
                      "Return ONLY a JSON array of the numbers that belong, e.g. [0, 3]. Return [] if none.")
            try:
                body = json.dumps({"model": MODEL, "max_tokens": 400,
                                   # simple yes/no task: no thinking and low effort keeps it cheap + fast (as in enrich_stories.py)
                                   "thinking": {"type": "disabled"}, "output_config": {"effort": "low"},
                                   "messages": [{"role": "user", "content": prompt}]}).encode()
                req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
                    "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
                with urllib.request.urlopen(req, timeout=90) as r:
                    out = json.loads(r.read())
                    usage.record(out)
                txt = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
                m = re.search(r"\[[\d,\s]*\]", txt)
                ok = set(json.loads(m.group(0))) if m else None
            except Exception as ex:
                log(f"  AI check failed ({str(ex)[:60]}); keyword filter decides for now")
                ok = None
            if ok is None:
                continue
            for n, a in enumerate(batch):
                cache[relevance_key(a["title"])] = n in ok
        log(f"  AI check (economy): {sum(1 for a in new if cache.get(relevance_key(a['title'])))} of {len(new)} new headlines kept")
    elif new:
        log(f"  no ANTHROPIC_API_KEY: keyword filter only for {len(new)} new headlines")
    return [a for a in arts if cache.get(relevance_key(a["title"]), True)]


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
            same_place = bool(a["place"]) and country_of(a["place"]) in g["places"]   # same country (both placed), so a sharper pin never splits a story
            if not any(same_story(tk, m, same_place) for m in g["tokens"]):
                continue
            j = max(jaccard(tk, m) for m in g["tokens"]) + (0.2 if same_place else 0)
            if j > best_j:
                best, best_j = g, j
        if best:
            best["arts"].append(a); best["tokens"].append(tk)
            if a["place"]:
                best["places"].add(country_of(a["place"]))
        else:
            groups.append({"arts": [a], "tokens": [tk], "places": {country_of(a["place"])} if a["place"] else set()})
    return groups


def rank(a):
    # best-ranked outlet first: tier, then the PRIORITY order within it
    return (ranking.tier(a["outlet"]), PRIORITY.index(a["outlet"]) if a["outlet"] in PRIORITY else len(PRIORITY))


def place_from(a):
    """Where an article's place was found: "title", "inst" (an institution in the headline) or "desc".
    Articles stored before placeFrom existed are judged from their headline."""
    if a.get("placeFrom"):
        return a["placeFrom"]
    t = a.get("title") or ""
    return "title" if locate(t) else "inst" if institution_place(t) else "desc"


def story_place(arts):
    """The story's pin. Countries vote first, a place found in a headline (or a headline institution) counting
    twice as much as one found only in a description, so a country a few descriptions mention in passing can't
    take the pin. Inside the winning country, a city or region wins when 2+ articles agree on it (and it has at
    least half the top label's count) or every article there names it; otherwise the country itself.
    No article placed: an empty pin, which enrich_stories.py fills from the AI's country (or drops the story)."""
    arts = [a for a in arts if a.get("place") in PLACES]
    if not arts:
        return {"label": "", "cat": "", "lat": None, "lon": None}
    countries = Counter()
    for a in arts:
        countries[country_of(PLACES[a["place"]]["label"])] += 2 if place_from(a) in ("title", "inst") else 1
    country = countries.most_common(1)[0][0]
    inside = [a for a in arts if country_of(PLACES[a["place"]]["label"]) == country]
    votes = Counter(PLACES[a["place"]]["label"] for a in inside)
    top_label, top_n = votes.most_common(1)[0]
    sharp = sorted(((n, -i, l) for i, (l, n) in enumerate(votes.items()) if PLACES[l]["spec"] >= 2), reverse=True)
    if sharp:
        n, _, label = sharp[0]
        if (n >= 2 and n * 2 >= top_n) or n == len(inside):
            return PLACES[label]
    return PLACES[country] if country in PLACES else PLACES[top_label]


def build_story(g, now):
    arts = g["arts"]
    first = min(arts, key=lambda a: a["time"])
    newest = max(arts, key=lambda a: a["time"])
    # A story still developing a day later (new reports keep joining the cluster) is ranked and
    # shown by its latest reporting, not frozen at the first article, or it sinks off the page.
    rolled = (parse_time(newest["time"]) - parse_time(first["time"])) > timedelta(hours=ROLL_HOURS)
    pool = [a for a in arts if parse_time(newest["time"]) - parse_time(a["time"]) <= timedelta(hours=ROLL_HOURS)] if rolled else arts
    # The lead article (headline, Source link, "Read original") must be about the story's main event. Articles
    # that match few others in the group were only pulled in loosely (a related angle, a reaction), so the lead
    # comes from the ones most alike, and a written article beats a video page.
    toks = [story_tokens(a["title"]) for a in pool]
    alike = [sum(1 for j in range(len(pool)) if j != i and same_story(toks[i], toks[j], bool(pool[i]["place"] and pool[j]["place"]) and country_of(pool[i]["place"]) == country_of(pool[j]["place"])))
             for i in range(len(pool))]
    best = max(alike) if alike else 0
    core = [a for a, n in zip(pool, alike) if n >= best * 0.5] if best else pool
    written = [a for a in core if "/video/" not in (a.get("url") or "")] or core
    rep = min(written, key=lambda a: (rank(a), a["time"]))
    if rolled:
        first = min(pool, key=lambda a: a["time"])
    outlets = []
    # the outlet named on the story is always the one its Source link opens, so rep goes first
    for a in [rep] + sorted(arts, key=rank):
        if a["outlet"] not in outlets:
            outlets.append(a["outlet"])
    topics = Counter()
    for a in arts:
        topics.update(a["topics"])
    # Big, established newsrooms count for more; a story only a small outlet carries rarely makes the cut.
    score = round(sum(ranking.weight(o) for o in outlets) + min(4, sum(topics.values()))
                  + (2 if any(ranking.tier(o) == 1 for o in outlets) else 0), 1)
    place = story_place(arts)
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
        "textUrls": [a["url"] for a in [rep] + sorted(arts, key=rank) if a.get("url") and "news.google.com" not in a["url"]][:3],
        "outlets": outlets,
        # every article in the cluster (outlet, time, headline), oldest first: feeds the Coverage & Bias tab
        "coverage": [dict({"o": a["outlet"], "t": a["time"], "h": a["title"]}, **({"u": a["url"]} if a.get("url") and "news.google.com" not in a["url"] else {})) for a in sorted(arts, key=lambda x: x["time"])][:24],
        "topics": [k for k, _ in topics.most_common()],
        "score": score,
        "_keys": [a["key"] for a in arts],
    }
    cover = rep.get("cover") or next((a["cover"] for a in arts if a.get("cover")), None)
    if cover:
        s["cover"] = cover
    return s


def carry_ids(stories, previous):
    """Keep each story's id from one run to the next. A story is named after its first article, and as a long
    story rolls on (or its first articles age out) that article changes, so the id would too: the app then
    re-alerts the same story, links to it stop working, and the summaries cache keyed by id is redone. A new
    story that shares articles (outlet and headline) with a story in the previous feed keeps that story's id."""
    owners = {}
    for p in previous if isinstance(previous, list) else []:
        if isinstance(p, dict) and p.get("auto") and p.get("id"):
            for c in p.get("coverage") or []:
                owners.setdefault((c.get("o"), c.get("h")), p["id"])
    taken = set()
    # Strongest first, so when two new stories both share articles with one old story, the bigger keeps its id.
    for s in sorted(stories, key=lambda s: s["score"], reverse=True):
        votes = Counter(owners[k] for k in ((c.get("o"), c.get("h")) for c in s["coverage"]) if k in owners)
        for pid, _ in votes.most_common():
            if pid not in taken:
                s["id"] = pid
                break
        taken.add(s["id"])


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
    if s["id"] in rules["ids"] or rules["keys"] & set(s.get("_keys") or []):
        return True
    head = html.unescape(s["headline"]).lower()
    return any(p in head for p in rules["phrases"])


def keep(stories, rules):
    """The story filter: score, the strict outlet rule (3+ different outlets, sister brands merged) and remove.txt."""
    return [s for s in stories if s["score"] >= MIN_SCORE and passes_strict_rule(s["outlets"])
            and not (rules and removed(s, rules))]


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
    fresh = {}
    # An outlet read twice (its own feed and a Google News search) gives the same article two links:
    # keep the first (the feeds come first in RSS_FEEDS, so the direct link wins).
    same = {(a.get("outlet"), a.get("title")) for a in store.values()}
    for a in raw:
        q = qualify(a, now)
        if q and q["key"] not in store and (q["outlet"], q["title"]) not in same:
            same.add((q["outlet"], q["title"]))
            fresh[q["key"]] = q
    relevance = load_json(RELEVANCE, {})
    if not isinstance(relevance, dict):
        relevance = {}
    fresh = ai_relevant(list(fresh.values()), relevance)
    if len(relevance) > 4000:   # keep the cache small
        relevance = dict(list(relevance.items())[-3000:])
    write_if_changed(RELEVANCE, relevance)
    added = 0
    for q in fresh:
        store[q["key"]] = q
        added += 1
    keep_after = now - timedelta(hours=STORE_HOURS)
    for a in store.values():   # a place renamed in the gazetteer (accents added) keeps its stored articles
        if a.get("place") in PLACES:
            a["place"] = PLACES[a["place"]]["label"]
    kept = [a for a in store.values()
            if (a.get("place") == "" or a.get("place") in PLACES) and (parse_time(a.get("time")) or now) >= keep_after]
    kept.sort(key=lambda a: a["time"], reverse=True)
    write_if_changed(STORE, kept)

    show_after = now - timedelta(hours=MAX_AGE_HOURS)
    recent = [a for a in kept if parse_time(a["time"]) >= show_after]
    rules = load_remove()
    stories = [build_story(g, now) for g in cluster(recent)]
    carry_ids(stories, load_json(OUTPUT, []))
    stories = keep(stories, rules)
    # Rank by importance AND freshness: a story's score halves every FRESH_HALF_LIFE hours, so a
    # big story from yesterday morning no longer blocks today's news, but still beats a minor new one.
    def fresh_rank(s):
        age_h = max(0.0, (now - (parse_time(s["time"]) or now)).total_seconds() / 3600)
        return s["score"] * 0.5 ** (age_h / FRESH_HALF_LIFE)
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
