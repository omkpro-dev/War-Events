"""Natural disasters + air quality for the Disasters globe (?view=disasters). No AI, standard library only.

Sources (all free):
  GDACS (EU JRC / UN)     main alert layer: Red / Orange / Green events, past storm tracks
  USGS + EMSC             earthquakes (EMSC adds Europe, Middle East, North Africa)
  NOAA NHC + US Navy JTWC live storms: position, strength, official forecast track
  NASA FIRMS              wildfire hot spots (needs a free MAP_KEY; GDACS wildfires if not set)
  Smithsonian GVP         weekly volcanic activity report (NASA EONET / GDACS as backup)
  ReliefWeb (UN OCHA)     humanitarian impact of current disasters
  NOAA GML Mauna Loa      global CO2 level
  Open-Meteo (CAMS)       air quality in 100 major cities (free tier: non-commercial; see note in AIR_NOTE)
Writes disasters.json to the folder given as the first argument (default: data/).
"""
import csv, datetime as dt, html as htmllib, io, json, math, os, re, sys, time, urllib.parse, urllib.request, zipfile

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
UA = "Mozilla/5.0 (compatible; WarEventsDisasters/1.0; +https://www.warevents.com)"
FIRMS_KEY = os.environ.get("FIRMS_MAP_KEY", "")
NOW = dt.datetime.now(dt.timezone.utc)
LOG = []


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOG.append(msg)
    print(msg, flush=True)


def get(url, timeout=40, binary=False, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                b = r.read(30_000_000)
                return b if binary else b.decode(r.headers.get_content_charset() or "utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def tag(s, name):
    m = re.search(r"<" + name + r"(?:\s[^>]*)?>(.*?)</" + name + ">", s, re.S)
    return htmllib.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""


def attr(s, name, a):
    m = re.search(r"<" + name + r"\s[^>]*" + a + r'="([^"]*)"', s)
    return m.group(1) if m else ""


def rfc(s):
    for f in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            d = dt.datetime.strptime(s.strip(), f)
            return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).isoformat()
        except Exception:
            pass
    return ""


def strip(s):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def dist_km(a, b, c, d):
    p = math.pi / 180
    h = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def r2(x):
    return round(float(x), 2)


# ---------------------------------------------------------------- GDACS
GD_TYPE = {"EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood", "VO": "Volcano", "DR": "Drought", "WF": "Wildfire", "TS": "Tsunami"}


def gdacs():
    xml = get("https://www.gdacs.org/xml/rss.xml")
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        if tag(it, "gdacs:iscurrent") != "true":
            continue
        t = tag(it, "gdacs:eventtype")
        try:
            lat, lng = float(tag(it, "geo:lat")), float(tag(it, "geo:long"))
        except ValueError:
            continue
        pop = attr(it, "gdacs:population", "value")
        out.append({
            "id": f"gd-{t}{tag(it, 'gdacs:eventid')}", "type": t, "kind": GD_TYPE.get(t, t),
            "alert": tag(it, "gdacs:alertlevel") or "Green", "name": tag(it, "gdacs:eventname"),
            "title": tag(it, "title"), "summary": strip(tag(it, "description"))[:400],
            "country": tag(it, "gdacs:country"), "severity": strip(tag(it, "gdacs:severity")),
            "population": int(float(pop)) if pop and pop.replace(".", "", 1).isdigit() else None,
            "lat": r2(lat), "lng": r2(lng), "from": rfc(tag(it, "gdacs:fromdate")), "to": rfc(tag(it, "gdacs:todate")),
            "url": tag(it, "link"), "eventid": tag(it, "gdacs:eventid"), "episodeid": tag(it, "gdacs:episodeid"),
        })
    # wildfires: GDACS lists hundreds of small Green fires; keep the bigger picture
    fires = [e for e in out if e["type"] == "WF"]
    rest = [e for e in out if e["type"] != "WF"]
    fires.sort(key=lambda e: ({"Red": 0, "Orange": 1}.get(e["alert"], 2), e["to"]), reverse=False)
    log(f"GDACS: {len(rest)} events + {len(fires)} wildfires")
    return rest, fires


def gdacs_track(e):
    """Past (and GDACS forecast) track of a cyclone from the GDACS geometry service."""
    try:
        g = json.loads(get(f"https://www.gdacs.org/gdacsapi/api/polygons/getgeometry?eventtype=TC&eventid={e['eventid']}&episodeid={e['episodeid']}"))
    except Exception as ex:
        log("  GDACS track failed", e["name"], str(ex)[:60])
        return [], [], ""
    past, fc, src = [], [], ""
    lines = [f for f in g.get("features", []) if f["geometry"]["type"] == "LineString"]
    lines.sort(key=lambda f: int(re.sub(r"\D", "", f["properties"].get("Class", "0")) or 0))
    for f in lines:
        src = f["properties"].get("source") or src
        pts = [[r2(c[1]), r2(c[0])] for c in f["geometry"]["coordinates"]]
        tgt = fc if f["properties"].get("forecast") else past
        for p in pts:
            if not tgt or tgt[-1] != p:
                tgt.append(p)
    return past, fc, src


# ---------------------------------------------------------------- storms: NHC + JTWC
def ll(s):
    m = re.match(r"([\d.]+)([NS])\s*([\d.]+)([EW])", s.strip())
    if not m:
        return None
    lat = float(m[1]) * (1 if m[2] == "N" else -1)
    lng = float(m[3]) * (1 if m[4] == "E" else -1)
    return [r2(lat), r2(lng)]


def nhc():
    out = []
    d = json.loads(get("https://www.nhc.noaa.gov/CurrentStorms.json"))
    for s in d.get("activeStorms", []):
        st = {"id": "nhc-" + s["id"], "name": s.get("name", ""), "cls": {"TD": "Tropical Depression", "TS": "Tropical Storm", "HU": "Hurricane", "MH": "Major Hurricane", "STD": "Subtropical Depression", "STS": "Subtropical Storm", "PTC": "Potential Tropical Cyclone", "PC": "Post-tropical Cyclone"}.get(s.get("classification", ""), s.get("classification", "")), "src": "NOAA National Hurricane Center",
              "lat": r2(s["latitudeNumeric"]), "lng": r2(s["longitudeNumeric"]), "wind_kt": int(s.get("intensity") or 0),
              "pressure": int(s.get("pressure") or 0) or None, "updated": s.get("lastUpdate", ""),
              "url": (s.get("publicAdvisory") or {}).get("url", "https://www.nhc.noaa.gov/"), "forecast": []}
        kmz = (s.get("forecastTrack") or {}).get("kmzFile")
        if kmz:
            try:
                z = zipfile.ZipFile(io.BytesIO(get(kmz, binary=True)))
                kml = z.read([n for n in z.namelist() if n.endswith(".kml")][0]).decode("utf-8", "replace")
                pts = []
                for c in re.findall(r"<Point>\s*<coordinates>([^<]+)</coordinates>", kml):
                    lo, la = c.strip().split(",")[:2]
                    pts.append([r2(la), r2(lo)])
                if not pts:
                    for c in re.findall(r"<coordinates>([^<]+)</coordinates>", kml)[:1]:
                        pts = [[r2(p.split(",")[1]), r2(p.split(",")[0])] for p in c.split()]
                st["forecast"] = pts
            except Exception as ex:
                log("  NHC track failed", st["name"], str(ex)[:60])
        out.append(st)
    log(f"NHC: {len(out)} storms")
    return out


def jtwc():
    out = []
    rss = get("https://www.metoc.navy.mil/jtwc/rss/jtwc.rss")
    for desc in re.findall(r"<description><!\[CDATA\[(.*?)\]\]></description>", rss, re.S):
        for name, url in re.findall(r"<b>([^<]*?(?:Typhoon|Tropical Storm|Cyclone|Depression|Hurricane)[^<]*?)</b>.*?<a href='([^']+web\.txt)'", desc, re.S):
            try:
                txt = get(url)
            except Exception:
                continue
            m = re.search(r"WARNING POSITION:\s*\n\s*\d{6}Z --- NEAR ([\d.]+[NS] [\d.]+[EW])", txt)
            if not m:
                continue
            here = ll(m[1])
            wind = re.search(r"MAX SUSTAINED WINDS - (\d+) KT", txt)
            fc = [ll(p) for p in re.findall(r"VALID AT:\s*\n\s*\d{6}Z --- ([\d.]+[NS] [\d.]+[EW])", txt)]
            nm = re.search(r"\(([A-Za-z0-9-]+)\)", name)
            cls = re.sub(r"\s+", " ", re.sub(r"\s+\d+[A-Z]\b.*$", "", name.strip())).strip()
            out.append({"id": "jtwc-" + re.sub(r"\W", "", url.split("/")[-1][:6]), "name": (nm[1].title() if nm else name.strip()),
                        "cls": cls, "src": "US Navy Joint Typhoon Warning Center", "lat": here[0], "lng": here[1],
                        "wind_kt": int(wind[1]) if wind else None, "pressure": None, "updated": NOW.isoformat(),
                        "url": url, "forecast": [here] + [p for p in fc if p]})
    log(f"JTWC: {len(out)} storms")
    return out


def storms(gd):
    st = []
    for fn in (nhc, jtwc):
        try:
            st += fn()
        except Exception as ex:
            log(fn.__name__, "failed:", str(ex)[:100])
    # past tracks + alert level from GDACS (matched by name or by position)
    tcs = [e for e in gd if e["type"] == "TC"]
    for s in st:
        best = None
        for e in tcs:
            n = (e["name"] or "").split("-")[0].lower()
            if n and n == s["name"].lower() or dist_km(s["lat"], s["lng"], e["lat"], e["lng"]) < 600:
                best = e
                break
        if best:
            past, fc, _ = gdacs_track(best)
            s["past"] = past
            if not s["forecast"]:
                s["forecast"] = fc
            s["alert"], s["gdacs"], s["country"] = best["alert"], best["url"], best["country"]
            best["_storm"] = s["id"]
        else:
            s["past"], s["alert"] = [], "Green"
    # GDACS-only cyclones (e.g. southern hemisphere basins not in the two feeds)
    for e in tcs:
        if "_storm" not in e:
            past, fc, src = gdacs_track(e)
            st.append({"id": e["id"], "name": (e["name"] or "").split("-")[0].title(), "cls": "Tropical cyclone", "src": f"GDACS ({src or 'JRC'})",
                       "lat": e["lat"], "lng": e["lng"], "wind_kt": None, "pressure": None, "updated": e["to"], "url": e["url"],
                       "forecast": fc, "past": past, "alert": e["alert"], "gdacs": e["url"], "country": e["country"]})
    return st


# ---------------------------------------------------------------- earthquakes
def quakes():
    q = []
    try:
        d = json.loads(get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"))
        for f in d["features"]:
            p, c = f["properties"], f["geometry"]["coordinates"]
            q.append({"id": "us-" + f["id"], "mag": round(p["mag"] or 0, 1), "place": p.get("place") or "", "lat": r2(c[1]), "lng": r2(c[0]),
                      "depth": round(c[2] or 0), "time": dt.datetime.fromtimestamp(p["time"] / 1000, dt.timezone.utc).isoformat(),
                      "url": p.get("url"), "src": "USGS", "tsunami": bool(p.get("tsunami")), "alert": p.get("alert"), "felt": p.get("felt")})
        log(f"USGS: {len(q)} quakes")
    except Exception as ex:
        log("USGS failed:", str(ex)[:100])
    try:
        start = (NOW - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
        url = ("https://www.seismicportal.eu/fdsnws/event/1/query?format=json&limit=300&minmag=4.0&start=" + start +
               "&minlat=24&maxlat=72&minlon=-32&maxlon=66")
        d = json.loads(get(url))
        added = 0
        for f in d.get("features", []):
            p = f["properties"]
            t = dt.datetime.fromisoformat(p["time"].replace("Z", "+00:00"))
            if any(abs((dt.datetime.fromisoformat(x["time"]) - t).total_seconds()) < 120 and dist_km(x["lat"], x["lng"], p["lat"], p["lon"]) < 150 for x in q):
                continue
            q.append({"id": "emsc-" + str(p.get("unid") or f.get("id")), "mag": round(p.get("mag") or 0, 1), "place": (p.get("flynn_region") or "").title(),
                      "lat": r2(p["lat"]), "lng": r2(p["lon"]), "depth": round(p.get("depth") or 0), "time": t.isoformat(),
                      "url": "https://www.emsc-csem.org/Earthquake_information/earthquake.php?id=" + str(p.get("source_id") or ""), "src": "EMSC",
                      "tsunami": False, "alert": None, "felt": None})
            added += 1
        log(f"EMSC: {added} extra quakes (Europe, Middle East, North Africa)")
    except Exception as ex:
        log("EMSC failed:", str(ex)[:100])
    q.sort(key=lambda x: x["time"], reverse=True)
    return q


# ---------------------------------------------------------------- wildfires
def fires(gd_fires):
    if FIRMS_KEY:
        try:
            raw = get(f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}/VIIRS_SNPP_NRT/world/1", timeout=120)
            cells = {}
            for row in csv.DictReader(io.StringIO(raw)):
                try:
                    la, lo, frp = float(row["latitude"]), float(row["longitude"]), float(row.get("frp") or 0)
                except (KeyError, ValueError):
                    continue
                if row.get("confidence", "n") == "l":
                    continue
                k = (round(la * 2) / 2, round(lo * 2) / 2)          # half-degree cells
                c = cells.setdefault(k, [0, 0.0, 0.0, 0.0])
                c[0] += 1; c[1] += frp; c[2] += la; c[3] += lo
            out = [{"lat": r2(c[2] / c[0]), "lng": r2(c[3] / c[0]), "n": c[0], "frp": round(c[1])} for c in cells.values() if c[0] >= 3]
            out.sort(key=lambda x: x["frp"], reverse=True)
            log(f"FIRMS: {len(out)} fire clusters")
            return out[:700], "NASA FIRMS (VIIRS, last 24 h)"
        except Exception as ex:
            log("FIRMS failed:", str(ex)[:100])
    out = [{"lat": e["lat"], "lng": e["lng"], "n": 1, "frp": None, "name": e["title"][:120], "alert": e["alert"], "url": e["url"]} for e in gd_fires]
    return out, "GDACS wildfire alerts (add a NASA FIRMS key for satellite hot spots)"


# ---------------------------------------------------------------- volcanoes
def volcanoes(gd):
    out = []
    try:
        xml = get("https://volcano.si.edu/news/WeeklyVolcanoRSS.xml")
        for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
            t = tag(it, "title")
            pt = tag(it, "georss:point")
            if not pt:
                continue
            la, lo = map(float, pt.split()[:2])
            m = re.match(r"(.+?)\s*\((.+?)\)", t)
            out.append({"name": m[1] if m else t, "country": m[2] if m else "", "lat": r2(la), "lng": r2(lo),
                        "note": strip(tag(it, "description"))[:420], "url": tag(it, "link"), "src": "Smithsonian GVP / USGS weekly report"})
        log(f"Smithsonian: {len(out)} volcanoes")
    except Exception as ex:
        log("Smithsonian failed:", str(ex)[:80])
    if not out:
        try:
            d = json.loads(get("https://eonet.gsfc.nasa.gov/api/v3/events?category=volcanoes&status=open"))
            for e in d.get("events", []):
                g = e["geometry"][-1]
                lo, la = g["coordinates"][:2]
                src = (e.get("sources") or [{}])[0]
                out.append({"name": re.sub(r",.*$", "", e["title"]).replace(" Volcano", ""), "country": (e["title"].split(",")[-1].strip() if "," in e["title"] else ""),
                            "lat": r2(la), "lng": r2(lo), "note": "", "url": src.get("url", e.get("link")), "src": "NASA EONET (" + src.get("id", "") + ")"})
            log(f"EONET volcanoes: {len(out)}")
        except Exception as ex:
            log("EONET failed:", str(ex)[:80])
    for e in gd:
        if e["type"] == "VO" and not any(dist_km(v["lat"], v["lng"], e["lat"], e["lng"]) < 50 for v in out):
            out.append({"name": e["name"] or e["title"], "country": e["country"], "lat": e["lat"], "lng": e["lng"], "note": e["summary"], "url": e["url"], "src": "GDACS", "alert": e["alert"]})
    return out


# ---------------------------------------------------------------- humanitarian impact
def relief():
    out = []
    try:
        xml = get("https://reliefweb.int/disasters/rss.xml")
        for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
            t = tag(it, "title")
            desc = tag(it, "description")
            m = re.match(r"(.+?):\s*(.+?)\s*-\s*(\w+ \d{4})", t)
            countries = re.findall(r'Affected countr(?:y|ies): ([^<]+)<', desc)
            body = strip(re.sub(r'<div class="tag[^"]*">.*?</div>', " ", desc, flags=re.S))
            out.append({"title": t, "country": (countries[0].strip() if countries else (m[1] if m else "")),
                        "type": m[2] if m else "", "date": rfc(tag(it, "pubDate")), "url": tag(it, "link"),
                        "summary": (body[:360] + "…") if len(body) > 360 else body})
        log(f"ReliefWeb: {len(out)} disasters")
    except Exception as ex:
        log("ReliefWeb failed:", str(ex)[:80])
    return out


def match_relief(items, rel):
    words = {"EQ": "earthquake", "TC": "cyclone|typhoon|hurricane|storm", "FL": "flood", "VO": "volcan", "DR": "drought", "WF": "fire"}
    for e in items:
        for r in rel:
            if re.search(words.get(e["type"], "$^"), r["type"] + " " + r["title"], re.I) and r["country"] and r["country"].split(",")[0].lower() in (e["country"] or "").lower():
                e["relief"] = {"title": r["title"], "url": r["url"], "summary": r["summary"]}
                break


# ---------------------------------------------------------------- CO2 + air quality
def co2():
    try:
        rows = [r for r in csv.reader(io.StringIO(get("https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_daily_mlo.csv"))) if r and r[0][:1].isdigit()]
        y, m, d, _, v = rows[-1][:5]
        last = dt.date(int(y), int(m), int(d))
        ago = next((float(r[4]) for r in reversed(rows) if dt.date(int(r[0]), int(r[1]), int(r[2])) <= last.replace(year=last.year - 1)), None)
        out = {"ppm": round(float(v), 1), "date": last.isoformat(), "yearAgo": round(ago, 1) if ago else None,
               "src": "NOAA Global Monitoring Laboratory, Mauna Loa", "url": "https://gml.noaa.gov/ccgg/trends/"}
        log(f"CO2: {out['ppm']} ppm on {out['date']}")
        return out
    except Exception as ex:
        log("CO2 failed:", str(ex)[:80])
        return None


CITIES = [  # name, country code, lat, lng
 ("Tokyo","JP",35.68,139.69),("Delhi","IN",28.61,77.21),("Shanghai","CN",31.23,121.47),("Dhaka","BD",23.81,90.41),("São Paulo","BR",-23.55,-46.63),
 ("Mexico City","MX",19.43,-99.13),("Cairo","EG",30.04,31.24),("Beijing","CN",39.90,116.41),("Mumbai","IN",19.08,72.88),("Osaka","JP",34.69,135.50),
 ("Chongqing","CN",29.56,106.55),("Karachi","PK",24.86,67.01),("Kinshasa","CD",-4.44,15.27),("Lagos","NG",6.52,3.38),("Istanbul","TR",41.01,28.98),
 ("Buenos Aires","AR",-34.60,-58.38),("Kolkata","IN",22.57,88.36),("Manila","PH",14.60,120.98),("Guangzhou","CN",23.13,113.26),("Tianjin","CN",39.34,117.36),
 ("Lahore","PK",31.55,74.34),("Bengaluru","IN",12.97,77.59),("Rio de Janeiro","BR",-22.91,-43.17),("Shenzhen","CN",22.54,114.06),("Moscow","RU",55.76,37.62),
 ("Chennai","IN",13.08,80.27),("Bogotá","CO",4.71,-74.07),("Jakarta","ID",-6.21,106.85),("Lima","PE",-12.05,-77.04),("Paris","FR",48.86,2.35),
 ("Bangkok","TH",13.76,100.50),("Hyderabad","IN",17.39,78.49),("Seoul","KR",37.57,126.98),("Nagoya","JP",35.18,136.91),("London","GB",51.51,-0.13),
 ("Chengdu","CN",30.57,104.07),("Tehran","IR",35.69,51.39),("Nanjing","CN",32.06,118.80),("Ho Chi Minh City","VN",10.82,106.63),("Luanda","AO",-8.84,13.23),
 ("Wuhan","CN",30.59,114.31),("Xi'an","CN",34.34,108.94),("Ahmedabad","IN",23.02,72.57),("Kuala Lumpur","MY",3.14,101.69),("New York","US",40.71,-74.01),
 ("Hong Kong","HK",22.32,114.17),("Hangzhou","CN",30.27,120.16),("Riyadh","SA",24.71,46.68),("Baghdad","IQ",33.31,44.36),("Santiago","CL",-33.45,-70.67),
 ("Surat","IN",21.17,72.83),("Madrid","ES",40.42,-3.70),("Pune","IN",18.52,73.86),("Dar es Salaam","TZ",-6.79,39.21),("Toronto","CA",43.65,-79.38),
 ("Khartoum","SD",15.50,32.56),("Johannesburg","ZA",-26.20,28.05),("Singapore","SG",1.35,103.82),("Los Angeles","US",34.05,-118.24),("Yangon","MM",16.84,96.17),
 ("Abidjan","CI",5.36,-4.01),("Alexandria","EG",31.20,29.92),("Saint Petersburg","RU",59.93,30.34),("Ankara","TR",39.93,32.86),("Chicago","US",41.88,-87.63),
 ("Addis Ababa","ET",9.03,38.74),("Nairobi","KE",-1.29,36.82),("Hanoi","VN",21.03,105.85),("Berlin","DE",52.52,13.40),("Sydney","AU",-33.87,151.21),
 ("Jeddah","SA",21.49,39.19),("Kabul","AF",34.56,69.21),("Casablanca","MA",33.57,-7.59),("Melbourne","AU",-37.81,144.96),("Rome","IT",41.90,12.50),
 ("Kyiv","UA",50.45,30.52),("Dubai","AE",25.20,55.27),("Accra","GH",5.60,-0.19),("Algiers","DZ",36.75,3.06),("Taipei","TW",25.03,121.57),
 ("Busan","KR",35.18,129.08),("Houston","US",29.76,-95.37),("Washington","US",38.91,-77.04),("Kano","NG",12.00,8.52),("Caracas","VE",10.48,-66.90),
 ("Lisbon","PT",38.72,-9.14),("Warsaw","PL",52.23,21.01),("Athens","GR",37.98,23.73),("Tashkent","UZ",41.30,69.24),("Baku","AZ",40.41,49.87),
 ("Ulaanbaatar","MN",47.89,106.91),("Pyongyang","KP",39.04,125.76),("Islamabad","PK",33.68,73.05),("Doha","QA",25.29,51.53),("Tel Aviv","IL",32.09,34.78),
 ("Beirut","LB",33.89,35.50),("Damascus","SY",33.51,36.29),("Sana'a","YE",15.37,44.19),("Vienna","AT",48.21,16.37),("Guadalajara","MX",20.67,-103.35),
]
AIR_NOTE = "Modelled by Copernicus CAMS via Open-Meteo. Open-Meteo's free API is for non-commercial use; switch to a paid plan or OpenAQ before the site earns money."


def air():
    out = []
    for i in range(0, len(CITIES), 50):
        chunk = CITIES[i:i + 50]
        url = ("https://air-quality-api.open-meteo.com/v1/air-quality?current=pm2_5,pm10,nitrogen_dioxide,ozone,us_aqi&latitude="
               + ",".join(str(c[2]) for c in chunk) + "&longitude=" + ",".join(str(c[3]) for c in chunk))
        try:
            d = json.loads(get(url))
            d = d if isinstance(d, list) else [d]
            for c, r in zip(chunk, d):
                cur = r.get("current") or {}
                if cur.get("us_aqi") is None:
                    continue
                out.append({"city": c[0], "cc": c[1], "lat": c[2], "lng": c[3], "aqi": int(cur["us_aqi"]),
                            "pm25": cur.get("pm2_5"), "pm10": cur.get("pm10"), "no2": cur.get("nitrogen_dioxide"), "o3": cur.get("ozone"), "time": cur.get("time")})
        except Exception as ex:
            log("Air quality failed:", str(ex)[:80])
        time.sleep(1)
    log(f"Air quality: {len(out)} cities")
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "disasters.json")
    old = {}
    try:
        old = json.load(open(path, encoding="utf-8"))
    except Exception:
        pass
    try:
        gd, gd_fires = gdacs()
    except Exception as ex:
        log("GDACS failed:", str(ex)[:100])
        gd, gd_fires = old.get("events", []), []
    rel = relief()
    st = storms(gd)
    match_relief(gd, rel)
    fr, fsrc = fires(gd_fires)
    data = {
        "updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events": [{k: v for k, v in e.items() if not k.startswith("_") and k not in ("eventid", "episodeid")} for e in gd if e["type"] not in ("TC",)],
        "storms": st, "quakes": quakes(), "fires": fr, "firesSrc": fsrc, "volcanoes": volcanoes(gd),
        "relief": rel, "co2": co2() or old.get("co2"), "air": air() or old.get("air", []), "airNote": AIR_NOTE,
    }
    for k in ("quakes", "volcanoes", "relief", "storms"):          # one failed source never empties the map
        if not data[k] and old.get(k):
            data[k] = old[k]
            log(f"{k}: kept previous data")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    json.load(open(tmp, encoding="utf-8"))
    os.replace(tmp, path)
    log(f"wrote {path}: {os.path.getsize(path)//1024} KB")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        log("fetch_disasters failed:", ex)
