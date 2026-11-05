import unittest
from decimal import Decimal

from reading.scoring import band_for, check_answer, normalize


class NormalizeTests(unittest.TestCase):
    def test_case_space_punctuation(self):
        self.assertEqual(normalize("  The  Birds. "), "the birds")

    def test_thousands_separator(self):
        self.assertEqual(normalize("1,000"), "1000")

    def test_keeps_hyphen_and_apostrophe(self):
        self.assertEqual(normalize("well-known"), "well-known")
        self.assertEqual(normalize("it\u2019s"), "it's")


class CheckAnswerTests(unittest.TestCase):
    def test_exact_and_case(self):
        self.assertTrue(check_answer("TRUE", "TRUE"))
        self.assertTrue(check_answer("true", "TRUE"))

    def test_alternatives(self):
        self.assertTrue(check_answer("wind mills", "windmills|wind mills"))
        self.assertTrue(check_answer("Windmills!", "windmills|wind mills"))

    def test_blank_and_wrong(self):
        self.assertFalse(check_answer("", "birds"))
        self.assertFalse(check_answer("   ", "birds"))
        self.assertFalse(check_answer("bird", "birds"))

    def test_number_formats(self):
        self.assertTrue(check_answer("1000", "1,000"))


class BandTests(unittest.TestCase):
    def test_academic_table(self):
        self.assertEqual(band_for(40, 40), Decimal("9.0"))
        self.assertEqual(band_for(30, 40), Decimal("7.0"))
        self.assertEqual(band_for(23, 40), Decimal("6.0"))
        self.assertEqual(band_for(0, 40), Decimal("0.0"))

    def test_general_table_differs(self):
        self.assertEqual(band_for(30, 40, "general"), Decimal("6.0"))

    def test_scaling(self):
        self.assertEqual(band_for(4, 8), band_for(20, 40))

    def test_no_questions(self):
        self.assertIsNone(band_for(0, 0))


if __name__ == "__main__":
    unittest.main()
