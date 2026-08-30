import unittest

from shipping import checkout_total, shipping_fee


class ShippingTests(unittest.TestCase):
    def test_below_threshold_charges_shipping(self):
        self.assertEqual(shipping_fee(99.0), 8.0)
        self.assertEqual(checkout_total(99.0), 107.0)

    def test_exact_threshold_is_free(self):
        self.assertEqual(shipping_fee(100.0), 0.0)
        self.assertEqual(checkout_total(100.0), 100.0)

    def test_above_threshold_is_free(self):
        self.assertEqual(shipping_fee(150.0), 0.0)
        self.assertEqual(checkout_total(150.0), 150.0)


if __name__ == "__main__":
    unittest.main()
