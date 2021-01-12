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

If you delete the __eurusd.csv__ file, a current version is downloaded directly
from <https://www.bundesbank.de/de/statistiken/wechselkurse>.
(Link to the data: [eurusd.csv](https://www.bundesbank.de/statistic-rmi/StatisticDownload?tsId=BBEX3.D.USD.EUR.BB.AC.000&its_csvFormat=en&its_fileFormat=csv&mode=its&its_from=2010))

The option __--usd__ can be used to not translate pnl data into Euro.

The option __--verbose__ adds currency gains for each transaction.

Per default balance adjustments are only output as total sum, you can use the option __--long__
to include balance adjustments into the list of transactions.

Per default the script stops on unknown trading symbols (underlyings) and you have
to hardcode into the source code if it is an individual stock or some ETF/fond.
You can use the __--assume-individual-stock__ option to assume individual stock for all unknown symbols.

Currency gains are only summed up within the first year and if no credit is paid back, otherwise
they are tax free. Also if dividents or credit is received or account fees are paid.
(They need to go into 'Anlage SO' within a German tax statement.)

The option __--debug-fifo__ gives details on the FIFO workings. Be aware that pnl data
is the cummulative sum, not the real local change. (Bug in the output!)

The option __--show__ gives some summary graphs.


If you work on Linux with Ubuntu/Debian, you need to make sure
<https://pandas.pydata.org/> is installed:

<code>
sudo apt-get install python3-pandas
</code>


CSV and Excel Output
--------------------

The script can also output all data again as CSV file or as Excel file.
(CSV should be most robust, I don't have much experience with excel. I'd recommend CSV
and just reading it into a new Excel sheet yourself. Both data types contain the same output data.)

The options for this are __--output-csv=file.csv__ and __--output-excel=file.xlsx__.

The output contains the important original data from the Tastyworks csv file plus
pnl generated data as well as eurusd conversion data. You probably do not have to
provide all data in a tax statement, some is only added for further data processing
convenience in your spreadsheet program.
Here the output transaction data in detail:

- __datetime__: Date and time (Tastyworks gives minutes for this, no exact seconds)
  of the transaction
- __pnl__: pnl for tax payments for this transaction based on FIFO
- __usd_gains__: currency conversion gains for the account in USD. Based on cash changes
  in USD due to this transaction.
- __usd_gains_notax__: as above, but not part of German tax law
- __eur_amount__: 'amount - fees' converted into Euro currency
- __amount__: transaction amount in USD
- __fees__: cost of transaction in USD that needs to be subtracted from amount
- __eurusd__: official eurusd conversion rate for this transaction date from bundesbank.de
- __quantity__: number of buys or sells
- __asset__: what is bought (stock symbol or something like 'SPY P310 20-12-18' for an option
- __symbol__: base asset (underlying) that is traded. This is included to be able to
  generate summary overviews for e.g. all transactions in SPY with stocks and options combined.
- __description__: additional informational text for the transaction
- __account_total__: account total in USD at this time. This is the previous account total plus
  'amount - fees' from this transaction. (Cash amount at Tastyworks.)
  This is purely informational and not needed for tax data.
- __net_total__: Sum in USD of account_total (cash) plus all assets (stocks, options)
  in your account.
  This does not use current market data, but keeps asset prices at purchase cost.
  Best looked at to check if this script calculates the same total sum as shown in your
  Tastyworks current total.
- __term_loss__: how much does this transaction contribute to losses in future
  contracts ('Verlustverrechnungstopf Termingeschäfte')
- __tax_free__: are further currency changes tax free (German: steuerneutral)


FAQ
---

- There is a calculation check with math.isclose() around line 116. I think people load
  the CSV file into a spreadsheet which will round the numbers. Either load the real
  numbers from Tastyworks or relax this check from "abs_tol=0.00001" to "abs_tol=0.001".
- Maybe ACH transfers are not yet implemented. I don't use them, maybe email me
  a sample transaction line, so that I can adjust the source code.
- Either github issues or email works for me to enhance/fix this program. Sample data
  is best to resolve issues.


TODO
----

Important:

- If a long option is assigned, the option buy price should be added to
  the stock price. This is currently not done, but we print a warning
  message for this case for manual adjustments in this rather rare case.
- Print header with explanation of transaction output.
- Can Excel output also include yearly summary data computed from Excel?
  Can transactions also be grouped per year on different sheets?
- Optionally break up report into: dividends, withholding-tax, interest, fees, stocks, other.
- Does not work with futures.
- For currency gains, we could also add all fees as tax free by adding a separate booking/transaction.
- Complete support for Investmentsteuergesetz (InvStG) 2018.
- Add images on how to download csv-file within Tastyworks into docu.
- Complete the list of non-stocks.
- For an individual stock whitelist we could list all SP500 and Nasdaq100 stocks.
- Specify non-realised gains to know how much tax needs to be paid for current net total.
- Add performance reviews, graphs based on different time periods.
- Add description of the asset: SPY: SPDR S&P 500 ETF Trust
- Check if dates are truely ascending.
- Check if withholding tax is max 15% for US stocks as per DBA.
- Are we rounding output correctly?
- Is the time output correct with the correct timezone?

Nice:

- Translate text output into German.
- Add docu in German.
- Add test data for users to try out.
- Add testsuite to verify proper operation.
- Improve output of open positions.
- Use pandas.isna(x)?

