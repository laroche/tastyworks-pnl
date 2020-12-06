#!/usr/bin/python3
#
# Copyright (C) 2020 Florian La Roche <Florian.LaRoche@gmail.com>
#
# Generate data for a German tax income statement from Tastyworks trade history.
#
# Download your trade history as csv file from
# https://trade.tastyworks.com/index.html#/transactionHistoryPage
# (Choose 'Activity' and then 'History' and then setup the filter for a
# custom period of time and download it as csv file.)
# Newest entries in the csv file should be on the top and it should contain the complete
# history over all years. The csv file has the following first line:
# Date/Time,Transaction Code,Transaction Subcode,Symbol,Buy/Sell,Open/Close,Quantity,Expiration Date,Strike,Call/Put,Price,Fees,Amount,Description,Account Reference
#
# sudo apt-get install python3-pandas
#
# TODO:
# - Profit and loss is only calculated like for normal stocks,
#   no special handling for options until now. (Works ok if you
#   have closed all positions by end of year.)
# - Filter out tax gains due to currency changes for an extra report.
# - Add net total including open positions.
# - Does not work with futures.
# - Translate text output into German.
# - Complete the list of non-stocks.
# - Add test data for users to try out.
# - Output new CSV file with all transactions plus year-end pnl data and also
#   pnl in $ and pnl in Euro.
# - Break up report into: dividends, withholding-tax, interest, fees, stocks, other.
# - Check if dates are truely ascending.
# - Improve output of open positions.
# - Are we rounding output correctly?
# - Use pandas.isna(x)?
#

import sys
import os
import getopt
from collections import deque
import math
import datetime as pydatetime
import pandas

convert_currency = True

# For an unknown symbol (underlying), assume it is a individual/ normal stock.
# Otherwise you need to adjust the hardcoded list in this script.
assume_stock = False

eurusd = None

# If the file 'eurusd.csv' does not exist, download the data from
# the bundesbank directly.
def read_eurusd():
    global eurusd
    url = 'eurusd.csv'
    if not os.path.exists(url):
        url = 'https://www.bundesbank.de/statistic-rmi/StatisticDownload?tsId=BBEX3.D.USD.EUR.BB.AC.000&its_csvFormat=en&its_fileFormat=csv&mode=its&its_from=2010'
    eurusd = pandas.read_csv(url, skiprows=5, skipfooter=2,
        names=['date', 'eurusd', 'nix'], usecols=['date', 'eurusd'], na_values=['.'], engine='python')
    eurusd = dict(eurusd.values.tolist())

def get_eurusd(date, debug=False):
    while True:
        x = eurusd[date]
        if str(x) != "nan":
            return x
        if debug:
            print('EURUSD conversion not found for', date)
        date = str(pydatetime.date(*map(int, date.split('-'))) - pydatetime.timedelta(days=1))

def eur2usd(x, date):
    if convert_currency:
        return x * get_eurusd(date)
    return x

def usd2eur(x, date):
    if convert_currency:
        return x / get_eurusd(date)
    return x

def check_tcode(tcode, tsubcode, description):
    if tcode not in ['Money Movement', 'Trade', 'Receive Deliver']:
        raise
    if tcode == 'Money Movement':
        if tsubcode not in ['Transfer', 'Deposit', 'Credit Interest', 'Balance Adjustment', 'Fee', 'Withdrawal', 'Dividend']:
            raise
        if tsubcode == 'Balance Adjustment' and description != 'Regulatory fee adjustment':
            raise
    elif tcode == 'Trade':
        if tsubcode not in ['Sell to Open', 'Buy to Close', 'Buy to Open', 'Sell to Close']:
            raise
    elif tcode == 'Receive Deliver':
        if tsubcode not in ['Sell to Open', 'Buy to Close', 'Buy to Open', 'Sell to Close', 'Expiration', 'Assignment', 'Exercise']:
            raise

def check_param(buysell, openclose, callput):
    if str(buysell) not in ['nan', 'Buy', 'Sell']:
        raise
    if str(openclose) not in ['nan', 'Open', 'Close']:
        raise
    if str(callput) not in ['nan', 'C', 'P']:
        raise

def check_trade(tsubcode, check_amount, amount):
    #print('FEHLER:', check_amount, amount)
    if tsubcode not in ['Expiration', 'Assignment', 'Exercise']:
        if not math.isclose(check_amount, amount, abs_tol=0.00001):
            raise
    else:
        if str(amount) != 'nan' and amount != .0:
            raise
        if str(check_amount) != 'nan' and check_amount != .0:
            raise

# Is the symbol a individual stock or anything else
# like an ETF or fond?
def is_stock(symbol):
    # Well known ETFs:
    if symbol in ['DXJ','EEM','EFA','EFA','EWZ','FEZ','FXB','FXE','FXI',
        'GDX','GDXJ','GLD','HYG','IEF','IWM','IYR','KRE','OIH','QQQ',
        'RSX','SLV','SMH','SPY','TLT','UNG','USO','VXX','XBI','XHB','XLB',
        'XLE','XLF','XLI','XLK','XLP','XLU','XLV','XME','XOP','XRT']:
        return False
    # Well known stock names:
    if symbol in ['M','AAPL','TSLA']:
        return True
    # The conservative way is to through an exception if we are not sure.
    if not assume_stock:
        print('No idea if this is a stock:', symbol)
        print('Use the option --assume-individual-stock to assume individual stock for all unknown symbols.')
        raise
    return True # Just assume this is a normal stock if not in the above list

def sign(x):
    if x >= 0:
        return 1
    return -1

# 'fifos' is a dictionary with 'asset' names. It contains a FIFO
# 'deque()' with a list of 'price' (as float) and 'quantity' (as integer)
# of the asset.
# https://docs.python.org/3/library/collections.html?#collections.deque
def fifo_add(fifos, quantity, price, asset, debug=False):
    if debug:
        print_fifos(fifos)
        print('fifo_add', quantity, price, asset)
    # Detect if this is an option we are working with as
    # we have to pay taxes for selling an option:
    # This is a gross hack, should we check the 'expire' param?
    #is_option = (len(asset) > 10)
    pnl = .0
    #if is_option and quantity < 0:
    #    pnl = quantity * price
    # Find the right FIFO queue for our asset:
    if fifos.get(asset) is None:
        fifos[asset] = deque()
    fifo = fifos[asset]
    # If the queue is empty, just add it to the queue:
    while len(fifo) > 0:
        # If we add assets into the same trading direction,
        # just add the asset into the queue. (Buy more if we are
        # already long, or sell more if we are already short.)
        if sign(fifo[0][1]) == sign(quantity):
            break
        # Here we start removing entries from the FIFO.
        # Check if the FIFO queue has enough entries for
        # us to finish:
        if abs(fifo[0][1]) >= abs(quantity):
            pnl += quantity * (fifo[0][0] - price)
            fifo[0][1] += quantity
            if fifo[0][1] == 0:
                fifo.popleft()
                if len(fifo) == 0:
                    del fifos[asset]
            return pnl
        # Remove the oldest FIFO entry and continue
        # the loop for further entries (or add the
        # remaining entries into the FIFO).
        pnl += fifo[0][1] * (price - fifo[0][0])
        quantity += fifo[0][1]
        fifo.popleft()
    # Just add this to the FIFO queue:
    fifo.append([price, quantity])
    return pnl

# Check if the first entry in the FIFO
# is 'long' the underlying or 'short'.
def fifos_islong(fifos, asset):
    return fifos[asset][0][1] > 0

def print_fifos(fifos):
    print('open positions:')
    for fifo in fifos:
        print(fifo, fifos[fifo])

def print_yearly_summary(cur_year, curr_sym, dividends, withholding_tax,
        withdrawal, interest_recv, interest_paid, fee_adjustments, pnl_stocks,
        pnl, usd, total_fees, total, fifos):
    print()
    print('Total sums paid and received in the year %s:' % cur_year)
    print('dividends received:   ', f'{dividends:10.2f}' + curr_sym)
    print('withholding tax paid: ', f'{-withholding_tax:10.2f}' + curr_sym)
    if withdrawal != .0:
        print('dividends paid:       ', f'{-withdrawal:10.2f}' + curr_sym)
    print('interest received:    ', f'{interest_recv:10.2f}' + curr_sym)
    if interest_paid != .0:
        print('interest paid:        ', f'{-interest_paid:10.2f}' + curr_sym)
    print('fee adjustments:      ', f'{fee_adjustments:10.2f}' + curr_sym)
    print('pnl stocks:           ', f'{pnl_stocks:10.2f}' + curr_sym)
    print('pnl other:            ', f'{pnl:10.2f}' + curr_sym)
    print('USD currency gains:   ', f'{int(usd / 10000):7d}')
    print()
    print('New end sums and open positions:')
    print('total fees paid:      ', f'{total_fees:10.2f}' + curr_sym)
    print('account end total:    ', f'{total:10.2f}' + '$')
    print_fifos(fifos)
    print()

def check(wk, long):
    #print(wk)
    fifos = {}
    total_fees = .0           # sum of all fees paid
    total = .0                # account total
    dividends = .0
    withholding_tax = .0      # withholding tax = German 'Quellensteuer'
    withdrawal = .0
    interest_recv = .0
    interest_paid = .0
    fee_adjustments = .0
    pnl_stocks = .0
    pnl = .0
    usd = .0
    cur_year = None
    check_account_ref = None
    for i in range(len(wk) - 1, -1, -1):
        datetime = wk['Date/Time'][i]
        date = str(datetime)[:10]
        if cur_year != str(datetime)[:4]:
            if cur_year is not None:
                print_yearly_summary(cur_year, curr_sym, dividends, withholding_tax,
                    withdrawal, interest_recv, interest_paid, fee_adjustments, pnl_stocks,
                    pnl, usd, total_fees, total, fifos)
                dividends = .0
                withholding_tax = .0
                withdrawal = .0
                interest_recv = .0
                interest_paid = .0
                fee_adjustments = .0
                pnl_stocks = .0
                pnl = .0
                usd = .0
                total_fees = .0
            cur_year = str(datetime)[:4]
        tcode = wk['Transaction Code'][i]
        tsubcode = wk['Transaction Subcode'][i]
        description = wk['Description'][i]
        check_tcode(tcode, tsubcode, description)
        buysell = wk['Buy/Sell'][i]
        openclose = wk['Open/Close'][i]
        callput = wk['Call/Put'][i]
        check_param(buysell, openclose, callput)
        account_ref = wk['Account Reference'][i]
        if check_account_ref is None:
            check_account_ref = account_ref
        if account_ref != check_account_ref: # check if this does not change over time
            raise
        fees = float(wk['Fees'][i])
        total_fees += usd2eur(fees, date)
        amount = float(wk['Amount'][i])
        total += amount - fees
        eur_amount = usd2eur(amount, date)
        usd += fifo_add(fifos, int((amount - fees) * 10000), 1 / get_eurusd(date), 'account-usd')

        quantity = wk['Quantity'][i]
        if str(quantity) != 'nan':
            if int(quantity) != quantity:
                raise
            quantity = int(quantity)
        symbol = wk['Symbol'][i]
        expire = wk['Expiration Date'][i]
        strike = wk['Strike'][i]
        price = wk['Price'][i]
        if str(price) == 'nan':
            price = .0
        if price < .0:
            raise

        curr_sym = '€'
        if not convert_currency:
            curr_sym = '$'
        header = "%s %s%s %s$" % (datetime, f'{eur_amount:10.2f}', curr_sym, f'{amount:10.2f}')

        if tcode == 'Money Movement':
            if tsubcode == 'Transfer':
                print(header, 'transferred:', description)
            elif tsubcode  in ['Deposit', 'Credit Interest']:
                if description == 'INTEREST ON CREDIT BALANCE':
                    print(header, 'interest')
                    if amount > .0:
                        interest_recv += eur_amount
                    else:
                        interest_paid += eur_amount
                else:
                    if amount > .0:
                        dividends += eur_amount
                        print(header, 'dividends: %s,' % symbol, description)
                    else:
                        withholding_tax += eur_amount
                        print(header, 'withholding tax: %s,' % symbol, description)
                if fees != .0:
                    raise
            elif tsubcode == 'Balance Adjustment':
                if long:
                    print(header, 'balance adjustment')
                fee_adjustments += eur_amount
                total_fees += eur_amount
                if fees != .0:
                    raise
            elif tsubcode == 'Fee':
                # XXX Additional fees for dividends paid in short stock? Interest fees?
                print(header, 'fees: %s,' % symbol, description)
                fee_adjustments += eur_amount
                total_fees += eur_amount
                if amount >= .0:
                    raise
                if fees != .0:
                    raise
            elif tsubcode == 'Withdrawal':
                # XXX In my case dividends paid for short stock:
                print(header, 'dividends paid: %s,' % symbol, description)
                withdrawal += eur_amount
                if amount >= .0:
                    raise
                if fees != .0:
                    raise
            elif tsubcode == 'Dividend':
                if amount > .0:
                    dividends += eur_amount
                    print(header, 'dividends: %s,' % symbol, description)
                else:
                    withholding_tax += eur_amount
                    print(header, 'withholding tax: %s,' % symbol, description)
                if fees != .0:
                    raise
        else:
            asset = symbol
            if str(expire) != 'nan':
                expire = pydatetime.datetime.strptime(expire, '%m/%d/%Y').strftime('%y-%m-%d')
                price *= 100.0
                if int(strike) == strike:
                    strike = int(strike)
                asset = '%s %s%s %s' % (symbol, callput, strike, expire)
                check_stock = False
            else:
                check_stock = is_stock(symbol)
            # 'buysell' is not set correctly for 'Expiration'/'Exercise'/'Assignment' entries,
            # so we look into existing positions to check if we are long or short (we cannot
            # be both, so this test should be safe):
            if str(buysell) == 'Sell' or \
                (tsubcode in ['Expiration', 'Exercise', 'Assignment'] and fifos_islong(fifos, asset)):
                quantity = - quantity
            check_trade(tsubcode, - (quantity * price), amount)
            price = abs((amount - fees) / quantity)
            price = usd2eur(price, date)
            local_pnl = fifo_add(fifos, quantity, price, asset)
            print(datetime, f'{local_pnl:10.2f}' + curr_sym, f'{amount-fees:10.2f}' + '$', '%5d' % quantity, asset)
            if check_stock:
                pnl_stocks += local_pnl
            else:
                pnl += local_pnl

    wk.drop('Account Reference', axis=1, inplace=True)

    print_yearly_summary(cur_year, curr_sym, dividends, withholding_tax,
        withdrawal, interest_recv, interest_paid, fee_adjustments, pnl_stocks,
        pnl, usd, total_fees, total, fifos)

    #print(wk)

def help():
    print('tw-pnl.py [--assume-individual-stock][--long][--usd][--help] *.csv')

def main(argv):
    long = False
    try:
        opts, args = getopt.getopt(argv, 'hlu',
            ['assume-individual-stock', 'help', 'long', 'usd'])
    except getopt.GetoptError:
        help()
        sys.exit(2)
    for opt, arg in opts:
        if opt == '--assume-individual-stock':
            global assume_stock
            assume_stock = True
        elif opt in ('-h', '--help'):
            help()
            sys.exit()
        elif opt in ('-l', '--long'):
            long = True
        elif opt in ('-u', '--usd'):
            global convert_currency
            convert_currency = False
    read_eurusd()
    args.reverse()
    for csv_file in args:
        wk = pandas.read_csv(csv_file, parse_dates=['Date/Time']) # 'Expiration Date'])
        check(wk, long)

if __name__ == '__main__':
    main(sys.argv[1:])

