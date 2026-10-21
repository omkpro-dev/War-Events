"""Latest Events FEED panel -> latest_reports.json (newest conflict/geopolitics headlines).

Shape per item (what index.html's renderReports expects):
  { name, handle, category, severity, time (ISO), text, cc: [ISO2...], permalink }
Standard library only. Runs every 15 minutes from .github/workflows/update-wire.yml.
"""
import html, json, os, re, time, random, urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from urllib.parse import urlparse
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "news-feed" else os.path.dirname(os.path.abspath(__file__)), "news-feed"))
from dedupe import dedupe, same_story, tokens as story_tokens
import outlets as ranking

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "latest_reports.json")
NAMES = json.load(open(os.path.join(ROOT, "news-feed", "country_iso2.json"), encoding="utf-8"))
GN = ("https://news.google.com/rss/search?q=site:{}+(war+OR+military+OR+troops+OR+missile+OR+sanctions"
      "+OR+ceasefire+OR+minister+OR+president+OR+election+OR+attack)+when:1d&hl=en-US&gl=US&ceid=US:en")
GN_HANDLE = {"Reuters": "reuters.com", "AP": "apnews.com", "Xinhua": "news.cn", "People's Daily": "people.cn",
             "China Daily": "chinadaily.com.cn", "Fars": "farsnews.ir"}   # Google News links hide the real site
FEEDS = [
    ("BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("DW", "https://rss.dw.com/rdf/rss-en-world"),
    ("France 24", "https://www.france24.com/en/rss"),
    ("Defense News", "https://www.defensenews.com/arc/outboundfeeds/rss/"),
    ("DefenceTalk", "https://www.defencetalk.com/feed/"),
    ("NPR", "https://feeds.npr.org/1004/rss.xml"),
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
    ("Mehr News", "https://en.mehrnews.com/rss"),   # Iranian state agency; its own feed works
]
from topics import GEO, is_geopolitical   # shared with the Wire ticker
ESC = re.compile(r"\b(attack|strike|airstrike|missile|invasion|offensive|killed|shelling|clashes|escalat)", re.I)
DEESC = re.compile(r"\b(ceasefire|truce|peace|talks|deal|agreement|withdraw|de-escalat|release)", re.I)
CATS = [("Nuclear", r"nuclear"), ("Maritime", r"navy|ship|strait|maritime|vessel"), ("Diplomacy", r"talks|summit|envoy|diplomat|treaty"),
        ("Sanctions", r"sanction|tariff"), ("Defence", r"defen[cs]e|procure|army|military"), ("Conflict", r".")]
UA = {"User-Agent": "WarEventsNewsBot/1.0 (+https://www.warevents.com)"}   # same as fetch_news.py; Cloudflare sites block the old one
KEYS = sorted(NAMES, key=len, reverse=True)
NAME_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in KEYS) + r")\b")


def items(label, url):
    time.sleep(random.uniform(1.5, 4))   # polite spacing between sites
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            body = r.read()
        end = max(body.rfind(b"</rss>"), body.rfind(b"</feed>"), body.rfind(b"</rdf:RDF>"))
        root = ET.fromstring(body[:body.index(b">", end) + 1] if end > 0 else body)   # drop anything a CDN tacks on after the feed
    except Exception as e:
        print("feed fail", label, e)
        return []
    out = []
    for it in root.iter():
        if not it.tag.endswith("item"):
            continue
        get = lambda n: next((c.text or "" for c in it if c.tag.split("}")[-1] == n), "")
        title = html.unescape(re.sub(r"<[^>]+>", "", get("title"))).strip()
        if "news.google.com" in url:   # "Headline - Reuters" -> "Headline"
            title = re.sub(r"\s+-\s+[^-]{2,30}$", "", title)
            title = re.sub(r"^Farsnews\s*\|\s*", "", title)
        if not title or not is_geopolitical(title, trusted=label in ("Defense News", "DefenceTalk")):
            continue
        d = get("pubDate") or get("date")
        try:
            t = parsedate_to_datetime(d) if "," in d else datetime.fromisoformat(d.replace("Z", "+00:00"))
        except Exception:   # undated feeds (Press TV): take the day from links like /2026/10/21/, else now
            m = re.search(r"/(20\d\d)/(\d\d)/(\d\d)/", get("link"))
            t = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, tzinfo=timezone.utc) if m else datetime.now(timezone.utc)
        desc = html.unescape(re.sub(r"<[^>]+>", "", get("description"))).strip()
        link = get("link").strip()
        cc = []
        for m in NAME_RE.findall(title + " " + desc[:200]):
            c = NAMES[m]
            if c not in cc:
                cc.append(c)
        cat = next(n for n, p in CATS if re.search(p, title, re.I))
        out.append({
            "name": label, "handle": GN_HANDLE.get(label) if "news.google.com" in url else urlparse(link).netloc.replace("www.", "") or label,
            "category": cat, "severity": "escalation" if ESC.search(title) else "de-escalation" if DEESC.search(title) else "development",
            "time": t.astimezone(timezone.utc).isoformat(), "text": title + (" — " + desc[:180] if desc and desc[:40] not in title else ""),
            "cc": cc[:4], "permalink": link,
        })
    return out


def main():
    allit = [x for lab, u in FEEDS for x in items(lab, u)]
    allit.sort(key=lambda x: x["time"], reverse=True)
    # Same story from several outlets: show it once, credited to the best-ranked outlet that carried it.
    out, toks = [], []
    for x in allit:
        tk = story_tokens(x["text"].split(" — ")[0])
        hit = next((i for i, t in enumerate(toks) if same_story(tk, t)), None)
        if hit is None:
            out.append(x); toks.append(tk)
        elif ranking.tier(x["name"]) < ranking.tier(out[hit]["name"]):
            out[hit] = x
    out.sort(key=lambda x: x["time"], reverse=True)
    # Lesser-known / very high-volume outlets get at most 2 items, regional ones at most 5.
    out = ranking.apply_caps(out, lambda x: x["name"])
    out = out[:30]
    if out:
        json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("reports:", len(out))


if __name__ == "__main__":
    main()
