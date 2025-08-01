import os
import unittest

from tastytradehelper import TastytradeHelper

class TastytradeHelperTests(unittest.TestCase):
    def setUp(self):
        pass
   
    def test_is_cash_settled(self):
        # Test with basic cash settled symbols
        self.assertTrue(TastytradeHelper.is_symbol_cash_settled("SPX"))
        self.assertTrue(TastytradeHelper.is_symbol_cash_settled("VIXW"))
        # Test with cash settled option symbol
        self.assertTrue(TastytradeHelper.is_symbol_cash_settled("SPXW  240919C05710000"))
        # Test with non-cash settled symbol AAPL
        self.assertFalse(TastytradeHelper.is_symbol_cash_settled("AAPL"))