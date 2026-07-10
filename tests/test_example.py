import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.example import average, calculate_factorial, find_user


class ExampleFunctionsTest(unittest.TestCase):
    def test_calculate_factorial_handles_negative_input(self):
        with self.assertRaises(ValueError):
            calculate_factorial(-1)

    def test_calculate_factorial_returns_expected_value(self):
        self.assertEqual(calculate_factorial(5), 120)

    def test_average_raises_for_empty_input(self):
        with self.assertRaises(ValueError):
            average([])

    def test_average_returns_mean(self):
        self.assertEqual(average([1, 2, 3, 4]), 2.5)

    def test_find_user_returns_matching_user(self):
        users = [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}]
        self.assertEqual(find_user(users, 2), {"id": 2, "name": "Grace"})

    def test_find_user_raises_when_not_found(self):
        users = [{"id": 1, "name": "Ada"}]
        with self.assertRaises(LookupError):
            find_user(users, 2)


if __name__ == "__main__":
    unittest.main()
