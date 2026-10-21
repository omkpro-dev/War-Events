#!/usr/bin/env python3
"""
Pulls the news RSS feeds below and writes wire_ticker.json -- the file the
homepage's WIRE ticker already reads (HEADLINE_SOURCE in index.html).

Browsers can't read other sites' RSS directly (cross-origin), so this runs
on the server instead, e.g. every 10 minutes from cron:

    */10 * * * *  cd /path/to/site && python3 fetch_rss_feeds.py

Standard library only -- nothing to install. To add a feed, add a line to
FEEDS: (label shown in the ticker, feed URL).
"""
import json, os, re, sys, tempfile, html, time, random
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "news-feed" else os.path.dirname(os.path.abspath(__file__)), "news-feed"))
from dedupe import dedupe, same_story, tokens as story_tokens
from topics import is_geopolitical   # drops local crime, courts, accidents, sport, celebrity

FEEDS = [
    ("DefenceTalk", "https://www.defencetalk.com/feed/"),
    ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Guardian", "https://www.theguardian.com/world/rss"),
    ("DW", "https://rss.dw.com/rdf/rss-en-world"),
    ("Defense News", "https://www.defensenews.com/arc/outboundfeeds/rss/"),
    ("France 24", "https://www.france24.com/en/rss"),
    ("NPR", "https://feeds.npr.org/1004/rss.xml"),
    ("Sky News", "https://feeds.skynews.com/feeds/rss/world.xml"),
    ("UN News", "https://news.un.org/feed/subscribe/en/news/topic/peace-and-security/feed/rss.xml"),
    ("RFE/RL", "https://www.rferl.org/api/zrqiteuuir"),
    ("Kyiv Independent", "https://kyivindependent.com/news-archive/rss/"),
    ("Times of Israel", "https://www.timesofisrael.com/feed/"),
    ("The Diplomat", "https://thediplomat.com/feed/"),
    ("Breaking Defense", "https://breakingdefense.com/feed/"),
    ("The War Zone", "https://www.twz.com/feed"),
    ("UK Defence Journal", "https://ukdefencejournal.org.uk/feed/"),
    ("RT", "https://www.rt.com/rss/news/"),
    ("Sputnik", "https://sputnikglobe.com/export/rss2/archive/index.xml"),
    ("Xinhua", "https://english.news.cn/rss/worldrss.xml"),
    ("China Daily", "https://www.chinadaily.com.cn/rss/world_rss.xml"),
    ("CGTN", "https://www.cgtn.com/subscribe/rss/section/world.xml"),
    ("Global Times", "https://www.globaltimes.cn/rss/outbrain.xml"),
    ("TASS", "https://tass.com/rss/v2.xml"),
]

# Defence / security-only outlets: everything they run is on-topic unless it's plainly local news.
TRUSTED = {"DefenceTalk", "Defense News", "UN News", "Breaking Defense", "The War Zone", "UK Defence Journal"}

OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wire_ticker.json")
MAX_ITEMS = 24          # newest first, across all feeds
MAX_AGE_HOURS = 72      # drop anything older than this
TIMEOUT = 15
UA = "Mozilla/5.0 (compatible; WarEventsBot/1.0; +https://www.warevents.com)"

ATOM = "{http://www.w3.org/2005/Atom}"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", "", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def parse_date(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)                      # RSS: "Fri, 13 Mar 2026 14:29:45 +0000"
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))   # Atom: ISO 8601
        except Exception:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def first_image(raw_html):
    m = re.search(r'<img[^>]+src="([^"]+)"', raw_html or "")
    return m.group(1) if m else None


def parse_feed(label, data):
    root = ET.fromstring(data)
    items = []
    for it in root.iter("item"):                          # RSS 2.0
        desc = it.findtext("description") or ""
        items.append({
            "title": clean(it.findtext("title")),
            "link": (it.findtext("link") or "").strip(),
            "date": parse_date(it.findtext("pubDate")),
            "image": first_image(desc),
            "tags": [clean(c.text) for c in it.findall("category") if c.text],
        })
    for it in root.iter(ATOM + "entry"):                  # Atom
        link = it.find(ATOM + "link")
        items.append({
            "title": clean(it.findtext(ATOM + "title")),
            "link": link.get("href") if link is not None else "",
            "date": parse_date(it.findtext(ATOM + "updated") or it.findtext(ATOM + "published")),
            "image": None,
            "tags": [],
        })
    for i in items:
        i["source"] = label
    return items


def main():
    now = datetime.now(timezone.utc)
    collected, seen = [], set()
    for label, url in FEEDS:
        time.sleep(random.uniform(1.5, 4))   # polite spacing between sites
        try:
            items = parse_feed(label, fetch(url))
        except Exception as e:
            print(f"[skip] {label}: {e}", file=sys.stderr)
            continue
        for i in items:
            key = (i["link"] or i["title"]).lower()
            if not i["title"] or key in seen:
                continue
            if not is_geopolitical(i["title"], trusted=label in TRUSTED):
                continue
            if i["date"] and (now - i["date"]).total_seconds() > MAX_AGE_HOURS * 3600:
                continue
            seen.add(key)
            collected.append(i)

    if not collected:
        print("No feed items fetched -- leaving the existing wire_ticker.json in place.", file=sys.stderr)
        return 1

    collected.sort(key=lambda i: i["date"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    collected = dedupe(collected)   # one event from several outlets shows once
    # Interleave sources so one busy feed (e.g. DefenceTalk) can't fill the whole banner.
    by_src = {}
    for i in collected:
        by_src.setdefault(i["source"], []).append(i)
    mixed = []
    while any(by_src.values()):
        for src in list(by_src):
            if by_src[src]:
                mixed.append(by_src[src].pop(0))
    collected = mixed

    # Same shape as a WordPress REST posts response, which is what the
    # ticker in index.html parses (title.rendered, link, first term name).
    out = [{
        "title": {"rendered": i["title"]},
        "link": i["link"],
        "date": i["date"].isoformat() if i["date"] else None,
        "image": i["image"],
        "tags": i["tags"],
        "_embedded": {"wp:term": [[{"name": i["source"]}]]},
    } for i in collected[:MAX_ITEMS]]

    # Write to a temp file then swap, so the site never reads a half-written file.
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT_FILE), suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_FILE)
    print(f"Wrote {len(out)} headlines to {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
