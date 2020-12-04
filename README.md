Tastyworks PNL
--------------

This python script is used to generate data for a German tax income statement
from Tastyworks csv-file with trade history.


How to use
----------

Download your trade history as csv file from
<https://trade.tastyworks.com/index.html#/transactionHistoryPage>.
(Choose "Activity" and then "History" and then setup the filter for a
custom period of time and download it as csv file.)

Newest entries in the csv file should be on the top and it should contain the complete
history over all years. The csv file has the following first line:

<code>
Date/Time,Transaction Code,Transaction Subcode,Symbol,Buy/Sell,Open/Close,Quantity,Expiration Date,Strike,Call/Put,Price,Fees,Amount,Description,Account Reference
</code>

If you work on Linux with Ubuntu/Debian, you need o make sure
<https://pandas.pydata.org/> is installed:

<code>
sudo apt-get install python3-pandas
</code>


TODO
----

- Profit and loss is only calculated like for normal stocks,
  no special handling for options until now.
- Missing conversion from USD to EUR.
  - Download official conversion data and include it also inline here.
- Filter out tax gains due to currency changes.
- Does not work with futures.
- Translate text output into German.
- Complete the list of non-stocks.
- Add test data for users to try out.
- Output yearly information, currently only the end result is printed once.
- Break up report into: dividends, withholding-tax, interest, fees, stocks, other.
- Check if dates are truely ascending.
- Improve output of open positions.
- Use pandas.isna(x)?

