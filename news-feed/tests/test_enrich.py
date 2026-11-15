import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enrich_stories import apply_country, keep_story, parse_reply, story_texts, system_prompt, user_message  # noqa: E402


class EnrichTests(unittest.TestCase):
    def test_story_texts_takes_three_different_outlets(self):
        story = {"sourceUrl": "https://a/1", "textUrls": ["https://b/2", "https://c/3", "https://d/4"],
                 "coverage": [{"o": "Reuters", "u": "https://a/1"}, {"o": "Politico", "u": "https://b/2"},
                              {"o": "Politico Europe", "u": "https://c/3"}, {"o": "FT", "u": "https://d/4"}]}
        got = story_texts(story, fetch=lambda u: "x" * 400)
        self.assertEqual([o for o, _ in got], ["Reuters", "Politico", "FT"])   # Politico Europe = same family

    def test_story_texts_skips_unreadable_and_google(self):
        story = {"sourceUrl": "https://news.google.com/rss/articles/abc", "textUrls": ["https://a/1"],
                 "coverage": [{"o": "AP", "u": "https://a/1"}]}
        self.assertEqual(story_texts(story, fetch=lambda u: "short"), [])

    def test_story_texts_source_url_without_coverage_uses_first_outlet(self):
        story = {"sourceUrl": "https://a/1", "outlets": ["Reuters", "AP"], "coverage": []}
        got = story_texts(story, fetch=lambda u: "x" * 400)
        self.assertEqual([o for o, _ in got], ["Reuters"])

    def test_story_texts_never_fetches_google_links(self):
        story = {"sourceUrl": "https://news.google.com/rss/articles/abc", "textUrls": ["https://a/1"],
                 "coverage": [{"o": "AP", "u": "https://a/1"}]}
        seen = []
        story_texts(story, fetch=lambda u: seen.append(u) or "x" * 400)
        self.assertEqual(seen, ["https://a/1"])

    def test_user_message_with_no_texts(self):
        msg = user_message({"headline": "Fed holds rates", "place": "", "outlets": ["Reuters", "AP", "FT"],
                            "coverage": [{"o": "AP", "h": "Fed keeps rates on hold"}]}, [])
        self.assertIn("Fed holds rates", msg)
        self.assertIn("Fed keeps rates on hold", msg)
        self.assertNotIn("not available", msg.lower())

    def test_user_message_lists_texts_and_place(self):
        msg = user_message({"headline": "H", "place": "Kyiv", "outlets": ["Reuters"], "coverage": []},
                           [("Reuters", "body one"), ("AP", "body two")])
        self.assertIn("Reuters", msg)
        self.assertIn("body two", msg)
        self.assertIn("Kyiv", msg)

    def test_economy_prompt_asks_for_country_and_synthesis(self):
        p = system_prompt("economy")
        self.assertIn('"country"', p)
        self.assertNotIn("Summarise THIS article only", p)

    def test_war_prompt_synthesises(self):
        self.assertNotIn("Summarise THIS article only", system_prompt("war"))

    def test_war_prompt_has_no_single_article_wording(self):
        p = system_prompt("war")
        for phrase in ("for this article", "the article actually says", "FULL ARTICLE", "the article says",
                       "from the article:"):
            self.assertNotIn(phrase, p)
        self.assertIn("the reporting", p)

    def test_parse_reply_country(self):
        r = parse_reply('{"headline":"Rates held steady by US central bank","summary":"s","country":"us"}', "economy")
        self.assertEqual(r["country"], "US")
        self.assertIsNone(parse_reply('{"summary":"s","country":"Mars"}', "economy")["country"])
        self.assertEqual(parse_reply('{"summary":"s","country":"EU"}', "economy")["country"], "EU")
        self.assertIsNone(parse_reply('{"summary":"s"}', "economy")["country"])

    def test_story_texts_bounds_fetch_attempts(self):
        story = {"sourceUrl": "https://a/0", "coverage": [{"o": "Outlet%d" % i, "u": "https://a/%d" % i} for i in range(10)]}
        calls = []
        got = story_texts(story, fetch=lambda u: calls.append(u) or "short")
        self.assertEqual(got, [])
        self.assertEqual(len(calls), 6)

    def test_unknown_section_fails_loudly(self):
        with self.assertRaises(ValueError):
            system_prompt("econmy")
        with self.assertRaises(ValueError):
            keep_story({"geo": 2}, "econmy")

    def test_min_geo_only_for_war(self):
        self.assertFalse(keep_story({"geo": 2}, "war"))
        self.assertTrue(keep_story({"geo": 2}, "economy"))

    def test_unknown_country_drops_story(self):
        for c in (None, "ZZ"):
            story = {"place": ""}
            self.assertFalse(apply_country(story, c))
            self.assertEqual(story["place"], "")
        story = {"place": ""}
        self.assertTrue(apply_country(story, "GB"))
        self.assertEqual(story["place"], "UNITED KINGDOM")
        self.assertIsNotNone(story["lat"])
        self.assertIsNotNone(story["lon"])
        self.assertTrue(story["cat"])
        kept = {"place": "KYIV, UKRAINE", "lat": 1, "lon": 2, "cat": "x"}
        self.assertTrue(apply_country(kept, "GB"))
        self.assertEqual(kept, {"place": "KYIV, UKRAINE", "lat": 1, "lon": 2, "cat": "x"})


if __name__ == "__main__":
    unittest.main()


class EconomyScore(unittest.TestCase):
    """The 0-10 score after the summary, as War's "geo" score: how much a story is economy news."""

    def test_parse_reply_reads_econ_score(self):
        self.assertEqual(parse_reply('{"summary":"s","econ":8}', "economy")["econ"], 8)
        self.assertEqual(parse_reply('{"summary":"s","econ":42}', "economy")["econ"], 10)
        self.assertEqual(parse_reply('{"summary":"s","econ":"x"}', "economy")["econ"], 10)
        self.assertEqual(parse_reply('{"summary":"s"}', "economy")["econ"], 10)

    def test_low_econ_score_dropped_from_economy(self):
        self.assertFalse(keep_story({"econ": 3}, "economy"))
        self.assertTrue(keep_story({"econ": 7}, "economy"))
        self.assertFalse(keep_story({"econ": 6}, "economy"))
        self.assertTrue(keep_story({}, "economy"))   # cached before the score existed: kept until re-asked

    def test_scores_only_apply_to_their_own_section(self):
        self.assertTrue(keep_story({"econ": 1, "geo": 9}, "war"))
        self.assertTrue(keep_story({"econ": 9, "geo": 1}, "economy"))

    def test_economy_prompt_asks_for_econ_score(self):
        self.assertIn('"econ"', system_prompt("economy"))
        self.assertNotIn('"econ"', system_prompt("war"))

    def test_economy_reasked_but_war_cache_kept(self):
        from enrich_stories import prompt_version
        self.assertEqual(prompt_version("war"), 12)
        self.assertGreater(prompt_version("economy"), 12)
        self.assertEqual(parse_reply('{"summary":"s"}', "economy")["v"], prompt_version("economy"))
        self.assertEqual(parse_reply('{"summary":"s"}', "war")["v"], 12)


class EconomyScoreIsInternational(unittest.TestCase):
    """Economy is international news: a story that matters mainly inside one country scores low."""

    def test_prompt_rewards_international_and_marks_domestic_low(self):
        p = system_prompt("economy")
        self.assertIn("international", p)
        self.assertIn("mainly inside one country", p)

    def test_rescored_with_new_guide(self):
        from enrich_stories import prompt_version
        self.assertEqual(prompt_version("economy"), 15)
