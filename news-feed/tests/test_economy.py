import io, json, os, sys, unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # news-feed
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import fetch_economy as e  # noqa: E402


class EconomyTests(unittest.TestCase):
    def test_economy_paths_do_not_touch_war_files(self):
        import fetch_economy as e, fetch_news as w
        self.assertNotEqual(os.path.basename(e.OUTPUT), os.path.basename(w.OUTPUT))
        self.assertNotEqual(e.STORE, w.STORE)
        wf = open(os.path.join(ROOT, ".github/workflows/update-economy.yml")).read()
        self.assertIn("economy-data", wf); self.assertNotIn("news-data", wf)
        self.assertNotIn("key_developments.json", wf); self.assertIn("SECTION: economy", wf)

    def test_news_workflow_push_only_on_main(self):
        wf = open(os.path.join(ROOT, ".github/workflows/update-news.yml")).read()
        self.assertIn("  push:\n    branches: [main]\n    paths:", wf)

    def test_economy_fetch_uses_no_paid_news_keys(self):
        # NewsAPI and GNews are War's shared free quota; Economy leans on free feeds only
        wf = open(os.path.join(ROOT, ".github/workflows/update-economy.yml")).read()
        self.assertNotIn("NEWSAPI_KEY", wf)
        self.assertNotIn("GNEWS_KEY", wf)

    def test_relevance_call_is_cheap(self):
        sent = []

        class Reply(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):   # never touches the network
            sent.append(json.loads(req.data))
            return Reply(json.dumps({"model": e.MODEL, "content": [{"type": "text", "text": "[0]"}]}).encode())

        arts = [{"title": "Fed holds interest rates steady", "outlet": "Reuters"}]
        with mock.patch.object(e, "ANTHROPIC_KEY", "test-key"), \
                mock.patch.object(e.urllib.request, "urlopen", fake_urlopen), mock.patch.object(e, "log", lambda *a: None):
            kept = e.ai_relevant(arts, {})
        self.assertEqual(kept, arts)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["thinking"], {"type": "disabled"})
        self.assertEqual(sent[0]["output_config"], {"effort": "low"})

    def test_is_economy(self):
        self.assertTrue(e.is_economy("Fed holds interest rates as inflation cools", ""))
        self.assertFalse(e.is_economy("Five stocks to buy before Christmas", ""))
        self.assertFalse(e.is_economy("Striker scores twice in cup final", ""))

    def test_placeless_article_is_kept(self):
        a = {"title": "Global stocks slide as bond yields jump on inflation worries", "url": "https://x.com/1",
             "outlet": "Reuters", "time": e.now_utc(), "desc": ""}
        q = e.qualify(a, e.now_utc())
        self.assertIsNotNone(q); self.assertEqual(q["place"], "")

    def test_keep_applies_strict_rule(self):
        two = {"id": "a", "score": 10, "outlets": ["Reuters", "AP"], "headline": "Stocks fall", "body": ""}
        three = dict(two, id="b", outlets=["Reuters", "AP", "Bloomberg"])
        sisters = dict(two, id="c", outlets=["Politico", "Politico Europe", "Reuters"])
        self.assertEqual([s["id"] for s in e.keep([two, three, sisters], [])], ["b"])

    def test_qualify_records_where_the_place_came_from(self):
        def q(title, desc):
            return e.qualify({"title": title, "url": "https://x.com/" + title.replace(" ", "-"), "outlet": "Reuters",
                              "time": e.now_utc(), "desc": desc}, e.now_utc())
        a = q("Fed holds interest rates steady", "The move comes as tariffs on Chinese goods weigh on prices.")
        self.assertEqual((a["place"], a["placeFrom"]), ("UNITED STATES", "inst"))
        self.assertEqual(q("Japan exports fall as tariffs bite", "")["placeFrom"], "title")
        b = q("Global stocks slide as bond yields jump", "Shares fell sharply in Japan on Friday.")
        self.assertEqual((b["place"], b["placeFrom"]), ("JAPAN", "desc"))

    def test_story_place_counts_countries_and_weights_headlines(self):
        arts = [{"place": "UNITED STATES", "placeFrom": "inst"},
                {"place": "WASHINGTON, UNITED STATES", "placeFrom": "title"},
                {"place": "CHINA", "placeFrom": "desc"}, {"place": "CHINA", "placeFrom": "desc"}]
        self.assertEqual(e.story_place(arts)["label"], "UNITED STATES")

    def test_story_place_sharpens_inside_the_winning_country(self):
        arts = [{"place": "TOKYO, JAPAN", "placeFrom": "title"}, {"place": "TOKYO, JAPAN", "placeFrom": "desc"},
                {"place": "JAPAN", "placeFrom": "title"}, {"place": "CHINA", "placeFrom": "desc"}]
        self.assertEqual(e.story_place(arts)["label"], "TOKYO, JAPAN")
        # a capital (spec 0, the country's own pin) never "sharpens": two Washington labels still give the country
        self.assertEqual(e.story_place([{"place": "WASHINGTON, UNITED STATES", "placeFrom": "title"}] * 2
                                       + [{"place": "UNITED STATES", "placeFrom": "inst"}])["label"], "UNITED STATES")
        self.assertEqual(e.story_place([])["label"], "")

    def test_fraud_sentencing_is_economy(self):
        self.assertTrue(e.is_economy("Former bank CEO sentenced to 12 years in prison for fraud", ""))
        self.assertTrue(e.is_economy("Hedge fund manager jailed for insider trading, police say", ""))


if __name__ == "__main__":
    unittest.main()
