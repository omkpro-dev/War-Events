import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spelling import spell  # noqa: E402


class SurnameSpelling(unittest.TestCase):
    def test_surname_alone_gets_accents(self):
        self.assertEqual(spell("Sanchez called an early vote."), "Sánchez called an early vote.")

    def test_possessive_surname_gets_accents(self):
        self.assertEqual(spell("Vucic's resignation to run for prime minister"),
                         "Vučić's resignation to run for prime minister")

    def test_full_name_still_fixed(self):
        self.assertEqual(spell("Pedro Sanchez and Jaroslaw Kaczynski"), "Pedro Sánchez and Jarosław Kaczyński")

    def test_already_accented_left_alone(self):
        self.assertEqual(spell("Sánchez and Vučić"), "Sánchez and Vučić")

    def test_common_word_surname_not_used_alone(self):
        # "Ratinho Junior" is a name, but "Junior" alone is an ordinary word.
        self.assertEqual(spell("a Junior partner"), "a Junior partner")

    def test_part_of_longer_word_untouched(self):
        self.assertEqual(spell("Sanchezville"), "Sanchezville")


if __name__ == "__main__":
    unittest.main()
