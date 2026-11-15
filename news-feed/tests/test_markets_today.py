import json, os, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # news-feed
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import markets_today as m  # noqa: E402

NOW = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)


def art(key, title, hours=1, outlet="Reuters", desc=""):
    t = (NOW - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"key": key, "title": title, "outlet": outlet, "time": t, "desc": desc}


class MarketsTests(unittest.TestCase):
    def test_selects_market_headlines_only(self):
        arts = [art("k1", "Wall Street falls as Treasury yields climb", 1),
                art("k2", "Chef opens new restaurant in Lyon this week", 2),
                art("k3", "Brent crude rises on supply worries", 3)]
        sel = m.select_articles(arts, NOW)
        self.assertEqual([a["key"] for a in sel], ["k1", "k3"])
        self.assertEqual([a["id"] for a in sel], ["a1", "a2"])

    def test_window_is_24_hours(self):
        arts = [art("old", "Nikkei slides at the open", 25), art("new", "Nikkei slides at the close", 23)]
        self.assertEqual([a["key"] for a in m.select_articles(arts, NOW)], ["new"])

    def test_selection_newest_first_and_limited(self):
        arts = [art(f"k{i}", f"Stocks move number {i}", i) for i in range(1, 10)]
        sel = m.select_articles(arts, NOW, limit=3)
        self.assertEqual([a["key"] for a in sel], ["k1", "k2", "k3"])

    def test_prompt_mentions_topics_and_headlines(self):
        sel = m.select_articles([art("k1", "Wall Street falls", 1, desc="Shares dropped 1.2%.")], NOW)
        p = m.build_prompt(sel)
        for t in m.TOPICS:
            self.assertIn(t, p)
        self.assertIn("a1", p); self.assertIn("Wall Street falls", p); self.assertIn("Shares dropped 1.2%.", p)

    @staticmethod
    def read(path):
        with open(path) as f:
            return f.read()

    def test_validate_survives_malformed_reply(self):
        sel = self.sel2()
        self.assertEqual(m.validate("nope", sel), [])
        self.assertEqual(m.validate(None, sel), [])
        bad = [{"topic": "stocks", "text": "Wall Street fell 1.2%.", "ids": [["a1"]]},
               {"topic": "oil", "text": "Brent rose.", "ids": "a2"},
               {"topic": "crypto", "ids": ["a3"]},
               {"topic": "bonds", "text": 5, "ids": ["a1"]},
               {"topic": ["asia"], "text": "x", "ids": ["a1"]},
               "junk", 7,
               {"topic": "europe", "text": "Wall Street fell 1.2%.", "ids": [["a1"], "a1", 3]}]
        out = m.validate(bad, sel)
        self.assertEqual([i["topic"] for i in out], ["europe"])

    def sel2(self):
        return m.select_articles([art("k1", "Wall Street fell 1.2% on Friday", 1, "Reuters"),
                                  art("k2", "Brent crude rises to $82.5 a barrel", 2, "AP"),
                                  art("k3", "Bitcoin steadies", 3, "Reuters")], NOW)

    def test_validate_drops_unknown_and_repeated_topics(self):
        items = [{"topic": "stocks", "text": "Wall Street fell 1.2%.", "ids": ["a1"]},
                 {"topic": "stocks", "text": "Wall Street fell 1.2% again.", "ids": ["a1"]},
                 {"topic": "weather", "text": "Wall Street fell.", "ids": ["a1"]},
                 {"topic": "oil", "text": "Brent rose.", "ids": ["zz"]}]
        out = m.validate(items, self.sel2())
        self.assertEqual([i["topic"] for i in out], ["stocks"])

    def test_validate_drops_number_not_in_sources(self):
        items = [{"topic": "stocks", "text": "Wall Street fell 3.4% on Friday.", "ids": ["a1"]},
                 {"topic": "oil", "text": "Brent rose to $82.5 a barrel.", "ids": ["a2"]}]
        out = m.validate(items, self.sel2())
        self.assertEqual([i["topic"] for i in out], ["oil"])

    def test_validate_orders_topics_and_names_outlets(self):
        items = [{"topic": "crypto", "text": "Bitcoin steadied.", "ids": ["a3"]},
                 {"topic": "stocks", "text": "Wall Street fell 1.2%.", "ids": ["a1", "a3"]}]
        out = m.validate(items, self.sel2())
        self.assertEqual([i["topic"] for i in out], ["stocks", "crypto"])
        self.assertEqual(out[0]["outlets"], ["Reuters"])
        out2 = m.validate([{"topic": "oil", "text": "Brent rose.", "ids": ["a2", "a1"]}], self.sel2())
        self.assertEqual(out2[0]["outlets"], ["AP", "Reuters"])

    def run_main(self, tmp, arts, key="k", ask=None):
        seen = os.path.join(tmp, "seen.json"); out = os.path.join(tmp, "markets_today.json")
        cache = os.path.join(tmp, "cache.json")
        with open(seen, "w") as f:
            json.dump(arts, f)
        with mock.patch.object(m, "SEEN", seen), mock.patch.object(m, "OUTPUT", out), \
             mock.patch.object(m, "CACHE", cache), mock.patch.object(m, "ANTHROPIC_KEY", key), \
             mock.patch.object(m, "now_utc", lambda: NOW), mock.patch.object(m, "ask", ask):
            return m.main(), out, cache

    def test_same_input_skips_call(self):
        arts = [art("k1", "Wall Street fell 1.2% on Friday", 1)]
        reply = json.dumps({"items": [{"topic": "stocks", "text": "Wall Street fell 1.2%.", "ids": ["a1"]}]})
        with tempfile.TemporaryDirectory(dir="/Volumes/OMK PRO SSD/WarEventsBuild") as tmp:
            calls = mock.Mock(return_value=reply)
            rc, out, cache = self.run_main(tmp, arts, ask=calls)
            self.assertEqual(rc, 0); self.assertEqual(calls.call_count, 1)
            with open(out) as f:
                data = json.load(f)
            self.assertEqual(data["items"][0]["outlets"], ["Reuters"]); self.assertEqual(data["outlets"], ["Reuters"])
            self.assertEqual(data["updated"], "2026-11-15T15:00:00Z")
            first = self.read(out)
            calls2 = mock.Mock(return_value="{}")
            rc, _, _ = self.run_main(tmp, arts, ask=calls2)
            self.assertEqual(rc, 0); calls2.assert_not_called()
            self.assertEqual(self.read(out), first)

    def test_no_key_exits_without_writing(self):
        with tempfile.TemporaryDirectory(dir="/Volumes/OMK PRO SSD/WarEventsBuild") as tmp:
            calls = mock.Mock()
            rc, out, _ = self.run_main(tmp, [art("k1", "Wall Street fell", 1)], key="", ask=calls)
            self.assertEqual(rc, 0); calls.assert_not_called(); self.assertFalse(os.path.exists(out))

    def test_economy_store_keeps_description(self):
        import fetch_economy as e
        now = e.now_utc()
        q = e.qualify({"title": "Central bank raises interest rates to fight inflation", "url": "https://www.reuters.com/x",
                       "outlet": "Reuters", "time": now, "desc": "Rates rose by 0.25% on Thursday."}, now)
        self.assertEqual(q["desc"], "Rates rose by 0.25% on Thursday.")

    def test_workflow_lists_markets_files(self):
        wf = self.read(os.path.join(ROOT, ".github/workflows/update-economy.yml"))
        self.assertGreaterEqual(wf.count("markets_today.json"), 2)
        self.assertEqual(wf.count("news-feed/markets_cache.json"), 2)
        self.assertIn("python news-feed/markets_today.py", wf)
        self.assertIn('      - "news-feed/markets_today.py"', wf)
        self.assertLess(wf.index("Summaries + impact"), wf.index("python news-feed/markets_today.py"))
        self.assertLess(wf.index("python news-feed/markets_today.py"), wf.index("Publish to economy-data"))


if __name__ == "__main__":
    unittest.main()
