"""单元测试：JSON 兼容格式化（纯函数，零外部依赖）。"""
import json
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal

from SmartVoyage.utils.format import DateEncoder, default_encoder, dumps


class TestFormatEncoder(unittest.TestCase):
    def test_encode_datetime(self):
        self.assertEqual(default_encoder(datetime(2025, 7, 30, 14, 30, 0)), '2025-07-30 14:30:00')

    def test_encode_date(self):
        self.assertEqual(default_encoder(date(2025, 7, 30)), '2025-07-30')

    def test_encode_timedelta(self):
        self.assertEqual(default_encoder(timedelta(hours=5, minutes=30)), '5:30:00')

    def test_encode_decimal(self):
        result = default_encoder(Decimal('123.45'))
        self.assertIsInstance(result, float)
        self.assertAlmostEqual(result, 123.45)

    def test_encode_unknown(self):
        self.assertEqual(default_encoder("hello"), "hello")

    def test_date_encoder_json_dumps(self):
        parsed = json.loads(json.dumps({
            "date": date(2025, 7, 30),
            "datetime": datetime(2025, 7, 30, 14, 30, 0),
            "value": Decimal('99.99'),
        }, cls=DateEncoder))
        self.assertEqual(parsed["date"], "2025-07-30")
        self.assertEqual(parsed["datetime"], "2025-07-30 14:30:00")
        self.assertEqual(parsed["value"], 99.99)

    def test_dumps_helper(self):
        parsed = json.loads(dumps({"p": Decimal('409.88'), "d": date(2026, 5, 1)}))
        self.assertEqual(parsed, {"p": 409.88, "d": "2026-05-01"})


if __name__ == "__main__":
    unittest.main()
