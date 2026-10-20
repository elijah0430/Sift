import unittest

from toy_research import evaluate, mae


class EvaluationTests(unittest.TestCase):
    def test_known_mean_absolute_error(self):
        self.assertEqual(mae([1, 2], [2, 4]), 1.5)

    def test_custom_model_and_metric(self):
        result = evaluate([3, 5], [6, 10], lambda value: value * 2)
        self.assertEqual(result, {"score": 0.0, "examples": 2})

    def test_empty_and_mismatched_data_are_rejected(self):
        for predictions, targets in [([], []), ([1], [1, 2])]:
            with self.assertRaises(ValueError):
                mae(predictions, targets)


if __name__ == "__main__":
    unittest.main()
