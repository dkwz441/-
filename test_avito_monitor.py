import unittest

from avito_monitor import (
    COMPONENT_NAMES,
    PRODUCTS,
    Listing,
    browser_profile_dir,
    build_search_url,
    detect_smart_query,
    listing_is_relevant,
    page_url,
    price_from_text,
)


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

    def test_every_component_has_catalog_entry(self):
        for component in COMPONENT_NAMES:
            self.assertIn(component, PRODUCTS)

    def test_main_component_manufacturers_are_present(self):
        self.assertIn("Kingston", PRODUCTS["Оперативная память"][1])
        self.assertIn("NVIDIA", PRODUCTS["Видеокарта"][1])
        self.assertIn("Seasonic", PRODUCTS["Блок питания"][1])

    def test_monitor_profiles_are_separate(self):
        self.assertNotEqual(browser_profile_dir("Brave", 1), browser_profile_dir("Brave", 2))

    def test_smart_ram_query(self):
        product, manufacturer, extra = detect_smart_query("оперативка Kingston 2x16 32gb")
        self.assertEqual(product, "Оперативная память")
        self.assertEqual(manufacturer, "Kingston")
        self.assertEqual(extra, "2x16 32gb")

    def test_relevance_rejects_motherboard_for_ram_search(self):
        ram = Listing("1", "Kingston Fury DDR5 32 ГБ комплект 2 x 16 ГБ", 9000, "https://example.test/1")
        board = Listing("2", "Материнская плата ASUS B650", 12000, "https://example.test/2")
        self.assertTrue(listing_is_relevant(ram, "Оперативная память", "Kingston", "2x16 32gb"))
        self.assertFalse(listing_is_relevant(board, "Оперативная память", "Kingston", "2x16 32gb"))

    def test_page_url(self):
        url = page_url("https://www.avito.ru/moskva?q=ram", 3)
        self.assertIn("p=3", url)


if __name__ == "__main__":
    unittest.main()
