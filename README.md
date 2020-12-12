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
Date/Time,Transaction Code,Transaction Subcode,Symbol,Buy/Sell,Open/Close,Quantity,\
Expiration Date,Strike,Call/Put,Price,Fees,Amount,Description,Account Reference
</code>

If you delete the __eurusd.csv__ file, a current version is downloaded directly
from <https://www.bundesbank.de/de/statistiken/wechselkurse>.
(Link to the data: [eurusd.csv](https://www.bundesbank.de/statistic-rmi/StatisticDownload?tsId=BBEX3.D.USD.EUR.BB.AC.000&its_csvFormat=en&its_fileFormat=csv&mode=its&its_from=2010))

The option __--usd__ can be used to not translate pnl data into Euro.

Per default balance adjustments are only output as total sum, you can use the option __--long__
to include balance adjustments into the list of transactions.

Per default the script stops on unknown trading symbols (underlyings) and you have
to hardcode into the source code if it is an individual stock or some ETF/fond.
You can use the __--assume-individual-stock__ option to assume individual stock for all unknown symbols.


If you work on Linux with Ubuntu/Debian, you need to make sure
<https://pandas.pydata.org/> is installed:

<code>
sudo apt-get install python3-pandas
</code>


TODO
----

Important:

- If a long option is assigned, the option buy price should be added to
  the stock price. This is currently not done, but we print a warning
  message for this case for manual adjustments in this rather rare case.
- Output new CSV file with all transactions plus year-end pnl data and also
  pnl in $ and pnl in Euro.
- Optionally break up report into: dividends, withholding-tax, interest, fees, stocks, other.
- Filter out tax gains due to currency changes for an extra report. If the pnl
  lists currency gains separate, can they be used up to 600 € for tax-free income?
- Does not work with futures.
- Add images on how to download csv-file within Tastyworks into docu.
- Complete the list of non-stocks.
- For an individual stock whitelist we could list all SP500 and Nasdaq100 stocks.
- Add net total including open positions.
- Specify non-realised gains to know how much tax needs to be paid for current net total.
- Add performance reviews, graphs based on different time periods.
- Add description of the asset: SPY: SPDR S&P 500 ETF Trust
- Check if dates are truely ascending.
- Are we rounding output correctly?

Nice:

- Translate text output into German.
- Add docu in German.
- Add test data for users to try out.
- Add testsuite to verify proper operation.
- Improve output of open positions.
- Use pandas.isna(x)?

