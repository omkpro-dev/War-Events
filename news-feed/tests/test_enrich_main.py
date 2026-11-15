import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # news-feed
sys.path.insert(0, HERE)

import enrich_stories as en  # noqa: E402


def entry(headline="A neutral headline for the story", country=None):
    return en.parse_reply(json.dumps({"headline": headline, "summary": "Short summary.", "geo": 9,
                                      "country": country}), "war")


def load(path):
    with open(path) as f:
        return json.load(f)


def dump(data, path):
    with open(path, "w") as f:
        json.dump(data, f)


class FakeClock:
    """Each call moves time forward by `step` seconds, starting at 0."""
    def __init__(self, step):
        self.t, self.step = -step, step

    def __call__(self):
        self.t += self.step
        return self.t


class MainTests(unittest.TestCase):
    def setUp(self):
        # never /tmp: a scratch folder next to the tests (removed afterwards)
        self.tmp = tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(__file__)))
        self.stories_path = os.path.join(self.tmp.name, "stories.json")
        self.cache_path = os.path.join(self.tmp.name, "cache.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, stories, cache=None):
        dump(stories, self.stories_path)
        if cache is not None:
            dump(cache, self.cache_path)

    def run_main(self, section="war", key="test-key", budget=150, **kw):
        with mock.patch.multiple(en, STORIES=self.stories_path, CACHE=self.cache_path, KEY=key,
                                 SECTION=section, BUDGET_S=budget):
            en.main(**kw)
        return load(self.stories_path)

    # 1. time budget
    def test_asks_stop_once_budget_passes_and_output_is_written(self):
        stories = [{"id": "s%d" % i, "headline": "Original %d" % i, "body": ""} for i in range(4)]
        old = dict(entry("Older cached headline for story three"), v=en.PROMPT_V - 1)
        self.write(stories, {"s3": old})
        asked = []
        out = self.run_main(ask=lambda s: asked.append(s["id"]) or entry(), clock=FakeClock(100), budget=150)
        self.assertEqual(asked, ["s0"])                      # t=100 asks, t=200 is past the 150 s budget
        self.assertEqual([s["id"] for s in out], ["s0", "s1", "s2", "s3"])
        self.assertEqual(out[0]["headline"], "A neutral headline for the story")
        self.assertEqual(out[1]["headline"], "Original 1")    # waits for the next run
        self.assertEqual(out[3]["headline"], "Older cached headline for story three")   # cached still goes out
        self.assertIn("s0", load(self.cache_path))

    def test_budget_defaults_to_150_seconds(self):
        self.assertEqual(en.BUDGET_S, float(os.environ.get("ENRICH_BUDGET_S", "150")))

    def test_cache_saved_after_each_ask(self):
        self.write([{"id": "a", "headline": "A", "body": ""}, {"id": "b", "headline": "B", "body": ""},
                    {"id": "c", "headline": "C", "body": ""}], {})
        seen = []

        def ask(s):
            on_disk = load(self.cache_path) if os.path.exists(self.cache_path) else {}
            seen.append(sorted(on_disk))
            if s["id"] == "c":
                raise KeyboardInterrupt("job killed")   # simulates the runner killing the job mid-run
            return entry()

        with self.assertRaises(KeyboardInterrupt):
            self.run_main(ask=ask, clock=FakeClock(0))
        self.assertEqual(seen, [[], ["a"], ["a", "b"]])
        self.assertEqual(sorted(load(self.cache_path)), ["a", "b"])   # progress survived the kill
        self.assertEqual([f for f in os.listdir(self.tmp.name) if f.endswith(".tmp")], [])   # no temp leftovers

    def test_prompt_version_is_12(self):
        self.assertEqual(en.PROMPT_V, 12)

    # 5. placeless economy stories
    def test_economy_without_key_still_drops_placeless_and_writes(self):
        self.write([{"id": "p", "headline": "Placed", "place": "JAPAN", "body": ""},
                    {"id": "n", "headline": "No place", "place": "", "body": ""}], {})
        out = self.run_main(section="economy", key="", ask=lambda s: self.fail("no key: must not ask"))
        self.assertEqual([s["id"] for s in out], ["p"])

    def test_economy_without_key_uses_cached_country(self):
        self.write([{"id": "n", "headline": "No place", "place": "", "body": ""}], {"n": entry(country="GB")})
        out = self.run_main(section="economy", key="")
        self.assertEqual([(s["id"], s["place"]) for s in out], [("n", "UNITED KINGDOM")])

    def test_economy_with_no_new_asks_drops_placeless(self):
        self.write([{"id": "n", "headline": "No place", "place": "", "body": ""}], {"n": entry(country=None)})
        out = self.run_main(section="economy", ask=lambda s: self.fail("cached: must not ask"))
        self.assertEqual(out, [])

    def test_main_applies_country_for_economy(self):
        self.write([{"id": "n", "headline": "No place", "place": "", "body": ""},
                    {"id": "z", "headline": "Unknown country", "place": "", "body": ""}], {})
        out = self.run_main(section="economy", ask=lambda s: entry(country="GB" if s["id"] == "n" else "ZZ"))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["place"], "UNITED KINGDOM")
        self.assertIsNotNone(out[0]["lat"])

    def test_war_without_key_leaves_file_alone(self):
        self.write([{"id": "n", "headline": "No place", "place": "", "body": ""}])
        with open(self.stories_path) as f:
            before = f.read()
        self.run_main(section="war", key="")
        with open(self.stories_path) as f:
            self.assertEqual(f.read(), before)


if __name__ == "__main__":
    unittest.main()
