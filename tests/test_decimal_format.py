from __future__ import annotations

from decimal import Decimal
import unittest

from apps.api.app.utils.decimal_format import format_decimal


class DecimalFormatTests(unittest.TestCase):
    def test_format_decimal_zero(self) -> None:
        self.assertEqual(format_decimal(Decimal("0.0000")), "0")

    def test_format_decimal_strips_trailing_zeros(self) -> None:
        self.assertEqual(format_decimal(Decimal("5.2500")), "5.25")


if __name__ == "__main__":
    unittest.main()
