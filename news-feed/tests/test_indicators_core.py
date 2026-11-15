import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators_core import (  # noqa: E402
    borrowing_position, borrowing_verdict, curve_verdict, direction_verdict, jobs_verdict,
    mortgage_verdict, pulse, pulse_from, range_position, rate_move, recession_position,
    recession_verdict, tone,
)


class IndicatorRules(unittest.TestCase):
    def test_curve_verdict(self):
        self.assertEqual(curve_verdict(4.42, 4.24), "normal")
        self.assertEqual(curve_verdict(4.2, 4.25), "flat")
        self.assertEqual(curve_verdict(4.0, 4.3), "inverted")

    def test_borrowing_verdict(self):
        self.assertEqual(borrowing_verdict(0.2), "rising")
        self.assertEqual(borrowing_verdict(-0.2), "falling")
        self.assertEqual(borrowing_verdict(0.0), "steady")
        self.assertEqual(borrowing_verdict(0.15), "steady")

    def test_borrowing_position(self):
        self.assertEqual(borrowing_position(-0.5), 0.0)
        self.assertEqual(borrowing_position(0.0), 0.5)
        self.assertEqual(borrowing_position(0.5), 1.0)
        self.assertEqual(borrowing_position(2), 1.0)
        self.assertEqual(borrowing_position(-2), 0.0)
        self.assertEqual(borrowing_position(0.2), 0.7)

    def test_recession_verdict(self):
        self.assertEqual(recession_verdict(0.0), "none")
        self.assertEqual(recession_verdict(-0.3), "watch")
        self.assertEqual(recession_verdict(-0.5), "watch")
        self.assertEqual(recession_verdict(-0.6), "warning")

    def test_recession_position(self):
        self.assertEqual(recession_position(1.0), 0.0)
        self.assertEqual(recession_position(-1.5), 1.0)
        self.assertEqual(recession_position(-0.25), 0.5)
        self.assertEqual(recession_position(5), 0.0)
        self.assertEqual(recession_position(-5), 1.0)

    def test_rate_move(self):
        self.assertEqual(rate_move(4.10, 4.50), "cut")
        self.assertEqual(rate_move(4.60, 4.50), "hold")
        self.assertEqual(rate_move(4.80, 4.50), "hike")
        self.assertEqual(rate_move(4.75, 4.50), "hold")

    def test_range_position(self):
        self.assertEqual(range_position(84.1, 68, 88), 0.805)
        self.assertEqual(range_position(5, 5, 5), 0.5)
        self.assertEqual(range_position(99, 68, 88), 1.0)
        self.assertEqual(range_position(10, 68, 88), 0.0)

    def test_direction_verdict(self):
        self.assertEqual(direction_verdict(0.5, 0.1), "rising")
        self.assertEqual(direction_verdict(-0.5, 0.1), "falling")
        self.assertEqual(direction_verdict(0.05, 0.1), "steady")

    def test_mortgage_verdict(self):
        self.assertEqual(mortgage_verdict(0.05), "edging_up")
        self.assertEqual(mortgage_verdict(-0.05), "easing")
        self.assertEqual(mortgage_verdict(0.01), "steady")

    def test_tone(self):
        self.assertEqual(tone("brent", 0.85), "hot")
        self.assertEqual(tone("mortgages", 0.8), "hot")
        self.assertEqual(tone("gas", 0.9), "hot")
        self.assertEqual(tone("eurusd", 0.85), "normal")
        self.assertEqual(tone("eurusd", 0.1), "cool")
        self.assertEqual(tone("brent", 0.5), "normal")

    def test_jobs_verdict(self):
        self.assertEqual(jobs_verdict(230, 200), "weakening")
        self.assertEqual(jobs_verdict(170, 200), "strong")
        self.assertEqual(jobs_verdict(210, 200), "steady")

    def test_pulse(self):
        self.assertEqual(pulse("rising", "none", "steady", ["hot", "normal"]), ("overheating", 0.833))
        self.assertEqual(pulse("falling", "watch", "weakening", ["normal", "cool"])[0], "cooling")
        self.assertEqual(pulse("steady", "none", "steady", ["normal"]), ("steady", 0.5))
        self.assertEqual(pulse("rising", "none", "strong", ["hot", "hot", "hot", "hot"])[1], 1.0)

    def test_pulse_needs_two_inputs_agreeing(self):
        # One cool price alone reaches the cooling score but has no second input with it.
        self.assertEqual(pulse("steady", "none", "steady", ["normal", "cool"]), ("steady", 0.333))
        self.assertEqual(pulse("steady", "warning", "steady", ["normal", "normal"]), ("steady", 0.333))
        # Two cool prices, or a cool price and a recession warning, do agree.
        self.assertEqual(pulse("steady", "none", "steady", ["cool", "cool"])[0], "cooling")
        self.assertEqual(pulse("steady", "watch", "steady", ["cool", "normal"])[0], "cooling")
        # Overheating needs two as well: one hot price and rising borrowing.
        self.assertEqual(pulse("rising", "none", "steady", ["hot"])[0], "overheating")
        self.assertEqual(pulse("steady", "none", "strong", ["normal", "normal"])[0], "steady")

    def test_pulse_missing_rows_count_as_nothing(self):
        self.assertEqual(pulse(None, None, "weakening", ["cool"])[0], "cooling")
        self.assertEqual(pulse(None, "none", None, []), ("steady", 0.5))

    def test_pulse_from(self):
        self.assertEqual(pulse_from([{"date": "2026-11-01", "verdict": "overheating"},
                                     {"date": "2026-11-14", "verdict": "cooling"}], "cooling", "2026-11-15"), "overheating")
        self.assertIsNone(pulse_from([{"date": "2026-09-01", "verdict": "overheating"},
                                      {"date": "2026-09-20", "verdict": "cooling"}], "cooling", "2026-11-15"))
        self.assertIsNone(pulse_from([], "steady", "2026-11-15"))
        self.assertIsNone(pulse_from([{"date": "2026-11-10", "verdict": "steady"}], "steady", "2026-11-15"))
        # change happening today
        self.assertEqual(pulse_from([{"date": "2026-11-14", "verdict": "steady"}], "cooling", "2026-11-15"), "steady")


if __name__ == "__main__":
    unittest.main()
