"""Pure rules for the twice-daily indicators job (no I/O).

Rules:
- curve_verdict: 10y minus 2y > 0.1 normal; -0.1..0.1 flat; < -0.1 inverted.
- borrowing_verdict: 20-trading-day change of avg(2y, 10y): > 0.15 rising, < -0.15 falling, else steady.
- borrowing_position: change -0.5..+0.5 mapped linearly to 0..1, clamped.
- recession_verdict: 10y-3m spread >= 0 none; -0.5 <= s < 0 watch; < -0.5 warning.
- recession_position: spread +1.0..-1.5 mapped linearly to 0..1, clamped.
- rate_move: market yield below policy rate by more than 0.25 -> cut, above by more than 0.25 -> hike, else hold.
- range_position: (value-low)/(high-low) clamped to 0..1; 0.5 when high == low.
- direction_verdict: change > threshold rising, < -threshold falling, else steady.
  mortgage_verdict uses threshold 0.03 and maps rising->edging_up, falling->easing.
- tone: hot when position >= 0.8 and card is mortgages/brent/gas; cool when position <= 0.2; else normal.
- jobs_verdict: 4-week average vs 1-year median: > +10% weakening, < -10% strong, else steady.
- pulse: score = borrowing (rising +1 / falling -1) + price tones (hot +1 / cool -1 each)
  + jobs (strong +1 / weakening -1) + recession (watch -0.5 / warning -1).
  score >= 1.5 overheating, <= -1 cooling, else steady; position = (clamp(score, -3, 3) + 3) / 6.
  Corroboration: overheating needs at least two inputs pointing up (rising, hot, strong), cooling at least
  two pointing down (falling, cool, weakening, watch/warning); otherwise steady. A missing input (None) adds nothing.
- pulse_from: the verdict before today's, if it differs and the change happened within the last 30 days.
All positions are rounded to 3 decimals.
"""
from datetime import date

HOT_CARDS = {"mortgages", "brent", "gas"}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def curve_verdict(y10, y2):
    d = y10 - y2
    if d > 0.1:
        return "normal"
    if d < -0.1:
        return "inverted"
    return "flat"


def borrowing_verdict(change20):
    if change20 > 0.15:
        return "rising"
    if change20 < -0.15:
        return "falling"
    return "steady"


def borrowing_position(change20):
    return round(_clamp((change20 + 0.5) / 1.0, 0.0, 1.0), 3)


def recession_verdict(spread_10y_3m):
    if spread_10y_3m >= 0:
        return "none"
    if spread_10y_3m >= -0.5:
        return "watch"
    return "warning"


def recession_position(spread):
    return round(_clamp((1.0 - spread) / 2.5, 0.0, 1.0), 3)


def rate_move(market_yield, policy_rate):
    d = market_yield - policy_rate
    if d < -0.25:
        return "cut"
    if d > 0.25:
        return "hike"
    return "hold"


def range_position(value, low, high):
    if high == low:
        return 0.5
    return round(_clamp((value - low) / (high - low), 0.0, 1.0), 3)


def direction_verdict(change, threshold):
    if change > threshold:
        return "rising"
    if change < -threshold:
        return "falling"
    return "steady"


def mortgage_verdict(change):
    v = direction_verdict(change, 0.03)
    return {"rising": "edging_up", "falling": "easing"}.get(v, v)


def tone(card_id, position):
    if position >= 0.8 and card_id in HOT_CARDS:
        return "hot"
    if position <= 0.2:
        return "cool"
    return "normal"


def jobs_verdict(latest4wk_avg, year_median):
    if latest4wk_avg > year_median * 1.10:
        return "weakening"
    if latest4wk_avg < year_median * 0.90:
        return "strong"
    return "steady"


def pulse(borrowing, recession, jobs, price_tones):
    score = {"rising": 1.0, "falling": -1.0}.get(borrowing, 0.0)
    score += sum(1.0 if t == "hot" else -1.0 if t == "cool" else 0.0 for t in price_tones)
    score += {"strong": 1.0, "weakening": -1.0}.get(jobs, 0.0)
    score += {"watch": -0.5, "warning": -1.0}.get(recession, 0.0)
    ups = (borrowing == "rising") + (jobs == "strong") + sum(t == "hot" for t in price_tones)
    downs = ((borrowing == "falling") + (jobs == "weakening") + (recession in ("watch", "warning"))
             + sum(t == "cool" for t in price_tones))
    if score >= 1.5 and ups >= 2:
        verdict = "overheating"
    elif score <= -1 and downs >= 2:
        verdict = "cooling"
    else:
        verdict = "steady"
    return verdict, round((_clamp(score, -3, 3) + 3) / 6, 3)


def pulse_from(history, verdict, today):
    """Verdict before today's, if it differs and changed within the last 30 days."""
    past = sorted((h for h in history if h["date"] < today), key=lambda h: h["date"])
    if not past:
        return None
    if past[-1]["verdict"] != verdict:
        prev, changed = past[-1]["verdict"], today
    else:
        i = len(past) - 1
        while i >= 0 and past[i]["verdict"] == verdict:
            i -= 1
        if i < 0:
            return None
        prev, changed = past[i]["verdict"], past[i + 1]["date"]
    age = (date.fromisoformat(today) - date.fromisoformat(changed)).days
    return prev if age <= 30 else None
