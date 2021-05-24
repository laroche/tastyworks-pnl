Tastyworks PNL
--------------

This python script is used to generate data for a private German tax income statement
from Tastyworks csv-file with trade history.


How to use
----------

Download your trade history as csv file from
<https://trade.tastyworks.com/index.html#/transactionHistoryPage>.
(Choose "Activity" and then "History" and then setup the filter for a
custom period of time and download it as csv file.)

Newest entries in the csv file should be on the top and it should contain the complete
history over all years. (You can at most download data for one year, so for several years
you have to download into several files and combine them into one file with a text editor.)
The csv file has the following first line:

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

All currency gains are classified as either tax-free or they need to go into the 'Anlage SO' within
a private German tax statement.
Currency gains are computed via FIFO as with other assets. They are tax free if hold more than one year
or if credit is paid back (negative cash balance). They are also tax free for dividends, credit payments and
sold options as well as account fees.

The summary output lists all assets at the end of each year. 'account-usd' contains a FIFO list of all
USD buys and the conversion price for Euro. This entry might be very long and look complicated. You might
want to ignore this line.

The option __--debug-fifo__ gives details on the FIFO workings. Be aware that pnl data
is the cummulative sum, not the real local change. (Bug in the output!)

The option __--show__ gives some summary graphs.


If you work on Linux with Ubuntu/Debian, you need to make sure
<https://pandas.pydata.org/> is installed:

<code>
sudo apt-get install python3-pandas
</code>

Or use pip for a local install:

<code>
pip install pandas
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
- __account_total__: account cash balance in USD after this transaction. This is the previous account total plus
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

- Maybe ACH transfers are not yet implemented. I don't use them, maybe email me
  a sample transaction line, so that I can adjust the source code.
- Either github issues or email works for me to enhance/fix this program. Sample data
  is best to resolve issues.


Currency gains in German tax law
--------------------------------

Discussion in German about Germany tax law on currency gains:


Links:

- <https://www.wertpapier-forum.de/topic/45232-steuerliche-behandlung-fremdw%C3%A4hrungskonto-ib-oder-andere-broker/>
- <https://www.wertpapier-forum.de/topic/53676-versteuerung-bei-ausl-aktien-mit-w%C3%A4hrungstausch/>
- <https://www.youtube.com/watch?v=VRjp1yVvHcg>   ab Minute 39
- <https://www.youtube.com/watch?v=Bm2r2yXCJ30>
   - <https://fintax-steuerberater.de/>
   - <https://fintegra.de/steuerliches-fremdwaehrungsreporting/>
- <http://www.iusconsulting.de/de/portal-eintrag/private-veraumluszligerungsgeschaumlfte>


Zusammenfassung Steuern im Privatvermögen bei Fremdwährungskonten:

- Private Veräußerungsgeschäfte werden in [§ 23 EStG](https://www.gesetze-im-internet.de/estg/__23.html) behandelt. (EStG = Einkommensteuergesetz)
- Bei der Anschaffung und Veräußerung von Fremdwährungsbeträgen kann es sich um ein
  privates Veräußerungsgeschäft i.S. des [§ 23 Abs. 1 Nr. 2 EStG](https://www.gesetze-im-internet.de/estg/__23.html) handeln.
  Diese werden in der privaten Einkommensteuererklärung in der
  [Anlage SO](https://www.formulare-bfinv.de/ffw/catalog/openForm.do?path=catalog%3A%2F%2FBuerger%2Fsteuern%2Fest%2Fest20%2F034029_20)
  in Zeile 49 angegeben.
- Da die Gewinne aus § 23 EStG nicht dem Steuerabzug unterliegen, ermitteln die inländischen
  Banken diese Gewinne in der Regel nicht. Die Einkünfte müssen daher eigenständig ermittelt
  werden und - sofern die Freigrenze des § 23 Abs. 3 Satz 5 EStG von 600 € überschritten ist - in der
  Einkommensteuererklärung (Anlage SO) erklärt werden. BMF, Schreiben v. 18.1.2016 - IV C 1 - S
  2252/08/1004:017, BStBl 2016 I S. 85 NWB WAAF-66193, Rz 131.
- Unterliegen nicht der Abgeltungssteuer sondern dem persönlichen Steuersatz.
- Fremdwährungen fallen nicht unter die Abgeltungssteuer/KapESt und werden daher von den Banken auch nicht
  in Ihrem Steuer-Reporting erfasst. Der Steuerpflichtige muss dies eigenverantwortlich übernehmen.
- Währungen gelten als Spekulationsgeschäfte, steuerbar beim Verkauf (betrachte das fremde Geld einfach als Wertpapiere)
   - Ein Konto in einer nicht-Euro-Währung gilt als eigenes Asset und muss besteuert werden.
- Für die Veräußerungsgewinnberechnung gilt die FiFo-Methode.
- die Spekulationsfrist beträgt ein Jahr (bei verzinster Anlage 10 Jahre), danach ist es immer steuerfrei
   - die 10 Jahre werden imho im Normalfall nicht angewandt, diese Regel ist nur für gezielte Steuervermeidungsstrategien (etwa spezielle Fonds)
   - Zur 10-Jahresverlängerung: Meines Wissens (Hinweis meiner Bank) gibt es vom BayLfSt die Verfügung vom 10.3.2016 die darlegt,
     dass die Erhöhung der Spekulationsfrist auf 10 Jahre (bei Festgeldverzinsung) nicht greift.
     <https://www.haufe.de/steuern/finanzverwaltung/veraeusserungsgewinne-bei-fremdwaehrungsgeschaeften-im-fokus_164_373742.html>
   - <https://www.wertpapier-forum.de/topic/53676-versteuerung-bei-ausl-aktien-mit-w%C3%A4hrungstausch/?do=findComment&comment=1354931>:
     Ein Nebeneffekt ist, dass verzinsliche Währungsguthaben dennoch nur der Ein-Jahresfrist in § 23 EStG unterliegen (und nicht verlängert),
     weil die Zinsen ja nicht für das Wirtschaftsgut "Währungsguthaben", sondern für die darunter liegende Forderung an sich bezahlt werden.
     Zinsen fallen unter § 20 EStG.
   - Bei der Berechnung der Spekulationsfrist wird der Tag der Anschaffung nicht mitgerechnet.
- Freigrenze 600 Euro (für alle Spekulationsgewinne zusammen), darunter immer steuerfrei
- Verluste werden in einem extra Verlustverrechnungstopf vom Finanzamt vorgetragen und können (auf Antrag) nur mit Gewinnen aus dem Vorjahr
  verrechnet werden.
- Dividendenauszahlungen/Optionsprämien/Zinsen in Fremdwährung sind keine "Anschaffung" von Währungsguthaben
  im Sinne von § 23 EStG (da gilt eine enge Auslegung des Anschaffungsbegriffs), sondern ein Zufluss (Der Zufluss an sich fällt ja unter § 20 EStG als Kapitalertrag).
  Die spätere Veräußerung von Währungsguthaben aus Dividendenzuflüssen ist somit nie nach § 23 EStG steuerbar, weil es kein Anschaffungsgeschäft dazu gibt.
  Anschaffung = Erwerb von etwas Bestehendem von einem Dritten gegen Hingabe des Kaufpreises.
- Abflüsse, die keine Veräußerung darstellen. Ich zähle dazu u.a. Kontogebühren, fremde Steuern, Zinsen etc. im Zusammenhang mit der Kapitalüberlassung


TODO
----

Important:

- If a long option is assigned, the option buy price should be added to
  the stock price. This is currently not done, but we print a warning
  message for this case for manual adjustments in this rather rare case.
- If option writing is cash-settled this must go into "Termingeschäftsverluste".
- Currently we only make one pass over the data. Better allow several data passes/computations.
- Print header with explanation of transaction output.
- Can Excel output also include yearly summary data computed from Excel?
  Can transactions also be grouped per year on different sheets?
- Optionally break up report into: dividends, withholding-tax, interest, fees, stocks, other.
- Does not work with futures.
- Stock splits and spinoffs are not supported. (Option strike prices also need to be adjusted.) Example entry:
<pre>
01/21/2021 12:39 PM,Receive Deliver,Forward Split,TQQQ,Buy,Open,108,,,,,0.00,-9940.86,Forward split: Open 108.0 TQQQ,xxx...00
01/21/2021 12:39 PM,Receive Deliver,Forward Split,TQQQ,Sell,Close,54,,,,,0.00,9940.86,Forward split: Close 54.0 TQQQ,xxx...00
</pre>
- Assumption: stock/option splits are tax neutral.
- For currency gains, we could also add all fees as tax free by adding a separate booking/transaction.
- For currency gains tax calculation you can reorder all transactions of one day and use the best
  order to minimize tax payments. This is currently not done with the current source code.
- In German: Stillhalterpraemien gelten auch nicht als Währungsanschaffung, sondern
  als Zufluss und sind daher steuer-neutral. Im Source wird dazu die Auszeichnung von Tastyworks
  als "Sell-To-Open" verwendet. Was passiert aber, wenn man eine Option gekauft hat und dann 2 davon
  verkauft? Bleibt das bei Tastyworks eine Transaktion oder finden hier dann zwei Transaktionen statt?
  Dieser Fall tritt bei mir nicht auf. Der Source Code sollte zumindest diesen Fall detektieren und
  eine Warnung ausgeben.
- Complete support for Investmentsteuergesetz (InvStG) 2018.
- Add images on how to download csv-file within Tastyworks into docu.
- Complete the list of non-stocks.
- Done: For an individual stock whitelist we could list all SP500 and Nasdaq100 stocks.
  How do we cope with historical data for this?
- Specify non-realised gains to know how much tax needs to be paid for current net total.
- Add performance reviews, graphs based on different time periods and underlyings.
- Add description of the asset: SPY: SPDR S&P 500 ETF Trust
- Done: Check if dates are truely ascending in the provided csv input files.
- Check if input has duplicate transactions. Could they happen? (As warning only.)
- Check if withholding tax is max 15% for US stocks as per DBA.
  Warn if e.g. 30% withholding tax is paid and point to missing W8-BEN formular.
- Are we rounding output correctly?
- Is the time output using the correct timezone?
- Does Tastyworks use BRK.B or BRK/B in transaction history?
  Adjust the list of individual stocks accordingly.
- Look at other libraries for currency conversion:
  <https://github.com/alexprengere/currencyconverter> or
  <https://github.com/flaxandteal/moneypandas>
- Generate documentation that can be passed on to the German tax authorities on how
  the tax is computed and also document on how to fill out the official tax documents.
   - Check this for docx reporting: <https://github.com/airens/interactive_brokers_tax>

Nice:

- Translate text output into German.
- Add docu in German.
- Add test data for users to try out.
- Add testsuite to verify proper operation.
- Improve output of open positions.
- Use pandas.isna(x)?

