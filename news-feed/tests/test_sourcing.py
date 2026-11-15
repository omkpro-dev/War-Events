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


class StateMediaCountOnce(unittest.TestCase):
    """Economy: outlets run by the same government count as one, so state media can't make a story on their own."""

    def test_one_governments_outlets_count_once_for_economy(self):
        self.assertFalse(passes_strict_rule(["Xinhua", "China Daily", "CGTN"]))
        self.assertFalse(passes_strict_rule(["TASS", "Xinhua", "China Daily"]))

    def test_state_outlet_still_counts_with_independent_ones(self):
        self.assertTrue(passes_strict_rule(["Xinhua", "Reuters", "Caixin Global"]))
        self.assertTrue(passes_strict_rule(["TASS", "Xinhua", "Reuters"]))

    def test_war_rule_unchanged(self):
        self.assertTrue(passes_war_rule(["Xinhua", "China Daily", "CGTN"]))


class EconomyNeedsABigNewsroom(unittest.TestCase):
    """Economy is big news only: besides 3 separate outlets, at least one is a top-tier international newsroom."""

    def test_domestic_outlets_alone_fail(self):
        from sourcing import passes_economy_rule
        self.assertFalse(passes_economy_rule(["The Economic Times", "Mint", "Business Standard", "Moneycontrol"]))

    def test_with_a_top_tier_newsroom_passes(self):
        from sourcing import passes_economy_rule
        self.assertTrue(passes_economy_rule(["Reuters", "Mint", "The Economic Times"]))

    def test_still_needs_three(self):
        from sourcing import passes_economy_rule
        self.assertFalse(passes_economy_rule(["Reuters", "Bloomberg"]))

    def test_state_media_still_count_once(self):
        from sourcing import passes_economy_rule
        self.assertFalse(passes_economy_rule(["Reuters", "Xinhua", "China Daily"]))
