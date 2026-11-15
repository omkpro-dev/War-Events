import json
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import fetch_indicators  # noqa: E402
from fetch_indicators import build, coming_up  # noqa: E402
from indicator_sources import parse_ecb_csv, parse_fred_csv, parse_treasury_csv, parse_tsa_html  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "indicators")
REPO = os.path.dirname(os.path.dirname(HERE))
TODAY = "2026-11-15"
CALENDAR = {"fed": ["2026-10-28", "2026-12-09", "2027-01-27"],
            "ecb": ["2026-12-17", "2027-02-04"],
            "boe": ["2026-11-05", "2026-12-17", "2027-02-04"]}
TOP_KEYS = ["updated", "pulse", "pulseHistory", "fedRate", "cards", "curve", "borrowing", "recession", "comingUp"]
CARD_IDS = ["mortgages", "brent", "gas", "eurusd", "claims", "travellers"]


def _read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def fixture_sources():
    fred = parse_fred_csv(_read("fred_dgs.csv"))
    return {
        "treasury": parse_treasury_csv(_read("treasury.csv")),
        "DFEDTARU": [("2026-11-12", 4.5), ("2026-11-13", 4.5)],
        "DFEDTARL": [("2026-11-12", 4.25), ("2026-11-13", 4.25)],
        "DCOILBRENTEU": fred,
        "DHHNGSP": fred,
        "ICSA": [("2026-10-31", 221000.0), ("2026-11-07", 228000.0)],
        "eurusd": parse_ecb_csv(_read("ecb.csv"))["USD"],
        "tsa": parse_tsa_html(_read("tsa.html")),
    }


def weekdays(start, end):
    d, out = date.fromisoformat(start), []
    while d <= date.fromisoformat(end):
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


class BuildTests(unittest.TestCase):
    def test_build_full_contract(self):
        out = build(fixture_sources(), {}, TODAY, calendar=CALENDAR)
        for k in TOP_KEYS:
            self.assertIn(k, out)
        self.assertEqual([c["id"] for c in out["cards"]], CARD_IDS)
        for c in out["cards"]:
            for k in ("asOf", "cadence", "value", "change", "low", "high", "position", "verdict", "tone"):
                self.assertIn(k, c, c["id"])
            self.assertTrue(0 <= c["position"] <= 1)
            self.assertIn(c["tone"], ("hot", "cool", "normal"))
        cards = {c["id"]: c for c in out["cards"]}
        self.assertEqual(cards["mortgages"]["value"], 5.15)
        self.assertEqual(cards["mortgages"]["asOf"], "2026-11-13")
        self.assertIn(cards["mortgages"]["verdict"], ("edging_up", "steady", "easing"))
        self.assertEqual(cards["claims"]["cadence"], "weekly")
        self.assertEqual(cards["travellers"]["value"], 2484345)
        self.assertEqual(out["curve"]["today"][0], {"m": "1m", "y": 4.10})
        self.assertIn(out["pulse"]["verdict"], ("cooling", "steady", "overheating"))
        self.assertEqual(set(out["pulse"]["rows"]), {"borrowing", "recession", "jobs"})
        self.assertEqual(out["recession"]["spread"], round(5.15 - 4.32, 2))
        json.dumps(out)  # serialisable

    def test_failed_source_keeps_previous(self):
        previous = build(fixture_sources(), {}, "2026-11-14", calendar=CALENDAR)
        prev_brent = next(c for c in previous["cards"] if c["id"] == "brent")
        for broken in ({"DCOILBRENTEU": []}, {"DCOILBRENTEU": None}):
            src = fixture_sources()
            src.update(broken)
            out = build(src, previous, TODAY, calendar=CALENDAR)
            brent = next(c for c in out["cards"] if c["id"] == "brent")
            self.assertEqual(brent, prev_brent)
        src = fixture_sources()
        del src["DCOILBRENTEU"], src["treasury"]
        out = build(src, previous, TODAY, calendar=CALENDAR)
        self.assertEqual(next(c for c in out["cards"] if c["id"] == "brent"), prev_brent)
        for k in ("curve", "borrowing", "recession"):
            self.assertEqual(out[k], previous[k])
        self.assertEqual([c["id"] for c in out["cards"]], CARD_IDS)

    def test_missing_source_without_previous_hides_card(self):
        src = fixture_sources()
        del src["tsa"]
        out = build(src, {}, TODAY, calendar=CALENDAR)
        self.assertEqual([c["id"] for c in out["cards"]], CARD_IDS[:-1])

    def test_stale_source_does_not_replace_newer_previous(self):
        previous = build(fixture_sources(), {}, TODAY, calendar=CALENDAR)
        src = fixture_sources()
        src["DCOILBRENTEU"] = [("2025-12-30", 60.0), ("2025-12-31", 61.0)]
        out = build(src, previous, TODAY, calendar=CALENDAR)
        self.assertEqual(next(c for c in out["cards"] if c["id"] == "brent"),
                         next(c for c in previous["cards"] if c["id"] == "brent"))

    def test_claims_change_is_week_on_week(self):
        src = fixture_sources()
        src["ICSA"] = [("2026-10-24", 200000.0), ("2026-10-31", 215000.0), ("2026-11-07", 230000.0)]
        claims = next(c for c in build(src, {}, TODAY, calendar=CALENDAR)["cards"] if c["id"] == "claims")
        self.assertEqual(claims["value"], 230000)
        self.assertEqual(claims["change"], 15000)
        self.assertEqual(claims["asOf"], "2026-11-12")  # week ending Sat 7 Nov, released Thu 12 Nov
        self.assertEqual(claims["verdict"], "rising")
        self.assertEqual((claims["low"], claims["high"]), (200000, 230000))

    def test_travellers_change_vs_same_weekday_a_week_before(self):
        src = fixture_sources()
        src["tsa"] = [("2026-11-12", 2500000), ("2026-11-11", 2000000), ("2026-11-05", 2400000)]
        t = next(c for c in build(src, {}, TODAY, calendar=CALENDAR)["cards"] if c["id"] == "travellers")
        self.assertEqual(t["change"], 100000)
        self.assertEqual(t["verdict"], "steady")  # 100k < 5% of 2.5M

    def test_curve_today_and_month_ago(self):
        rows = []
        for i, d in enumerate(weekdays("2026-09-01", "2026-11-13")):
            if d == "2026-10-16":  # exactly 28 days before asOf: missing, so the 15th is used
                continue
            rows.append({"date": d, "1m": round(3.0 + i / 100, 2), "3m": 4.0, "2y": 4.2, "10y": 4.5, "30y": 4.7})
        rows.reverse()  # newest first, as parse_treasury_csv returns
        src = fixture_sources()
        src["treasury"] = rows
        curve = build(src, {}, TODAY, calendar=CALENDAR)["curve"]
        self.assertEqual(curve["asOf"], "2026-11-13")
        self.assertEqual(curve["verdict"], "normal")
        self.assertEqual([p["m"] for p in curve["today"]], ["1m", "3m", "2y", "10y", "30y"])
        row_15 = next(r for r in rows if r["date"] == "2026-10-15")
        self.assertEqual(curve["monthAgo"][0], {"m": "1m", "y": row_15["1m"]})
        self.assertEqual(curve["today"][0], {"m": "1m", "y": rows[0]["1m"]})

    def test_borrowing_uses_20_trading_days(self):
        days = weekdays("2026-09-01", "2026-11-13")
        rows = [{"date": d, "3m": 4.0, "2y": 4.0 + 0.01 * i, "10y": 4.4 + 0.01 * i} for i, d in enumerate(days)]
        rows.reverse()
        src = fixture_sources()
        src["treasury"] = rows
        b = build(src, {}, TODAY, calendar=CALENDAR)["borrowing"]
        self.assertEqual(b["verdict"], "rising")  # +0.20 over 20 rows
        self.assertEqual(b["position"], 0.7)

    def test_fed_path_uses_6m_then_2y(self):
        src = fixture_sources()
        src["treasury"] = [{"date": "2026-11-13", "3m": 4.3, "6m": 4.10, "2y": 4.80, "10y": 4.9}]
        src["DFEDTARU"] = [("2026-11-13", 4.50)]
        fed = build(src, {}, TODAY, calendar=CALENDAR)["fedRate"]
        self.assertEqual(fed["now"], 4.5)
        self.assertEqual(fed["asOf"], "2026-11-13")
        self.assertEqual([n["move"] for n in fed["next"]], ["cut", "hike"])
        self.assertEqual([n["date"] for n in fed["next"]], ["2026-12-09", "2027-01-27"])

    def test_fed_path_with_dates_run_out(self):
        fed = build(fixture_sources(), {}, TODAY, calendar={"fed": ["2026-12-09"]})["fedRate"]
        self.assertEqual([n["date"] for n in fed["next"]], ["2026-12-09"])
        fed = build(fixture_sources(), {}, TODAY, calendar={})["fedRate"]
        self.assertEqual(fed["next"], [])

    def test_coming_up_sorted_and_windowed(self):
        got = coming_up(CALENDAR, TODAY)
        self.assertEqual(got, [{"date": "2026-11-19", "event": "claims"},
                               {"date": "2026-12-09", "event": "fed"},
                               {"date": "2026-12-17", "event": "ecb"},
                               {"date": "2026-12-17", "event": "boe"}])
        self.assertEqual(coming_up({"fed": ["2027-03-17"]}, TODAY), [{"date": "2026-11-19", "event": "claims"}])
        self.assertEqual(coming_up({}, "2026-11-19")[0], {"date": "2026-11-19", "event": "claims"})

    def test_pulse_history_appends_once_per_day(self):
        first = build(fixture_sources(), {}, TODAY, calendar=CALENDAR)
        again = build(fixture_sources(), first, TODAY, calendar=CALENDAR)
        self.assertEqual([h["date"] for h in again["pulseHistory"]], [TODAY])
        nxt = build(fixture_sources(), again, "2026-11-16", calendar=CALENDAR)
        self.assertEqual([h["date"] for h in nxt["pulseHistory"]], [TODAY, "2026-11-16"])

    def test_pulse_from_previous_verdict(self):
        previous = {"pulseHistory": [{"date": "2026-11-10", "verdict": "overheating"}]}
        out = build(fixture_sources(), previous, TODAY, calendar=CALENDAR)
        if out["pulse"]["verdict"] != "overheating":
            self.assertEqual(out["pulse"]["from"], "overheating")
        else:
            self.assertIsNone(out["pulse"]["from"])


def daily(base, amp, end="2026-11-13", days=380):
    """A calm daily series ending on `end`, oldest first: base +/- amp in a fixed zig-zag."""
    e = date.fromisoformat(end)
    return [((e - timedelta(days=i)).isoformat(), round(base + amp * (((i * 7) % 11) - 5) / 5, 3))
            for i in range(days - 1, -1, -1)]


def calm_sources():
    """Steady readings everywhere: flat curve, steady borrowing, no recession signal, steady jobs."""
    rows = [{"date": d, "3m": 4.0, "6m": 4.4, "2y": 4.2, "10y": 4.5} for d in weekdays("2026-08-01", "2026-11-13")]
    rows.reverse()
    claims_end = date.fromisoformat("2026-11-07")
    claims = [((claims_end - timedelta(weeks=i)).isoformat(), 220000.0 + (i % 3) * 1000) for i in range(55, -1, -1)]
    brent = daily(80.0, 5.0)
    brent[-1] = (brent[-1][0], 80.0)
    gas = daily(3.0, 0.2)
    gas[-1] = (gas[-1][0], 3.00)
    return {"treasury": rows, "DFEDTARU": [("2026-11-13", 4.5)], "DFEDTARL": [("2026-11-13", 4.25)],
            "DCOILBRENTEU": brent, "DHHNGSP": gas, "ICSA": claims}


class OutlierAndPulseTests(unittest.TestCase):
    def test_one_spike_does_not_drive_gas_tone_or_pulse(self):
        src = calm_sources()
        gas = list(src["DHHNGSP"])
        i = len(gas) - 120
        gas[i] = (gas[i][0], 30.72)  # one freak day in the year
        src["DHHNGSP"] = gas
        out = build(src, {}, TODAY, calendar=CALENDAR)
        card = next(c for c in out["cards"] if c["id"] == "gas")
        self.assertEqual(card["value"], 3.0)
        self.assertEqual(card["high"], 30.72)  # the bar still shows the true 1-year range
        self.assertEqual(card["low"], 2.8)
        self.assertTrue(0.3 <= card["position"] <= 0.7, card["position"])
        self.assertEqual(card["tone"], "normal")
        self.assertEqual(out["pulse"]["verdict"], "steady")

    def test_position_clamps_outside_percentile_band(self):
        src = calm_sources()
        gas = list(src["DHHNGSP"])
        gas[-1] = (gas[-1][0], 30.72)  # today's reading is the spike
        src["DHHNGSP"] = gas
        card = next(c for c in build(src, {}, TODAY, calendar=CALENDAR)["cards"] if c["id"] == "gas")
        self.assertEqual(card["position"], 1.0)
        self.assertEqual(card["tone"], "hot")

    def test_one_cool_price_alone_is_not_cooling(self):
        src = calm_sources()
        gas = list(src["DHHNGSP"])
        gas[-1] = (gas[-1][0], 2.5)  # genuinely at the bottom of its year
        src["DHHNGSP"] = gas
        out = build(src, {}, TODAY, calendar=CALENDAR)
        self.assertEqual(next(c for c in out["cards"] if c["id"] == "gas")["tone"], "cool")
        self.assertEqual(out["pulse"]["verdict"], "steady")

    def test_missing_jobs_row_is_null(self):
        src = calm_sources()
        del src["ICSA"]
        out = build(src, {}, TODAY, calendar=CALENDAR)
        self.assertIsNone(out["pulse"]["rows"]["jobs"])
        self.assertEqual(out["pulse"]["rows"]["borrowing"], "steady")
        self.assertEqual(out["pulse"]["rows"]["recession"], "none")
        json.dumps(out)

    def test_missing_treasury_rows_are_null(self):
        src = calm_sources()
        del src["treasury"]
        out = build(src, {}, TODAY, calendar=CALENDAR)
        self.assertEqual(out["pulse"]["rows"], {"borrowing": None, "recession": None, "jobs": "steady"})

    def test_pulse_left_out_with_fewer_than_two_inputs(self):
        src = {"DHHNGSP": calm_sources()["DHHNGSP"]}  # price tones only
        out = build(src, {}, TODAY, calendar=CALENDAR)
        self.assertNotIn("pulse", out)
        self.assertNotIn("pulseHistory", out)
        out = build({}, {"pulseHistory": [{"date": "2026-11-14", "verdict": "steady"}]}, TODAY, calendar=CALENDAR)
        self.assertNotIn("pulse", out)
        self.assertEqual(out["pulseHistory"], [{"date": "2026-11-14", "verdict": "steady"}])
        src = {"ICSA": calm_sources()["ICSA"], "DHHNGSP": calm_sources()["DHHNGSP"]}  # jobs + price tones
        self.assertIn("pulse", build(src, {}, TODAY, calendar=CALENDAR))


class ClaimsDateTests(unittest.TestCase):
    def test_claims_as_of_is_release_thursday(self):
        src = fixture_sources()
        src["ICSA"] = [("2026-10-31", 221000.0), ("2026-11-07", 228000.0)]
        claims = next(c for c in build(src, {}, TODAY, calendar=CALENDAR)["cards"] if c["id"] == "claims")
        self.assertEqual(claims["asOf"], "2026-11-12")
        self.assertEqual(date.fromisoformat(claims["asOf"]).weekday(), 3)


class FedMidpointTests(unittest.TestCase):
    def _fed(self, lower):
        src = fixture_sources()
        src["treasury"] = [{"date": "2026-11-13", "3m": 4.3, "6m": 4.20, "2y": 4.65, "10y": 4.9}]
        src["DFEDTARU"] = [("2026-11-13", 4.50)]
        if lower is None:
            del src["DFEDTARL"]
        else:
            src["DFEDTARL"] = [("2026-11-13", lower)]
        return build(src, {}, TODAY, calendar=CALENDAR)["fedRate"]

    def test_compares_to_middle_of_range(self):
        fed = self._fed(4.25)  # middle 4.375: 6m -0.175 hold, 2y +0.275 hike (vs the top: cut, hold)
        self.assertEqual(fed["now"], 4.5)
        self.assertEqual([n["move"] for n in fed["next"]], ["hold", "hike"])

    def test_missing_lower_bound_falls_back_to_top_minus_eighth(self):
        self.assertEqual([n["move"] for n in self._fed(None)["next"]], ["hold", "hike"])
        # a lower bound far below shows it is really read: middle 4.0 -> 6m +0.2 hold, 2y +0.65 hike
        src_low = self._fed(3.5)
        self.assertEqual([n["move"] for n in src_low["next"]], ["hold", "hike"])

    def test_lower_bound_is_fetched(self):
        self.assertIn("DFEDTARL", fetch_indicators.FRED_SERIES)


class EveningRunTests(unittest.TestCase):
    MORNING = datetime(2026, 12, 9, 7, 2, tzinfo=timezone.utc)
    EVENING = datetime(2026, 12, 9, 19, 2, tzinfo=timezone.utc)

    def test_fed_meeting_today_counts_until_the_evening_run(self):
        fed = build(fixture_sources(), {}, "2026-12-09", calendar=CALENDAR, now=self.MORNING)["fedRate"]
        self.assertEqual(fed["next"][0]["date"], "2026-12-09")
        fed = build(fixture_sources(), {}, "2026-12-09", calendar=CALENDAR, now=self.EVENING)["fedRate"]
        self.assertEqual(fed["next"][0]["date"], "2027-01-27")

    def test_coming_up_drops_today_after_the_evening_run(self):
        morning = coming_up(CALENDAR, "2026-12-09", now=self.MORNING)
        self.assertIn({"date": "2026-12-09", "event": "fed"}, morning)
        evening = coming_up(CALENDAR, "2026-12-09", now=self.EVENING)
        self.assertNotIn({"date": "2026-12-09", "event": "fed"}, evening)
        thu_am = datetime(2026, 11, 19, 7, 0, tzinfo=timezone.utc)
        thu_pm = datetime(2026, 11, 19, 19, 0, tzinfo=timezone.utc)
        self.assertEqual(coming_up({}, "2026-11-19", now=thu_am)[0], {"date": "2026-11-19", "event": "claims"})
        self.assertEqual(coming_up({}, "2026-11-19", now=thu_pm)[0], {"date": "2026-11-26", "event": "claims"})

    def test_build_passes_the_clock_to_coming_up(self):
        out = build(fixture_sources(), {}, "2026-12-09", calendar=CALENDAR, now=self.EVENING)
        self.assertNotIn("2026-12-09", [e["date"] for e in out["comingUp"] if e["event"] == "fed"])


class MainTests(unittest.TestCase):
    def test_main_all_sources_down_keeps_file(self):
        scratch = os.environ.get("INDICATORS_TEST_DIR") or os.path.join(HERE, "fixtures", "indicators")
        path = os.path.join(scratch, "_main_test_indicators.json")
        previous = build(fixture_sources(), {}, TODAY, calendar=CALENDAR)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(previous, f)
        try:
            with mock.patch.dict(os.environ, {"INDICATORS_OUTPUT": path}), \
                    mock.patch.object(fetch_indicators, "fetch_text", side_effect=OSError("down")), \
                    mock.patch("builtins.print"):
                self.assertEqual(fetch_indicators.main(), 0)
                with open(path, encoding="utf-8") as f:
                    first = f.read()
                self.assertEqual(json.loads(first)["cards"], previous["cards"])
                self.assertEqual(json.loads(first)["curve"], previous["curve"])
                self.assertEqual(fetch_indicators.main(), 0)  # nothing new: file left untouched
                with open(path, encoding="utf-8") as f:
                    self.assertEqual(f.read(), first)
        finally:
            os.remove(path)


class WorkflowAndCalendar(unittest.TestCase):
    def test_workflow_has_dispatch_and_main_only(self):
        with open(os.path.join(REPO, ".github", "workflows", "update-indicators.yml"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("branches: [main]", text)
        self.assertNotIn("economy-data", text)
        self.assertIn("indicators-data", text)
        self.assertIn("FRED_API_KEY: ${{ secrets.FRED_API_KEY }}", text)

    def test_calendar_file_is_sorted_iso_dates(self):
        with open(os.path.join(os.path.dirname(HERE), "indicator_calendar.json"), encoding="utf-8") as f:
            cal = json.load(f)
        self.assertEqual(sorted(cal), ["boe", "ecb", "fed"])
        for bank, dates in cal.items():
            self.assertEqual(dates, sorted(dates), bank)
            for d in dates:
                date.fromisoformat(d)

    def test_fed_dates_match_published_fomc_calendar(self):
        # federalreserve.gov/monetarypolicy/fomccalendars.htm (last update 12 Nov 2026): decision = second day.
        # 2027 has no December meeting (Oct 26-27 is labelled a strategy meeting, Nov 16-17 is the last);
        # the next one is 25-26 Jan 2028.
        with open(os.path.join(os.path.dirname(HERE), "indicator_calendar.json"), encoding="utf-8") as f:
            fed = json.load(f)["fed"]
        self.assertEqual([d for d in fed if d.startswith("2027")],
                         ["2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28", "2027-09-15",
                          "2027-10-27", "2027-11-17"])
        self.assertIn("2028-01-26", fed)


if __name__ == "__main__":
    unittest.main()
