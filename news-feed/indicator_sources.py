"""Source parsers and fetch helper for the twice-daily indicators job (stdlib only)."""
import csv
import io
import json
import re
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

TREASURY_URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
                "&field_tdr_date_value={year}&page&_format=csv")
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
FRED_API_URL = ("https://api.stlouisfed.org/fred/series/observations?series_id={}"
                "&api_key={}&file_type=json&observation_start={}")
ECB_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=csvdata&startPeriod={}"
TSA_URL = "https://www.tsa.gov/travel/passenger-volumes"

USER_AGENT = "WarEventsDataBot/1.0"

TREASURY_COLUMNS = {
    "1 Mo": "1m", "2 Mo": "2m", "3 Mo": "3m", "4 Mo": "4m", "6 Mo": "6m",
    "1 Yr": "1y", "2 Yr": "2y", "3 Yr": "3y", "5 Yr": "5y", "7 Yr": "7y",
    "10 Yr": "10y", "20 Yr": "20y", "30 Yr": "30y",
}


def _float(s):
    s = (s or "").strip()
    if not s or s == ".":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_treasury_csv(text):
    """Rows {"date": "YYYY-MM-DD", "1m": float, ...}, newest first; blank cells omitted."""
    rows = []
    for rec in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        try:
            date = datetime.strptime((rec.get("Date") or "").strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            continue
        row = {"date": date}
        for header, key in TREASURY_COLUMNS.items():
            v = _float(rec.get(header))
            if v is not None:
                row[key] = v
        rows.append(row)
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def parse_fred_csv(text):
    """(date, value) oldest first; skips '.' and blank values."""
    out = []
    for rec in csv.reader(io.StringIO(text.lstrip("﻿"))):
        if len(rec) < 2 or not re.match(r"\d{4}-\d{2}-\d{2}$", rec[0].strip()):
            continue
        v = _float(rec[1])
        if v is not None:
            out.append((rec[0].strip(), v))
    out.sort(key=lambda p: p[0])
    return out


def parse_fred_api(json_text):
    out = []
    for o in json.loads(json_text).get("observations", []):
        v = _float(str(o.get("value", "")))
        if v is not None and o.get("date"):
            out.append((o["date"], v))
    out.sort(key=lambda p: p[0])
    return out


def parse_ecb_csv(text):
    """{currency: [(date, value), ...]} oldest first."""
    out = {}
    for rec in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        cur, date, v = rec.get("CURRENCY"), rec.get("TIME_PERIOD"), _float(rec.get("OBS_VALUE"))
        if cur and date and v is not None:
            out.setdefault(cur, []).append((date, v))
    for series in out.values():
        series.sort(key=lambda p: p[0])
    return out


class _TsaTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells, self._in_td, self._buf = [], False, []

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self._in_td, self._buf = True, []

    def handle_data(self, data):
        if self._in_td:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self._in_td:
            self._in_td = False
            self.cells.append("".join(self._buf).strip())


def parse_tsa_html(html):
    """(YYYY-MM-DD, travellers) newest first from <td> date/number pairs."""
    p = _TsaTable()
    p.feed(html)
    out = []
    for i in range(0, len(p.cells) - 1, 2):
        try:
            date = datetime.strptime(p.cells[i], "%m/%d/%Y").strftime("%Y-%m-%d")
            n = int(p.cells[i + 1].replace(",", ""))
        except ValueError:
            continue
        out.append((date, n))
    out.sort(key=lambda r: r[0], reverse=True)
    return out


def latest(series):
    return series[-1] if series else None


def check_body(body, expect):
    """Raise ValueError if the body is not the kind of document the caller expected."""
    if expect not in ("csv", "json", "html"):
        raise ValueError("expect must be 'csv', 'json' or 'html', got %r" % (expect,))
    first = body.lstrip()[:1]
    if expect == "csv" and first == "<":
        raise ValueError("expected csv but got markup")
    if expect == "json" and first not in ("{", "["):
        raise ValueError("expected json but got something else")
    if expect == "html" and "<table" not in body.lower():
        raise ValueError("expected an HTML page with a table")


def fetch_text(url, expect, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise ValueError("HTTP %s for %s" % (resp.status, url))
        body = resp.read().decode("utf-8", errors="replace")
    check_body(body, expect)
    return body
