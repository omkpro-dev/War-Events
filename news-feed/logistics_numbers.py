"""Daily numbers for the Logistics view (data/logistics.json). No AI, no judgement calls.

  1. Chokepoint traffic from IMF PortWatch (satellite AIS ship counts, one row per strait per day):
     each chokepoint gets a "traffic" line -- latest day, 7-day average, and the change against the
     2023 average (Jan-Oct 2023, before the Red Sea attacks) -- plus the raw numbers in "counts".
  2. Internet outages from IODA (Georgia Tech): every country in "blackouts" gets an "ioda" line
     saying whether a national outage is being measured right now. Strong NEW outages (active
     probing and routing both down, still ongoing) go to signals.outages for review_logistics.py
     to check against the news -- they are never added to the map from the numbers alone.

Status, notes and sources are left alone; review_logistics.py (weekly, Claude) handles those.
Standard library only.
"""
import datetime as dt
import json, os, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "logistics.json")

PORTWATCH = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query"
# our chokepoint id -> PortWatch portid
PW_IDS = {
    "suez": "chokepoint1", "panama": "chokepoint2", "bosporus": "chokepoint3", "bab-el-mandeb": "chokepoint4",
    "malacca": "chokepoint5", "hormuz": "chokepoint6", "cape": "chokepoint7", "gibraltar": "chokepoint8",
    "dover": "chokepoint9", "danish": "chokepoint10", "taiwan": "chokepoint11", "kerch": "chokepoint28",
}
PW_NOTE = {"danish": ", Øresund only"}
BASE_FROM, BASE_TO = "2023-01-01", "2023-10-31"

IODA = "https://api.ioda.inetintel.cc.gatech.edu/v2/outages"
OUTAGE_MIN_SCORE = 100000     # overall IODA score; small-island BGP noise sits far below this
OUTAGE_MIN_HOURS = 3


def get_json(url, params=None, tries=3):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "WarEvents/1.0 (+https://www.warevents.com)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            if i == tries - 1:
                raise
            print("retrying", url[:80], e)
            time.sleep(5 * (i + 1))


def pw_query(**params):
    params.setdefault("f", "json")
    d = get_json(PORTWATCH, params)
    if d.get("error"):
        raise RuntimeError(d["error"])
    return [f["attributes"] for f in d.get("features", [])]


def day_label(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


def traffic(choke, today):
    ids = ",".join(f"'{p}'" for p in PW_IDS.values())
    since = (today - dt.timedelta(days=21)).isoformat()
    rows = pw_query(where=f"portid IN ({ids}) AND date >= '{since}'", outFields="date,portid,n_total",
                    orderByFields="date DESC", resultRecordCount=2000)
    base = {r["portid"]: r["avg_n"] for r in pw_query(
        where=f"portid IN ({ids}) AND date >= '{BASE_FROM}' AND date <= '{BASE_TO}'",
        outStatistics=json.dumps([{"statisticType": "avg", "onStatisticField": "n_total", "outStatisticFieldName": "avg_n"}]),
        groupByFieldsForStatistics="portid")}
    by = {}
    for r in rows:
        if r.get("n_total") is not None:
            by.setdefault(r["portid"], []).append(r)
    done = 0
    for c in choke:
        pid = PW_IDS.get(c.get("id"))
        days = sorted(by.get(pid, []), key=lambda r: r["date"], reverse=True)
        if not days:
            continue
        last, week = days[0], [r["n_total"] for r in days[:7]]
        avg7, b = sum(week) / len(week), base.get(pid)
        n = last["n_total"]
        txt = f"{n:,} ship{'s' if n != 1 else ''} on {day_label(last['date'])}, 7-day average {avg7:,.0f}"
        if b:
            pct = round((avg7 - b) / b * 100)
            txt += f", {abs(pct)}% {'below' if pct < 0 else 'above'} the 2023 average of {b:,.0f} a day" if abs(pct) >= 5 else f", close to the 2023 average of {b:,.0f} a day"
        c["traffic"] = txt + " (IMF PortWatch" + PW_NOTE.get(c["id"], "") + ")"
        c["counts"] = {"date": last["date"], "n": n, "avg7": round(avg7, 1), "base2023": round(b, 1) if b else None,
                       "last14": [[r["date"], r["n_total"]] for r in days[:14]]}
        done += 1
    print("chokepoint traffic:", done, "of", len(choke))


def outages(data, now):
    frm, until = int(now - 86400), int(now)
    summ = get_json(IODA + "/summary", {"from": frm, "until": until, "entityType": "country", "limit": 300}).get("data", [])
    events = get_json(IODA + "/events", {"from": frm, "until": until, "entityType": "country", "limit": 2000, "format": "codf"}).get("data", [])
    live = {}   # cc -> {sources, start} for outages still running in the last 2 hours
    for e in events:
        cc = (e.get("location") or "").split("/")[-1].upper()
        if now - (e["start"] + e["duration"]) < 2 * 3600:
            x = live.setdefault(cc, {"src": set(), "start": e["start"]})
            x["src"].add(e.get("datasource", "").split(".")[0])
            x["start"] = min(x["start"], e["start"])
    score = {r["entity"]["code"].upper(): r["scores"].get("overall", 0) for r in summ}
    today = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    mine = {b["cc"] for b in data.get("blackouts", [])}
    for b in data.get("blackouts", []):
        x = live.get(b["cc"])
        if x and "ping-slash24" in x["src"]:
            b["ioda"] = f"IODA is measuring a national internet outage now (since {day_label(dt.datetime.fromtimestamp(x['start'], dt.timezone.utc).date().isoformat())})"
        elif x:
            b["ioda"] = "IODA sees partial disruption now (routing data only)"
        else:
            b["ioda"] = "IODA measures no national outage now; filtering and app blocks do not show in its data"
        b["iodaAt"] = today.date().isoformat()
        if b.get("auto"):   # added by review_logistics.py from an outage: drop it once IODA has been clear for 2 days
            b["clearSince"] = b.get("clearSince") or b["iodaAt"] if not x else None
    data["blackouts"] = [b for b in data.get("blackouts", []) if not (b.get("auto") and b.get("clearSince")
                         and (today.date() - dt.date.fromisoformat(b["clearSince"])).days >= 2)]
    strong = []
    for cc, x in live.items():
        hours = (now - x["start"]) / 3600
        if cc in mine or "ping-slash24" not in x["src"] or "bgp" not in x["src"]:
            continue
        if score.get(cc, 0) >= OUTAGE_MIN_SCORE and hours >= OUTAGE_MIN_HOURS:
            strong.append({"cc": cc, "since": dt.datetime.fromtimestamp(x["start"], dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
                           "hours": round(hours), "score": round(score[cc]),
                           "source": f"https://ioda.inetintel.cc.gatech.edu/country/{cc}"})
    data.setdefault("signals", {})["outages"] = strong
    print("blackouts checked:", len(mine), "| strong new outages:", [s["cc"] for s in strong])


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DATA
    data = json.load(open(path, encoding="utf-8"))
    now, ok = time.time(), 0
    for name, step in (("PortWatch", lambda: traffic(data.get("chokepoints", []), dt.date.today())),
                       ("IODA", lambda: outages(data, now))):
        try:
            step()
            ok += 1
        except Exception as e:
            print(name, "failed:", e)   # keep yesterday's numbers rather than failing the run
    if not ok:
        sys.exit(1)
    data["numbersAt"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    json.load(open(tmp, encoding="utf-8"))
    os.replace(tmp, path)


if __name__ == "__main__":
    main()
