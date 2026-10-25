import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from update_predictions import calculate_probabilities


class TestPoissonProbabilities(unittest.TestCase):
    def test_outcome_probabilities_sum_to_one_hundred(self):
        for home_rate, away_rate in ((0.15, 0.15), (1.4, 1.45), (2.8, 1.2), (4.0, 4.0)):
            with self.subTest(home_rate=home_rate, away_rate=away_rate):
                result = calculate_probabilities(home_rate, away_rate)
                total = result["homeWin"] + result["draw"] + result["awayWin"]
                self.assertAlmostEqual(total, 100.0, delta=0.2)

    def test_all_markets_stay_in_probability_range(self):
        for home_rate, away_rate in ((0.15, 0.15), (1.8, 0.7), (4.0, 4.0)):
            with self.subTest(home_rate=home_rate, away_rate=away_rate):
                result = calculate_probabilities(home_rate, away_rate)
                for market, value in result.items():
                    self.assertGreaterEqual(value, 0.0, market)
                    self.assertLessEqual(value, 100.0, market)

    def test_goal_markets_respect_logical_relationships(self):
        for home_rate, away_rate in ((0.5, 0.4), (1.5, 1.2), (3.2, 2.8)):
            with self.subTest(home_rate=home_rate, away_rate=away_rate):
                result = calculate_probabilities(home_rate, away_rate)
                self.assertLessEqual(result["over25"], result["over15"] + 0.2)
                self.assertLessEqual(result["btts"], result["over15"] + 0.2)


if __name__ == "__main__":
    unittest.main()
