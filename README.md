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

If you delete the local "eurusd.csv" file, a current one is downloaded over the
Internet.

The option '--usd' can be used to not translate pnl data into Euro.
Per default balance adjustments are only output as total sum, you can use the option '--long'
to include balance adjustments into the list of transactions.

Per default the script stops on unknown trading symbols (underlyings) and you have
to hardcode into the source code if it is an individual stock or some ETF/fond.
You can use the '--assume-individual-stock' option to assume individual stock for all unknown symbols.

If you work on Linux with Ubuntu/Debian, you need to make sure
<https://pandas.pydata.org/> is installed:

<code>
sudo apt-get install python3-pandas
</code>


TODO
----

- Profit and loss is only calculated like for normal stocks,
  no special handling for options until now. (Works ok if you
  have closed all positions by end of year.)
- Filter out tax gains due to currency changes for an extra report.
- Does not work with futures.
- Translate text output into German.
- Complete the list of non-stocks.
- Add test data for users to try out.
- Output new CSV file with all transactions plus year-end pnl data and also
  pnl in $ and pnl in Euro.
- Break up report into: dividends, withholding-tax, interest, fees, stocks, other.
- Check if dates are truely ascending.
- Improve output of open positions.
- Are we rounding output correctly?
- Use pandas.isna(x)?

