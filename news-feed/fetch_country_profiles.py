"""Daily refresh of country profiles in data/country_stats.json.

- UN voting alignment with the US, China, Russia and the EU (France+Germany),
  from Voeten/Bailey/Strezhnev UNGA ideal points (Harvard Dataverse, CC0).
  Alignment % = 100 * exp(-|ideal point distance|), latest year available.
- Fills any missing "Geopolitical overview" from Wikipedia's
  "Foreign relations of <country>" summary.
Standard library only. Run from .github/workflows/update-profiles.yml.
"""
import csv, io, json, math, os, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS = os.path.join(ROOT, "data", "country_stats.json")
NAMES = json.load(open(os.path.join(ROOT, "news-feed", "country_names.json"), encoding="utf-8"))
UA = {"User-Agent": "WarEvents profile bot (github actions)"}
DOI = "doi:10.7910/DVN/LEJUQZ"
THE = {"United States", "United Kingdom", "Philippines", "Bahamas", "Gambia", "Maldives", "Comoros",
       "Seychelles", "Marshall Islands", "Solomon Islands", "Central African Republic", "Czech Republic",
       "Dominican Republic", "United Arab Emirates", "Republic of the Congo"}


def get(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def iso3_to_num():
    j = json.loads(get("https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/master/all/all.json"))
    return {c["alpha-3"]: str(int(c["country-code"])) for c in j}


def un_alignment():
    meta = json.loads(get("https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId=" + DOI))
    files = meta["data"]["latestVersion"]["files"]
    cands = [f["dataFile"] for f in files if f["dataFile"]["filename"].lower().startswith("idealpoint")
             and f["dataFile"]["filename"].lower().endswith((".csv", ".tab"))]
    if not cands:
        raise RuntimeError("no ideal point file")
    fid = sorted(cands, key=lambda d: d.get("id", 0))[-1]["id"]
    raw = get(f"https://dataverse.harvard.edu/api/access/datafile/{fid}?format=original", timeout=180)
    text = raw.decode("utf-8", "replace")
    delim = "\t" if text.split("\n", 1)[0].count("\t") > text.split("\n", 1)[0].count(",") else ","
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    cols = {c.lower(): c for c in rows[0].keys()}
    iso_c = cols.get("iso3c") or cols.get("iso3")
    ip_c = cols.get("idealpointall") or cols.get("idealpointfp") or cols.get("idealpoint")
    yr_c = cols.get("year") or cols.get("session")
    if not (iso_c and ip_c and yr_c):
        raise RuntimeError("unexpected columns: %s" % list(rows[0].keys()))
    latest = {}
    for r in rows:
        try:
            y, v, k = int(float(r[yr_c])), float(r[ip_c]), r[iso_c].strip().upper()
        except Exception:
            continue
        if k and (k not in latest or y > latest[k][0]):
            latest[k] = (y, v)
    ref = {"United States": ["USA"], "China": ["CHN"], "Russia": ["RUS"], "European Union": ["FRA", "DEU"]}
    refv = {lab: sum(latest[c][1] for c in cs if c in latest) / max(1, sum(1 for c in cs if c in latest))
            for lab, cs in ref.items()}
    out = {}
    for k, (y, v) in latest.items():
        out[k] = {"year": y, "alignment": [
            {"label": lab, "pct": int(round(100 * math.exp(-abs(v - rv))))} for lab, rv in refv.items()]}
    return out


def overview(name):
    t = "Foreign relations of " + ("the " if name in THE else "") + name
    if name == "DR Congo":
        t = "Foreign relations of the Democratic Republic of the Congo"
    if name == "Kingdom of the Netherlands":
        t = "Foreign relations of the Netherlands"
    try:
        j = json.loads(get("https://en.wikipedia.org/api/rest_v1/page/summary/" +
                           urllib.parse.quote(t.replace(" ", "_")) + "?redirect=true", 30))
        return (j.get("extract") or "").strip()
    except Exception:
        return ""


def main():
    data = json.load(open(STATS, encoding="utf-8"))
    C = data["countries"]
    try:
        m = iso3_to_num()
        al = un_alignment()
        n = 0
        for iso3, a in al.items():
            cid = m.get(iso3)
            if cid and cid in C:
                C[cid]["unAlignment"] = a["alignment"]
                C[cid]["unAlignmentYear"] = a["year"]
                n += 1
        print("UN alignment:", n)
    except Exception as e:
        print("UN alignment skipped:", e)
    filled = 0
    for cid, name in NAMES.items():
        c = C.setdefault(cid, {})
        if c.get("overview"):
            continue
        s = overview(name)
        if s:
            c["overview"] = s[:520].rsplit(". ", 1)[0] + "." if len(s) > 520 else s
            filled += 1
        time.sleep(0.4)
    print("overviews filled:", filled)
    data["updated"] = time.strftime("%Y-%m-%d")
    with open(STATS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
