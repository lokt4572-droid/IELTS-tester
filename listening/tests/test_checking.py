import unittest

from listening.checking import (
    accepted_answers,
    check_answer,
    check_mcq_multi,
    normalize_answer,
)


class ListeningCheckingTests(unittest.TestCase):
    def test_normalization_case_space_punctuation_and_dash_variants(self):
        self.assertEqual(normalize_answer("  (Twenty\u2013  five)!  "), "twenty- five")
        self.assertEqual(normalize_answer("  NORTH\u2014EAST  "), "north-east")
        self.assertEqual(normalize_answer("  \"Blue sky.\" "), "blue sky")
        self.assertEqual(normalize_answer(""), "")

    def test_accepted_alternatives_are_normalized_separately(self):
        self.assertEqual(
            accepted_answers(" colour |  COLOR  "),
            ["colour", "color"],
        )
        self.assertTrue(check_answer("COLOR", "colour|color"))
        self.assertTrue(check_answer("  twenty\u2011five ", "25|twenty-five"))

    def test_empty_answer_is_always_wrong(self):
        self.assertFalse(check_answer("", "answer"))
        self.assertFalse(check_answer("   ", "answer"))
        self.assertFalse(check_answer("answer", ""))

    def test_letter_answers_are_compared_case_insensitively(self):
        for qtype in ("mcq", "matching", "diagram_label"):
            with self.subTest(qtype=qtype):
                self.assertTrue(check_answer(" b ", "B", qtype))
                self.assertFalse(check_answer("BB", "B", qtype))

    def test_non_letter_answer_uses_normalized_text(self):
        self.assertTrue(check_answer("  Main   Street ", "main street"))
        self.assertFalse(check_answer("Main Street", "Main Avenue"))

    def test_multi_select_is_order_independent_and_awards_each_correct_letter(self):
        self.assertEqual(check_mcq_multi(["D", "B"], ["B", "D"]), 2)
        self.assertEqual(check_mcq_multi("D, B", ["B", "D"]), 2)

    def test_multi_select_duplicates_and_wrong_extras_do_not_score(self):
        self.assertEqual(check_mcq_multi(["B", "B", "X"], ["B", "D"]), 1)
        self.assertEqual(check_mcq_multi(["X", "Y"], ["B", "D"]), 0)
        self.assertEqual(check_mcq_multi([], ["B", "D"]), 0)
