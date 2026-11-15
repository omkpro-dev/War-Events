"""Offline replay: stored articles -> cluster -> build_story -> the module's story filter, for both pipelines.
No network, no API key; `now` is fixed to the newest article so the result never depends on the clock."""
import json, os, sys, unittest
from datetime import timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # news-feed
sys.path.insert(0, HERE)

import fetch_economy as eco  # noqa: E402
import fetch_news as war  # noqa: E402
from sourcing import distinct_outlets, passes_strict_rule, passes_war_rule  # noqa: E402

FIX = os.path.join(HERE, "tests", "fixtures")
NO_RULES = {"ids": set(), "keys": set(), "phrases": []}


def replay(mod, name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        arts = [a for a in json.load(f) if isinstance(a, dict) and a.get("key")]
    now = max(mod.parse_time(a["time"]) for a in arts)
    recent = [a for a in arts if mod.parse_time(a["time"]) >= now - timedelta(hours=mod.MAX_AGE_HOURS)]
    built = [mod.build_story(g, now) for g in mod.cluster(recent)]
    return built, now


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.war_built, _ = replay(war, "war_seen.json")
        cls.war_kept = war.keep(cls.war_built, NO_RULES)
        cls.eco_built, _ = replay(eco, "economy_seen.json")
        cls.eco_kept = eco.keep(cls.eco_built, [])

    def test_war_keeps_stories_and_all_pass_the_war_rule(self):
        self.assertGreaterEqual(len(self.war_kept), 1)
        for s in self.war_kept:
            self.assertTrue(passes_war_rule(s["outlets"]), s["headline"])
            self.assertGreaterEqual(s["score"], war.MIN_SCORE)

    def test_war_rule_actually_filters(self):
        # the fixture holds stories that fail the rule, so a bypassed keep() would be caught above
        self.assertLess(len(self.war_kept), len(self.war_built))
        self.assertTrue(any(not passes_war_rule(s["outlets"]) for s in self.war_built))

    def test_economy_keeps_stories_and_all_pass_the_strict_rule(self):
        self.assertGreaterEqual(len(self.eco_kept), 1)
        for s in self.eco_kept:
            self.assertTrue(passes_strict_rule(s["outlets"]), s["headline"])
            self.assertGreaterEqual(len(distinct_outlets(s["outlets"])), 3)

    def test_economy_rule_actually_filters(self):
        self.assertLess(len(self.eco_kept), len(self.eco_built))
        self.assertTrue(any(not passes_strict_rule(s["outlets"]) for s in self.eco_built))

    def test_no_economy_headline_matches_the_exclude_list(self):
        import html
        for s in self.eco_kept:
            self.assertIsNone(eco.EXCLUDE_RX.search(html.unescape(s["headline"])), s["headline"])

    def test_kept_stories_are_well_formed(self):
        for s in self.war_kept + self.eco_kept:
            self.assertTrue(s["id"] and s["headline"] and s["outlets"])
        for s in self.war_kept:   # War stories always have a pin; Economy ones without one get it from the AI's country later
            self.assertIsInstance(s["lat"], (int, float), s["headline"])
            self.assertIsInstance(s["lon"], (int, float), s["headline"])


if __name__ == "__main__":
    unittest.main()
