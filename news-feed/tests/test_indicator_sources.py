import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import indicator_sources as src  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "indicators")


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class SourceParsers(unittest.TestCase):
    def test_treasury_columns_mapped(self):
        rows = src.parse_treasury_csv(fixture("treasury.csv"))
        self.assertEqual([r["date"] for r in rows], ["2026-11-13", "2026-11-12", "2026-11-10"])
        r = rows[1]
        self.assertEqual(r["1m"], 4.12)
        self.assertEqual(r["10y"], 5.10)
        self.assertEqual(r["30y"], 5.43)
        self.assertEqual(r["2m"], 4.26)
        self.assertEqual(len(r), 14)  # date + 13 tenors, "1.5 Month" ignored

    def test_latest_row_skips_blank_values(self):
        rows = src.parse_treasury_csv(fixture("treasury.csv"))
        self.assertNotIn("4m", rows[0])
        self.assertEqual(rows[0]["6m"], 4.42)

    def test_fred_dot_values_skipped(self):
        s = src.parse_fred_csv(fixture("fred_dgs.csv"))
        self.assertEqual(s, [("2026-11-11", 4.38), ("2026-11-12", 4.41)])
        self.assertEqual(src.latest(s), ("2026-11-12", 4.41))
        self.assertIsNone(src.latest([]))

    def test_fred_api_parsed(self):
        self.assertEqual(src.parse_fred_api(fixture("fred_api.json")), [("2026-11-12", 4.41)])

    def test_ecb_usd_series(self):
        d = src.parse_ecb_csv(fixture("ecb.csv"))
        self.assertEqual(d["USD"][0], ("2026-10-01", 1.1298))
        self.assertEqual(len(d["USD"]), 3)

    def test_tsa_rows_parsed(self):
        rows = src.parse_tsa_html(fixture("tsa.html"))
        self.assertEqual(rows[0], ("2026-11-12", 2484345))
        self.assertEqual(len(rows), 3)

    def test_tsa_unpadded_dates(self):
        html = "<table><tr><td>11/9/2026</td><td>2,535,058</td></tr></table>"
        self.assertEqual(src.parse_tsa_html(html), [("2026-11-09", 2535058)])

    def test_fetch_rejects_html_for_csv(self):
        with self.assertRaises(ValueError):
            src.check_body("<!DOCTYPE html><html></html>", "csv")
        with self.assertRaises(ValueError):
            src.check_body("  <html>", "json")
        src.check_body("a,b\n1,2\n", "csv")
        src.check_body("<table></table>", "html")

    def test_check_body_comment_prefixed_html_rejected_for_csv(self):
        with self.assertRaises(ValueError):
            src.check_body("<!-- x --><html>", "csv")

    def test_check_body_html_page_rejected_for_json(self):
        with self.assertRaises(ValueError):
            src.check_body("<html><body>Error</body></html>", "json")
        src.check_body(' [1]', "json")
        src.check_body('{"a":1}', "json")

    def test_header_only_csv_parses_empty(self):
        self.assertEqual(src.parse_treasury_csv('Date,"1 Mo"\n'), [])
        self.assertEqual(src.parse_fred_csv("observation_date,DGS10\n"), [])
        self.assertEqual(src.parse_ecb_csv("CURRENCY,TIME_PERIOD,OBS_VALUE\n"), {})

    def test_tsa_page_without_table_rejected(self):
        with self.assertRaises(ValueError):
            src.check_body("<html><body>Access denied</body></html>", "html")

    def test_expect_is_required(self):
        with self.assertRaises(TypeError):
            src.fetch_text("http://x.invalid")
        with self.assertRaises(ValueError):
            src.check_body("a,b", "xml")

    def test_urls(self):
        self.assertIn("2026", src.TREASURY_URL.format(year=2026))
        self.assertEqual(src.FRED_CSV_URL.format("DGS10"), "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10")


if __name__ == "__main__":
    unittest.main()
