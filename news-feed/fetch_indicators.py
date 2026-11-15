"""Twice-daily indicators job: fetch public series, assemble indicators.json (stdlib only).

Sources: US Treasury par yield curve CSV, FRED (DFEDTARU, DFEDTARL, DCOILBRENTEU, DHHNGSP, ICSA),
ECB reference rate (USD per EUR), TSA checkpoint numbers. Each source is fetched on its own;
a source that fails (or returns older data than the file already holds) keeps the previous
file's object for its key, so a card never blanks or goes back in time.

Rules stated here (the rest live in indicators_core):
- Card value = latest point; change = latest - previous point (claims: week-on-week;
  travellers: vs the same weekday a week before); low/high = true min/max over the 365 days up to asOf
  (shown on the bar); position and tone use the 2nd-98th percentile of that window instead, clamped 0..1,
  so one freak day can't push today's reading to an end of the bar.
- Claims asOf: FRED dates ICSA by the week-ending Saturday; the card shows the Thursday release (+5 days).
- Card verdicts: mortgages -> mortgage_verdict; brent/gas/eurusd/claims/travellers ->
  direction_verdict with thresholds brent 1.0, gas 0.1, eurusd 0.005, claims 10000,
  travellers 5% of the value.
- Borrowing: change over 20 trading days of avg(2y, 10y) (oldest row if fewer exist).
- Fed path: next meeting from the 6-month bill, the one after from the 2-year, each against the middle of
  the target range (DFEDTARU + DFEDTARL) / 2, or DFEDTARU - 0.125 when DFEDTARL is missing; `now` is DFEDTARU.
- Evening run: from 19:00 UTC a Fed meeting or claims release dated today has happened, so the Fed path and
  coming_up only use dates after today.
- Jobs (pulse row): average of the last 4 ICSA values vs the ICSA median over 365 days.
- Pulse price tones: brent and gas card tones. A pulse row with no data (new or previous) is null; the pulse
  is left out when fewer than two of borrowing, recession, jobs, price tones are available.
"""
import json
import os
import statistics
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import indicators_core as core  # noqa: E402
from indicator_sources import (  # noqa: E402
    ECB_URL, FRED_API_URL, FRED_CSV_URL, TREASURY_URL, TSA_URL, fetch_text, parse_ecb_csv,
    parse_fred_api, parse_fred_csv, parse_treasury_csv, parse_tsa_html,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CALENDAR_PATH = os.path.join(HERE, "indicator_calendar.json")
FRED_SERIES = ("DFEDTARU", "DFEDTARL", "DCOILBRENTEU", "DHHNGSP", "ICSA")
TENORS = ("1m", "2m", "3m", "4m", "6m", "1y", "2y", "3y", "5y", "7y", "10y", "20y", "30y")
HISTORY_DAYS = 400
PULSE_HISTORY_KEEP = 90

# id, source key, cadence, decimals
CARDS = (
    ("mortgages", "treasury", "daily", 2),
    ("brent", "DCOILBRENTEU", "daily", 2),
    ("gas", "DHHNGSP", "daily", 3),
    ("eurusd", "eurusd", "daily", 4),
    ("claims", "ICSA", "weekly", 0),
    ("travellers", "tsa", "daily", 0),
)
THRESHOLDS = {"brent": 1.0, "gas": 0.1, "eurusd": 0.005, "claims": 10000}
EVENT_ORDER = {"claims": 0, "fed": 1, "ecb": 2, "boe": 3}
EVENING_HOUR_UTC = 19
CLAIMS_RELEASE_LAG = 5  # week-ending Saturday -> Thursday release


def log(*a):
    print(*a, flush=True)


def _d(s):
    return date.fromisoformat(s)


def _num(x, decimals):
    return int(round(x)) if decimals == 0 else round(x, decimals)


def _series(points):
    """(date, value) pairs, oldest first, whatever order they came in."""
    return sorted(((d, float(v)) for d, v in (points or []) if v is not None), key=lambda p: p[0])


def _treasury_series(rows, tenor):
    return _series((r["date"], r[tenor]) for r in rows or [] if tenor in r)


def _year_window(series, as_of):
    start = _d(as_of) - timedelta(days=365)
    return [v for d, v in series if start < _d(d) <= _d(as_of)]


def _percentile(values, p):
    """Linear-interpolated p-th percentile (0..100) of a non-empty list."""
    v = sorted(values)
    k = (len(v) - 1) * p / 100.0
    i = int(k)
    j = min(i + 1, len(v) - 1)
    return v[i] + (v[j] - v[i]) * (k - i)


def _first_day(today, now):
    """The earliest date still to come: today, or tomorrow once the evening run (19:00 UTC) has passed."""
    if now is not None and now.hour >= EVENING_HOUR_UTC and now.date().isoformat() == today:
        return (_d(today) + timedelta(days=1)).isoformat()
    return today


def _not_older(new, old):
    """True unless the previous object carries a later asOf than the new one."""
    if not old or not new:
        return True
    return new.get("asOf", "") >= old.get("asOf", "")


def _card(card_id, cadence, decimals, series):
    as_of, value = series[-1]
    if card_id == "travellers":
        week_before = (_d(as_of) - timedelta(days=7)).isoformat()
        older = [p for p in series if p[0] <= week_before]
        prior = older[-1][1] if older else (series[-2][1] if len(series) > 1 else value)
    else:
        prior = series[-2][1] if len(series) > 1 else value
    change = value - prior
    window = _year_window(series, as_of)
    low, high = min(window), max(window)
    position = core.range_position(value, _percentile(window, 2), _percentile(window, 98))
    if card_id == "mortgages":
        verdict = core.mortgage_verdict(round(change, 4))
    else:
        threshold = value * 0.05 if card_id == "travellers" else THRESHOLDS[card_id]
        verdict = core.direction_verdict(round(change, 4), threshold)
    if card_id == "claims":
        as_of = (_d(as_of) + timedelta(days=CLAIMS_RELEASE_LAG)).isoformat()
    return {"id": card_id, "asOf": as_of, "cadence": cadence, "value": _num(value, decimals),
            "change": _num(change, decimals), "low": _num(low, decimals), "high": _num(high, decimals),
            "position": position, "verdict": verdict, "tone": core.tone(card_id, position)}


def _curve_points(row):
    return [{"m": t, "y": row[t]} for t in TENORS if t in row]


def _treasury_objects(rows):
    """curve, borrowing, recession from treasury rows (any order); None for each that can't be built."""
    rows = sorted((r for r in rows or [] if "2y" in r and "10y" in r), key=lambda r: r["date"], reverse=True)
    if not rows:
        return None, None, None
    top = rows[0]
    as_of = top["date"]
    month_cut = (_d(as_of) - timedelta(days=28)).isoformat()
    month_ago = next((r for r in rows if r["date"] <= month_cut), None)
    curve = {"asOf": as_of, "verdict": core.curve_verdict(top["10y"], top["2y"]),
             "today": _curve_points(top), "monthAgo": _curve_points(month_ago) if month_ago else []}
    back = rows[min(20, len(rows) - 1)]
    change20 = (top["2y"] + top["10y"]) / 2 - (back["2y"] + back["10y"]) / 2
    change20 = round(change20, 4)
    borrowing = {"asOf": as_of, "verdict": core.borrowing_verdict(change20),
                 "position": core.borrowing_position(change20)}
    recession = None
    with_3m = next((r for r in rows if "3m" in r), None)
    if with_3m:
        spread = round(with_3m["10y"] - with_3m["3m"], 2)
        recession = {"asOf": with_3m["date"], "verdict": core.recession_verdict(spread),
                     "spread": spread, "position": core.recession_position(spread)}
    return curve, borrowing, recession


def _fed_rate(rate_series, rows, calendar, today, lower_series=None, now=None):
    as_of, top = rate_series[-1]
    middle = (top + lower_series[-1][1]) / 2 if lower_series else top - 0.125  # ranges are 0.25 wide
    latest = sorted(rows or [], key=lambda r: r["date"], reverse=True)
    first = _first_day(today, now)
    meetings = [d for d in sorted((calendar or {}).get("fed", [])) if d >= first][:2]
    nxt = []
    for meeting, tenor in zip(meetings, ("6m", "2y")):
        row = next((r for r in latest if tenor in r), None)
        if row is None:
            break
        nxt.append({"date": meeting, "move": core.rate_move(row[tenor], middle)})
    return {"asOf": as_of, "now": round(top, 2), "next": nxt}


def coming_up(calendar, today, limit_days=60, now=None):
    """Next claims Thursday plus each bank's next meeting within limit_days, sorted by date.
    From 19:00 UTC on `today` (when `now` is given), today's events count as past."""
    first = _first_day(today, now)
    f = _d(first)
    thursday = f + timedelta(days=(3 - f.weekday()) % 7)
    out = [{"date": thursday.isoformat(), "event": "claims"}]
    end = (_d(today) + timedelta(days=limit_days)).isoformat()
    for bank in ("fed", "ecb", "boe"):
        upcoming = [d for d in sorted((calendar or {}).get(bank, [])) if first <= d <= end]
        if upcoming:
            out.append({"date": upcoming[0], "event": bank})
    out.sort(key=lambda e: (e["date"], EVENT_ORDER[e["event"]]))
    return out


def load_calendar(path=CALENDAR_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def build(sources, previous, today, calendar=None, now=None):
    """Assemble the indicators.json object from parsed series and the previous file (pure but for the clock)."""
    sources = sources or {}
    previous = previous or {}
    if calendar is None:
        calendar = load_calendar()
    now = now or datetime.now(timezone.utc)
    rows = sources.get("treasury") or []
    out = {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ")}

    # Rates and warning signs from the Treasury curve.
    for key, obj in zip(("curve", "borrowing", "recession"), _treasury_objects(rows)):
        old = previous.get(key)
        if obj is not None and _not_older(obj, old):
            out[key] = obj
        elif old is not None:
            out[key] = old

    rate = _series(sources.get("DFEDTARU"))
    lower = _series(sources.get("DFEDTARL"))
    old_fed = previous.get("fedRate")
    fed = _fed_rate(rate, rows, calendar, today, lower, now) if rate and rows else None
    if fed is not None and _not_older(fed, old_fed):
        out["fedRate"] = fed
    elif old_fed is not None:
        out["fedRate"] = old_fed
    elif rate:
        out["fedRate"] = _fed_rate(rate, [], calendar, today, lower, now)

    # Cards, fixed order; a card with neither new nor previous data is left out.
    prev_cards = {c.get("id"): c for c in previous.get("cards", []) if isinstance(c, dict)}
    cards = []
    for card_id, key, cadence, decimals in CARDS:
        series = _treasury_series(rows, "10y") if key == "treasury" else _series(sources.get(key))
        card = _card(card_id, cadence, decimals, series) if series else None
        old = prev_cards.get(card_id)
        if card is not None and _not_older(card, old):
            cards.append(card)
        elif old is not None:
            cards.append(old)
    out["cards"] = cards

    # Pulse: a row with no data is null, never a reassuring default.
    claims = _series(sources.get("ICSA"))
    prev_rows = (previous.get("pulse") or {}).get("rows") or {}
    if claims:
        last4 = [v for _, v in claims[-4:]]
        jobs = core.jobs_verdict(sum(last4) / len(last4), statistics.median(_year_window(claims, claims[-1][0])))
    else:
        jobs = prev_rows.get("jobs")
    borrowing = (out.get("borrowing") or {}).get("verdict")
    recession = (out.get("recession") or {}).get("verdict")
    tones = [c["tone"] for c in cards if c["id"] in ("brent", "gas")]
    history = [h for h in previous.get("pulseHistory", []) if isinstance(h, dict) and h.get("date") != today]
    available = sum(x is not None for x in (borrowing, recession, jobs)) + (1 if tones else 0)
    if available >= 2:
        verdict, position = core.pulse(borrowing, recession, jobs, tones)
        out["pulse"] = {"verdict": verdict, "from": core.pulse_from(history, verdict, today), "position": position,
                        "rows": {"borrowing": borrowing, "recession": recession, "jobs": jobs}}
        history = sorted(history + [{"date": today, "verdict": verdict}], key=lambda h: h["date"])
    else:
        history = [h for h in previous.get("pulseHistory", []) if isinstance(h, dict)]
    if history:
        out["pulseHistory"] = history[-PULSE_HISTORY_KEEP:]

    out["comingUp"] = coming_up(calendar, today, now=now)
    return {k: out[k] for k in ("updated", "pulse", "pulseHistory", "fedRate", "cards", "curve",
                                "borrowing", "recession", "comingUp") if k in out}


# ---------------------------------------------------------------- I/O

def _fetch_treasury(today):
    rows, errors = [], []
    for year in (today.year, today.year - 1):
        try:
            rows += parse_treasury_csv(fetch_text(TREASURY_URL.format(year=year), "csv"))
        except Exception as e:  # noqa: BLE001 - one year failing must not stop the other
            errors.append("%s: %s" % (year, e))
    if errors:
        log("treasury: partial/failed (%s)" % "; ".join(errors))
    seen, merged = set(), []
    for r in sorted(rows, key=lambda r: r["date"], reverse=True):
        if r["date"] not in seen:
            seen.add(r["date"])
            merged.append(r)
    return merged


def _fetch_fred(series_id, start):
    key = os.environ.get("FRED_API_KEY", "").strip()
    if key:
        points = parse_fred_api(fetch_text(FRED_API_URL.format(series_id, key, start), "json"))
    else:
        points = parse_fred_csv(fetch_text(FRED_CSV_URL.format(series_id), "csv"))
    return [p for p in points if p[0] >= start]


def fetch_sources(today):
    start = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    sources = {}

    def attempt(name, fn):
        try:
            data = fn()
        except Exception as e:  # noqa: BLE001 - each source stands alone
            log("%s: FAILED (%s: %s)" % (name, type(e).__name__, e))
            return
        if not data:
            log("%s: FAILED (no data)" % name)
            return
        newest = max(d[0] if isinstance(d, tuple) else d["date"] for d in data)
        log("%s: ok, %d points, latest %s" % (name, len(data), newest))
        sources[name] = data

    attempt("treasury", lambda: _fetch_treasury(today))
    via = "FRED API" if os.environ.get("FRED_API_KEY", "").strip() else "fredgraph.csv"
    log("fred: using %s" % via)
    for sid in FRED_SERIES:
        attempt(sid, lambda sid=sid: _fetch_fred(sid, start))
    attempt("eurusd", lambda: parse_ecb_csv(fetch_text(ECB_URL.format(start), "csv")).get("USD", []))
    attempt("tsa", lambda: parse_tsa_html(fetch_text(TSA_URL, "html")))
    return sources


def _without_updated(obj):
    return {k: v for k, v in (obj or {}).items() if k != "updated"}


def main():
    output = os.environ.get("INDICATORS_OUTPUT") or os.path.join(ROOT, "indicators.json")
    try:
        with open(output, encoding="utf-8") as f:
            previous = json.load(f)
    except (OSError, ValueError):
        previous = {}
    now = datetime.now(timezone.utc)
    today = now.date()
    sources = fetch_sources(today)
    out = build(sources, previous, today.isoformat(), calendar=load_calendar(), now=now)
    if _without_updated(out) == _without_updated(previous):
        log("indicators.json unchanged (%d sources ok)" % len(sources))
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    tmp = output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    os.replace(tmp, output)
    log("indicators.json written: %d cards, %d sources ok -> %s" % (len(out["cards"]), len(sources), output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
