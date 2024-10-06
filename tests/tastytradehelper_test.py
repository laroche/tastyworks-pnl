import os
import unittest

import pandas

from tastytradehelper import TastytradeHelper
from pandas.testing import assert_frame_equal

class TastytradeHelperTests(unittest.TestCase):
    def setUp(self):
        pass

    def _get_test_data_directory(self):
        """
        Return the directory where the test data is stored.
        """
        return os.path.join(os.path.dirname(__file__), 'data')
    
    def test_is_legacy_csv(self):
        """
        Test the detection of the CSV file format.
        """
        testdata_directory = self._get_test_data_directory()
        self.assertTrue(TastytradeHelper.is_legacy_csv(testdata_directory + os.sep + 'Legacy Format.csv'))
        self.assertFalse(TastytradeHelper.is_legacy_csv(testdata_directory + os.sep + 'MES LT112.csv'))
        #TODO: Add test for wrong first line in csv file (raise ValueError)

    def test_price_from_description(self):
        extracted_price = TastytradeHelper.price_from_description('Bought 1 SPY 100 16 OCT 20 340 Call @ 1.23')
        self.assertEqual(extracted_price, 1.23)
        extracted_price = TastytradeHelper.price_from_description('Sold 1 SPY 100 16 OCT 20 300 Call @ "2,323.23"')
        self.assertEqual(extracted_price, 2323.23)

    def test_consolidate_and_sort_transactions(self):
        """
        Test the consolidation and sorting of transactions from multiple csv files.
        Transactions are expected to be sorted descending by date.
        """
        testdata_directory = self._get_test_data_directory()
        transactions = []
        # Read first older data file and then the newer one
        transactions.append(TastytradeHelper.read_transaction_history(testdata_directory + os.sep + 'CL Future.csv'))
        transactions.append(TastytradeHelper.read_transaction_history(testdata_directory + os.sep + 'MES LT112.csv'))
        consolidated_data = TastytradeHelper.consolidate_and_sort_transactions(transactions)
        # Expected data from the two files sorted descending by date
        expected_data = TastytradeHelper.read_transaction_history(testdata_directory + os.sep + 'test_consolidate_and_sort_transactions_result.csv')
        pandas.testing.assert_frame_equal(consolidated_data, expected_data, check_categorical=False)

    def test_get_eurusd(self):
        """
        Test the retrieval of the EURUSD exchange rate for a given date.
        """
        TastytradeHelper._eurusd_rates = {'2020-10-15': 1.17, '2020-10-16': None,'2020-10-17': 1.16}
        self.assertEqual(TastytradeHelper.get_eurusd('2020-10-15'), 1.17)
        self.assertEqual(TastytradeHelper.get_eurusd('2020-10-16'), 1.17)
        self.assertEqual(TastytradeHelper.get_eurusd('2020-10-17'), 1.16)

        # Expect Exception if there is no exchange rate available for the given date
        with self.assertRaises(ValueError):
            TastytradeHelper.get_eurusd('2020-10-14')
        
