import unittest
from decimal import Decimal

from listening.scoring import listening_band


class ListeningBandTests(unittest.TestCase):
    def test_all_score_ranges(self):
        cases = {
            40: "9.0",
            39: "9.0",
            38: "8.5",
            37: "8.5",
            36: "8.0",
            35: "8.0",
            34: "7.5",
            32: "7.5",
            31: "7.0",
            30: "7.0",
            29: "6.5",
            26: "6.5",
            25: "6.0",
            23: "6.0",
            22: "5.5",
            18: "5.5",
            17: "5.0",
            16: "5.0",
            15: "4.5",
            13: "4.5",
            12: "4.0",
            10: "4.0",
            9: "3.5",
            8: "3.5",
            7: "3.0",
            6: "3.0",
            5: "2.5",
            4: "2.5",
            3: "2.0",
            2: "1.5",
            1: "1.0",
            0: "0.0",
        }
        for score, expected in cases.items():
            with self.subTest(score=score):
                self.assertEqual(listening_band(score, 40), Decimal(expected))

    def test_band_requires_exactly_40_questions(self):
        self.assertIsNone(listening_band(39, 39))
        self.assertIsNone(listening_band(39, 41))

    def test_invalid_score_returns_none(self):
        self.assertIsNone(listening_band(-1, 40))
        self.assertIsNone(listening_band(41, 40))
        self.assertIsNone(listening_band(True, 40))
