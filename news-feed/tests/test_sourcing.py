import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sourcing import distinct_outlets, outlet_family, passes_strict_rule, passes_war_rule  # noqa: E402


class SourcingRules(unittest.TestCase):
    def test_three_outlets_pass_both_rules(self):
        o = ["Reuters", "Dawn", "The Hindu"]
        self.assertTrue(passes_war_rule(o)); self.assertTrue(passes_strict_rule(o))

    def test_two_top_tier_pass_war_only(self):
        o = ["Reuters", "AP"]
        self.assertTrue(passes_war_rule(o)); self.assertFalse(passes_strict_rule(o))

    def test_top_tier_plus_tier2_fails_war(self):
        self.assertFalse(passes_war_rule(["Reuters", "Dawn"]))   # Dawn is not TIER1

    def test_one_outlet_fails(self):
        self.assertFalse(passes_war_rule(["Reuters"])); self.assertFalse(passes_strict_rule(["Reuters"]))

    def test_sister_brands_count_once(self):
        o = ["Politico", "Politico Europe", "Reuters"]
        self.assertEqual(distinct_outlets(o), ["Politico", "Reuters"])
        self.assertFalse(passes_strict_rule(o))

    def test_duplicates_count_once(self):
        self.assertFalse(passes_strict_rule(["Reuters", "Reuters", "AP"]))

    def test_france24_editions_merge(self):
        self.assertEqual(outlet_family("France 24 Africa"), "France 24")
        self.assertEqual(outlet_family("Dawn"), "Dawn")
        self.assertFalse(passes_war_rule(["France 24", "France 24 Africa"]))

    def test_scmp_names_merge(self):
        self.assertEqual(outlet_family("SCMP"), outlet_family("South China Morning Post"))
        self.assertFalse(passes_strict_rule(["SCMP", "South China Morning Post", "Reuters"]))


if __name__ == "__main__":
    unittest.main()
