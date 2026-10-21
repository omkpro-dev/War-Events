"""Builds the Power > Economic and technological data (monthly).

data/economic.json        latest value per country for every measure (+ the year it is from)
data/eco/<measure>.json   yearly history 2000-now per country, for the charts

Sources: World Bank World Development Indicators (CC BY 4.0) and, for government debt,
the IMF World Economic Outlook DataMapper (free to reuse with attribution). Stdlib only.
"""
import json, os, time, urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "economic.json")
HIST_DIR = os.path.join(ROOT, "data", "eco")
START, END = 2000, date.today().year - 1        # last complete year; IMF projections beyond it are left out

WB = {
    "gdp": "NY.GDP.MKTP.PP.CD", "gdp_usd": "NY.GDP.MKTP.CD", "gdp_pc": "NY.GDP.PCAP.PP.CD",
    "growth": "NY.GDP.MKTP.KD.ZG", "inflation": "FP.CPI.TOTL.ZG", "trade_gdp": "NE.TRD.GNFS.ZS",
    "exports": "NE.EXP.GNFS.CD", "fuel_x": "TX.VAL.FUEL.ZS.UN", "food_m": "TM.VAL.FOOD.ZS.UN",
    "remit": "BX.TRF.PWKR.DT.GD.ZS", "fdi": "BX.KLT.DINV.CD.WD", "rnd": "GB.XPD.RSDV.GD.ZS",
    "hitech": "TX.VAL.TECH.CD", "internet": "IT.NET.USER.ZS", "researchers": "SP.POP.SCIE.RD.P6",
    "patents": "IP.PAT.RESD", "unemployment": "SL.UEM.TOTL.ZS",
    "interest_rev": "GC.XPN.INTP.RV.ZS", "_int_lcu": "GC.XPN.INTP.CN", "_fx": "PA.NUS.FCRF",
}
IMF = {"debt": "GGXWDG_NGDP", "deficit": "GGXCNL_NGDP"}


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; WarEvents/1.0; +https://www.warevents.com)"}), timeout=90) as r:
                return json.loads(r.read())
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(5)


def rnd(v):
    if v is None:
        return None
    a = abs(v)
    return round(v) if a >= 1e5 else round(v, 2) if a >= 1 else round(v, 3)


def main():
    iso3to2, hist = {}, {}
    for k, ind in WB.items():
        rows = get(f"https://api.worldbank.org/v2/country/all/indicator/{ind}?format=json&date={START}:{END}&per_page=20000")
        rows = rows[1] if isinstance(rows, list) and len(rows) > 1 and rows[1] else []
        for x in rows:
            c2, c3 = x["country"]["id"], x.get("countryiso3code")
            if not c3 or len(c2) != 2 or not c2.isalpha():
                continue
            iso3to2[c3] = c2
            if x["value"] is not None:
                hist.setdefault(k, {}).setdefault(c2, {})[x["date"]] = rnd(x["value"])
        print(k, len(hist.get(k, {})))
    for k, ind in IMF.items():
        d = get(f"https://www.imf.org/external/datamapper/api/v1/{ind}").get("values", {}).get(ind, {})
        for c3, ys in d.items():
            c2 = iso3to2.get(c3)
            if not c2:
                continue
            for y, v in ys.items():
                if START <= int(y) <= END and v is not None:
                    hist.setdefault(k, {}).setdefault(c2, {})[y] = rnd(v)
        print(k, len(hist.get(k, {})))
    # interest paid on government debt, in US dollars: local-currency interest / official exchange rate
    lcu, fx = hist.pop("_int_lcu", {}), hist.pop("_fx", {})
    for c, ys in lcu.items():
        for y, v in ys.items():
            r = fx.get(c, {}).get(y)
            if r:
                hist.setdefault("interest", {}).setdefault(c, {})[y] = rnd(v / r)
    # drop World Bank aggregates (regions, income groups): they have 2-letter ids that are not countries
    agg = set("1A 1W 4E 7E 8S B8 EU F1 OE S1 S2 S3 S4 T2 T3 T4 T5 T6 T7 V1 V2 V3 V4 XC XD XE XF XG XH XI XJ XL XM XN XO XP XQ XT XU XY Z4 Z7 ZB ZF ZG ZH ZI ZJ ZQ ZT".split())
    latest, years = {}, {}
    os.makedirs(HIST_DIR, exist_ok=True)
    for k, by in hist.items():
        by = {c: v for c, v in by.items() if c not in agg}
        ys = []
        for c, s in by.items():
            y = max(s)
            latest.setdefault(c, {})[k] = s[y]
            ys.append(int(y))
        years[k] = max(set(ys), key=ys.count) if ys else None
        with open(os.path.join(HIST_DIR, k + ".json"), "w") as f:
            json.dump(by, f, separators=(",", ":"))
    out = {"updated": date.today().isoformat(),
           "source": "World Bank World Development Indicators (CC BY 4.0); IMF World Economic Outlook (government debt and balance)",
           "years": years, "countries": latest}
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print("countries", len(latest), years)


if __name__ == "__main__":
    main()
