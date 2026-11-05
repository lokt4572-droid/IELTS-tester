import unittest

from writing.scoring import count_words, round_band, task_band, writing_band


class CountingTests(unittest.TestCase):
    def test_count_words_uses_whitespace_tokens(self):
        self.assertEqual(count_words(""), 0)
        self.assertEqual(count_words("one two three"), 3)
        self.assertEqual(count_words("  one   two\nthree  "), 3)


class BandTests(unittest.TestCase):
    def test_round_band_nearest_half(self):
        self.assertEqual(round_band(6.125), 6.0)
        self.assertEqual(round_band(6.75), 7.0)
        self.assertEqual(round_band(6.25), 6.5)

    def test_task_band_average(self):
        self.assertEqual(task_band(6, 6.5, 6, 6), 6.0)
        self.assertEqual(task_band(6.5, 7, 6.5, 7), 7.0)

    def test_writing_band_formula(self):
        self.assertEqual(writing_band(6.0, 7.0), 6.5)
        self.assertEqual(writing_band(6.5, 7.0), 7.0)


if __name__ == "__main__":
    unittest.main()
