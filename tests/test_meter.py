from __future__ import annotations

import unittest

from apps.api.app.services.usage.meter import (
    compute_credits_burned,
    compute_oe_tokens,
    get_model_multiplier,
)


class MeterTests(unittest.TestCase):
    def test_compute_oe_tokens_basic(self) -> None:
        self.assertEqual(compute_oe_tokens(100, 50, 10), 50.0)

    def test_compute_oe_tokens_negatives_clamped(self) -> None:
        self.assertEqual(compute_oe_tokens(-100, -25, -2), 0.0)

    def test_compute_credits_burned_with_multiplier(self) -> None:
        self.assertEqual(compute_credits_burned(10_000, model_multiplier=0.5), 0.5)

    def test_compute_credits_burned_default_multiplier(self) -> None:
        self.assertEqual(compute_credits_burned(10_000), 1.0)

    def test_get_model_multiplier_known(self) -> None:
        self.assertEqual(get_model_multiplier("deepseek"), 0.5)

    def test_get_model_multiplier_unknown_falls_back(self) -> None:
        self.assertEqual(get_model_multiplier("unknown-model"), 1.0)


if __name__ == "__main__":
    unittest.main()
