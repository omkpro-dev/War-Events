import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gazetteer import INSTITUTIONS, PLACES, article_place, institution_place, place_for_iso2  # noqa: E402


class PlacesTests(unittest.TestCase):
    def test_place_for_iso2(self):
        self.assertEqual(place_for_iso2("GB")["label"], "UNITED KINGDOM")
        self.assertEqual(place_for_iso2("US")["label"], "UNITED STATES")
        self.assertEqual(place_for_iso2("EU")["label"], "EUROPEAN UNION")
        self.assertIsNone(place_for_iso2("ZZ"))
        self.assertIsNone(place_for_iso2(""))

    def test_place_for_iso2_name_exceptions(self):
        for code, label in (("RU", "RUSSIA"), ("KR", "SOUTH KOREA"), ("CZ", "CZECHIA"), ("CD", "DR CONGO"),
                            ("NL", "NETHERLANDS"), ("BA", "BOSNIA"), ("AE", "UNITED ARAB EMIRATES"), ("TR", "TURKEY")):
            self.assertEqual(place_for_iso2(code)["label"], label, code)

    def test_hong_kong(self):
        self.assertIn("HONG KONG, CHINA", PLACES)
        self.assertEqual(place_for_iso2("HK")["label"], "HONG KONG, CHINA")
        self.assertEqual(place_for_iso2("hk")["label"], "HONG KONG, CHINA")
        self.assertEqual(place_for_iso2("CN")["label"], "CHINA")   # China itself is unchanged
        self.assertEqual(article_place("Hang Seng slides on property worries", "", institutions=True)["label"],
                         "HONG KONG, CHINA")

    def test_pboc_with_either_apostrophe(self):
        for name in ("People's Bank of China", "People\u2019s Bank of China"):
            # institution table itself (the word "China" alone would also find CHINA through the place names)
            self.assertEqual((institution_place(name + " trims lending rate") or {}).get("label"), "CHINA", name)

    def test_institutions_only_when_asked(self):
        self.assertIsNone(article_place("Fed holds rates steady", ""))
        self.assertEqual(article_place("Fed holds rates steady", "", institutions=True)["label"], "UNITED STATES")

    def test_named_place_beats_institution(self):
        self.assertEqual(article_place("Japan exports fall as Fed holds", "", institutions=True)["label"], "JAPAN")

    def test_war_places_unchanged(self):
        self.assertEqual(article_place("Russian strikes hit Kyiv", "")["label"],
                         article_place("Russian strikes hit Kyiv", "", institutions=True)["label"])

    def test_institution_labels_exist_and_whole_words(self):
        for label in INSTITUTIONS.values():
            self.assertIn(label, PLACES)
        self.assertIsNone(article_place("Confederation of Sensexual things", "", institutions=True))
        self.assertEqual(article_place("ECB signals cut", "", institutions=True)["label"], "EUROPEAN UNION")
        self.assertEqual(article_place("Bank of England holds", "", institutions=True)["label"], "UNITED KINGDOM")

    def test_headline_institution_beats_description_place(self):
        desc = "The move comes as tariffs on Chinese goods weigh on prices."
        self.assertEqual(article_place("Fed holds rates steady", desc, institutions=True)["label"], "UNITED STATES")
        # War (institutions=False) is unchanged: no headline place, so the description decides
        self.assertEqual(article_place("Fed holds rates steady", desc)["label"], "CHINA")

    def test_description_place_beats_description_institution(self):
        self.assertEqual(article_place("Stocks slide on rate worries", "Fed officials spoke as shares fell in Japan.",
                                       institutions=True)["label"], "JAPAN")
        self.assertEqual(article_place("Stocks slide on rate worries", "Fed officials spoke on Friday.",
                                       institutions=True)["label"], "UNITED STATES")

    def test_european_markets_are_an_institution(self):
        t = "European shares fall as Nvidia CEO's exit raises doubts over AI boom"
        d = "Oil prices rose after Iran said it would cut exports."
        self.assertEqual(article_place(t, d, institutions=True)["label"], "EUROPEAN UNION")
        self.assertEqual(article_place(t, d)["label"], "IRAN")   # War unchanged


if __name__ == "__main__":
    unittest.main()
