import unittest

from avito_monitor import build_search_url, price_from_text


class AvitoMonitorTests(unittest.TestCase):
    def test_build_search_url(self):
        url = build_search_url("https://www.avito.ru/moskva/telefony?foo=bar", "iphone 15", 50_000)
        self.assertIn("foo=bar", url)
        self.assertIn("q=iphone+15", url)
        self.assertIn("pmax=50000", url)
        self.assertIn("s=104", url)

    def test_rejects_non_avito_url(self):
        with self.assertRaises(ValueError):
            build_search_url("https://example.com", "ram", 1000)

    def test_price_from_text(self):
        self.assertEqual(price_from_text("12 345 ₽"), 12345)
        self.assertEqual(price_from_text("9999"), 9999)
        self.assertIsNone(price_from_text("договорная"))


if __name__ == "__main__":
    unittest.main()
