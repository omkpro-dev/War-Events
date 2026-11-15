"""Studies: research and reports straight from the institutions (IMF, OECD, BIS, ECB...), shown in Economy as
'Study'. One publication each, so they skip the 3-outlet rule; the AI study check and the 0-10 score still apply."""
import os
import sys
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetch_economy as fe  # noqa: E402
import enrich_stories as en  # noqa: E402


def art(title, url="https://www.oecd.org/en/publications/youth-2026.html", inst="OECD", desc="", age_days=1):
    now = fe.now_utc()
    return {"title": title, "url": url, "outlet": inst, "desc": desc, "time": now - timedelta(days=age_days)}


class StudyItems(unittest.TestCase):
    def test_recent_study_qualifies(self):
        q = fe.qualify_study(art("Youth unemployment across OECD countries rose in 2026"), fe.now_utc())
        self.assertIsNotNone(q)
        self.assertEqual(q["outlet"], "OECD")

    def test_old_study_dropped(self):
        self.assertIsNone(fe.qualify_study(art("Global trade outlook for the coming decade", age_days=fe.STUDY_DAYS + 1), fe.now_utc()))

    def test_story_marked_as_study_with_one_source(self):
        s = fe.build_study(fe.qualify_study(art("Youth unemployment across OECD countries rose in 2026"), fe.now_utc()), fe.now_utc())
        self.assertEqual(s["kind"], "study")
        self.assertEqual(s["outlets"], ["OECD"])
        self.assertTrue(s["id"].startswith("study-"))
        self.assertEqual(s["textUrls"], ["https://www.oecd.org/en/publications/youth-2026.html"])
        self.assertIn("Reported by:", s["body"])

    def test_study_about_a_country_pinned_there(self):
        s = fe.build_study(fe.qualify_study(art("Japan's wage growth and inflation: an assessment", inst="IMF",
                                                url="https://www.imf.org/en/x"), fe.now_utc()), fe.now_utc())
        self.assertEqual(fe.country_of(s["place"]), "JAPAN")

    def test_global_study_pinned_at_institution_home(self):
        s = fe.build_study(fe.qualify_study(art("Convergence within and between countries", inst="BIS",
                                                url="https://www.bis.org/publ/work1.htm"), fe.now_utc()), fe.now_utc())
        self.assertEqual(s["place"], fe.place_for_iso2("CH")["label"])

    def test_google_link_not_read_for_text(self):
        s = fe.build_study(fe.qualify_study(art("Global debt monitor 2026", inst="IMF",
                                                url="https://news.google.com/rss/articles/abc"), fe.now_utc()), fe.now_utc())
        self.assertEqual(s["textUrls"], [])

    def test_newest_studies_kept_up_to_cap(self):
        now = fe.now_utc()
        items = [fe.build_study(fe.qualify_study(art("Study number %d on global trade and prices" % i,
                                                     url="https://www.oecd.org/%d" % i, age_days=i % 6), now), now)
                 for i in range(fe.MAX_STUDIES + 4)]
        picked = fe.pick_studies(items)
        self.assertEqual(len(picked), fe.MAX_STUDIES)
        self.assertEqual(picked, sorted(picked, key=lambda s: s["time"], reverse=True))

    def test_every_study_source_has_a_home(self):
        for name, url, home in fe.STUDY_SOURCES:
            self.assertIsNotNone(fe.place_for_iso2(home), name)


class StudySummaries(unittest.TestCase):
    def test_summary_request_says_it_is_a_study(self):
        msg = en.user_message({"kind": "study", "outlets": ["OECD"], "headline": "Youth jobs report"}, [])
        self.assertIn("study published by OECD", msg)

    def test_news_request_unchanged(self):
        msg = en.user_message({"outlets": ["Reuters"], "headline": "Fed holds rates"}, [])
        self.assertNotIn("study", msg)


if __name__ == "__main__":
    unittest.main()
