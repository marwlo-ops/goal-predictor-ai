import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from model_analytics import analyze_match, score_matrix


class TestModelAnalytics(unittest.TestCase):
    def test_score_matrix_is_normalized(self):
        for home, away in ((0.1, 0.2), (1.5, 1.5), (3.7, 1.1), (4.0, 4.0)):
            with self.subTest(home=home, away=away):
                matrix = score_matrix(home, away)
                self.assertAlmostEqual(sum(map(sum, matrix)), 1.0, places=9)

    def test_symmetric_fixture_has_symmetric_win_chance(self):
        output = analyze_match(1.45, 1.45, seed=17, samples=3000)
        markets = output["markets"]
        self.assertAlmostEqual(markets["homeWin"], markets["awayWin"], delta=0.1)
        self.assertGreater(markets["draw"], 0)

    def test_all_markets_are_in_range_and_monotonic(self):
        markets = analyze_match(1.7, 1.2, seed=22, samples=3000)["markets"]
        for name, value in markets.items():
            self.assertGreaterEqual(value, 0, name)
            self.assertLessEqual(value, 100, name)
        self.assertLessEqual(markets["over25"], markets["over15"])
        self.assertLessEqual(markets["over35"], markets["over25"])
        self.assertLessEqual(markets["btts"], markets["over15"])

    def test_simulation_is_reproducible_and_close_to_grid(self):
        one = analyze_match(1.8, 1.1, seed=2026, samples=12000)
        two = analyze_match(1.8, 1.1, seed=2026, samples=12000)
        self.assertEqual(one["monteCarlo"], two["monteCarlo"])
        for market in ("homeWin", "draw", "awayWin", "over25", "btts"):
            self.assertLess(abs(one["markets"][market] - one["monteCarlo"]["markets"][market]), 2.5)

    def test_invalid_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            analyze_match(-1, 1.2)
        with self.assertRaises(ValueError):
            analyze_match(1, 1, samples=10)


if __name__ == "__main__":
    unittest.main()
