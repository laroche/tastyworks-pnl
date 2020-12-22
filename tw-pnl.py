#!/usr/bin/python3
#
# Copyright (C) 2020 Florian La Roche <Florian.LaRoche@gmail.com>
#
# Generate data for a German tax income statement from Tastyworks trade history.
#
#
# Download your trade history as csv file from
# https://trade.tastyworks.com/index.html#/transactionHistoryPage
# (Choose 'Activity' and then 'History' and then setup the filter for a
# custom period of time and download it as csv file.)
# Newest entries in the csv file should be on the top and it should contain the complete
# history over all years. The csv file has the following first line:
# Date/Time,Transaction Code,Transaction Subcode,Symbol,Buy/Sell,Open/Close,\
#   Quantity,Expiration Date,Strike,Call/Put,Price,Fees,Amount,Description,Account Reference
#
#
# Install on Debian/Ubuntu-based systems:
#
# sudo apt-get install python3-pandas
#
#
# pylint: disable=C0103,C0114,C0116
#

import sys
import os
import getopt
from collections import deque
import math
import datetime as pydatetime
import pandas
#import matplotlib.pyplot as plt

convert_currency = True

# For an unknown symbol (underlying), assume it is a individual/normal stock.
# Otherwise you need to adjust the hardcoded list in this script.
assume_stock = False

eurusd = None

# Setup 'eurusd' as dict() to contain the EURUSD exchange rate on a given date
# based on official data from bundesbank.de.
# If the file 'eurusd.csv' does not exist, download the data from
# the bundesbank directly.
def read_eurusd():
    global eurusd
    url = 'eurusd.csv'
    if not os.path.exists(url):
        url = 'https://www.bundesbank.de/statistic-rmi/StatisticDownload?tsId=BBEX3.D.USD.EUR.BB.AC.000&its_csvFormat=en&its_fileFormat=csv&mode=its&its_from=2010'
    eurusd = pandas.read_csv(url, skiprows=5, skipfooter=2, names=['date', 'eurusd', 'nix'],
        usecols=['date', 'eurusd'], na_values=['.'], engine='python')
    eurusd = dict(eurusd.values.tolist())

def get_eurusd(date, debug=False):
    while True:
        x = eurusd[date]
        if str(x) != 'nan':
            return x
        if debug:
            print('EURUSD conversion not found for', date)
        date = str(pydatetime.date(*map(int, date.split('-'))) - pydatetime.timedelta(days=1))

def eur2usd(x, date, conv=None):
    if convert_currency:
        if conv is None:
            return x * get_eurusd(date)
        return x * conv
    return x

def usd2eur(x, date, conv=None):
    if convert_currency:
        if conv is None:
            return x / get_eurusd(date)
        return x / conv
    return x

def check_tcode(tcode, tsubcode, description):
    if tcode not in ['Money Movement', 'Trade', 'Receive Deliver']:
        raise
    if tcode == 'Money Movement':
        if tsubcode not in ['Transfer', 'Deposit', 'Credit Interest', 'Balance Adjustment',
            'Fee', 'Withdrawal', 'Dividend']:
            raise
        if tsubcode == 'Balance Adjustment' and description != 'Regulatory fee adjustment':
            raise
    elif tcode == 'Trade':
        if tsubcode not in ['Sell to Open', 'Buy to Close', 'Buy to Open', 'Sell to Close']:
            raise
    elif tcode == 'Receive Deliver':
        if tsubcode not in ['Sell to Open', 'Buy to Close', 'Buy to Open', 'Sell to Close',
            'Expiration', 'Assignment', 'Exercise']:
            raise
        if tsubcode == 'Assignment' and description != 'Removal of option due to assignment':
            raise
        if tsubcode == 'Exercise' and description != 'Removal of option due to exercise':
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
        print('Use the option --assume-individual-stock to assume ' +
            'individual stock for all unknown symbols.')
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
def fifo_add(fifos, quantity, price, asset, debug=False, debugfifo=False):
    (pnl, term_losses) = (.0, .0)
    if quantity == 0:
        return (pnl, term_losses)
    if debug:
        print_fifos(fifos)
        print('fifo_add', quantity, price, asset)
    # Detect if this is an option we are working with as
    # we have to pay taxes for selling an option:
    # This is a gross hack, should we check the 'expire' param?
    is_option = (len(asset) > 10 and asset != 'account-usd')
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
            if is_option and quantity > 0:
                pnl -= quantity * price
            else:
                p = quantity * (price - fifo[0][0])
                pnl -= p
                if is_option and quantity < 0 and p > .0:
                    #print('Termingeschäft-Verlust von %.2f:' % p)
                    term_losses += p
            if debugfifo:
                print('DEBUG FIFO: %s: del %7d * %8.2f (new: %8.2f) = %8.2f pnl' \
                    % (asset, quantity, fifo[0][0], price, pnl))
            fifo[0][1] += quantity
            if fifo[0][1] == 0:
                fifo.popleft()
                if len(fifo) == 0:
                    del fifos[asset]
            return (pnl, term_losses)
        # Remove the oldest FIFO entry and continue
        # the loop for further entries (or add the
        # remaining entries into the FIFO).
        if is_option and quantity > 0:
            pnl += fifo[0][1] * price
        else:
            p = fifo[0][1] * (price - fifo[0][0])
            pnl +=  p
            # XXX: verify this, not happening in my case:
            if is_option and quantity < 0 and p < .0:
                print('2Termingeschäft-Verlust von %.2f:' % -p)
                term_losses -= p
        if debugfifo:
            print('DEBUG FIFO: %s: del %7d * %8.2f (new: %8.2f) = %8.2f pnl' \
                % (asset, -fifo[0][1], fifo[0][0], price, pnl))
        quantity += fifo[0][1]
        fifo.popleft()
    # Just add this to the FIFO queue:
    fifo.append([price, quantity])
    # selling an option is taxed directly as income
    if is_option and quantity < 0:
        pnl -= quantity * price
    if debugfifo:
        print('DEBUG FIFO: %s: add %7d * %8.2f = %8.2f pnl' \
            % (asset, quantity, price, pnl))
    return (pnl, term_losses)

# Check if the first entry in the FIFO
# is 'long' the underlying or 'short'.
def fifos_islong(fifos, asset):
    return fifos[asset][0][1] > 0

def print_fifos(fifos):
    print('open positions:')
    for fifo in fifos:
        print(fifo, fifos[fifo])

def print_yearly_summary(cur_year, curr_sym, dividends, withholding_tax,
        withdrawal, interest_recv, interest_paid, fee_adjustments, pnl_stocks_gains,
        pnl_stocks_losses, pnl, account_usd, total_fees, term_losses, total, fifos, verbose):
    print()
    print('Total sums paid and received in the year %s:' % cur_year)
    if dividends != .0 or withholding_tax != .0 or verbose:
        print('dividends received:   ', f'{dividends:10.2f}' + curr_sym)
        print('withholding tax paid: ', f'{-withholding_tax:10.2f}' + curr_sym)
    if withdrawal != .0:
        print('dividends paid:       ', f'{-withdrawal:10.2f}' + curr_sym)
    print('interest received:    ', f'{interest_recv:10.2f}' + curr_sym)
    if interest_paid != .0:
        print('interest paid:        ', f'{-interest_paid:10.2f}' + curr_sym)
    print('fee adjustments:      ', f'{fee_adjustments:10.2f}' + curr_sym)
    if pnl_stocks_gains != .0 or pnl_stocks_losses != .0 or verbose:
        print('pnl stocks gains:     ', f'{pnl_stocks_gains:10.2f}' + curr_sym)
        print('pnl stocks losses:    ', f'{pnl_stocks_losses:10.2f}' + curr_sym)
    print('pnl other:            ', f'{pnl:10.2f}' + curr_sym)
    print('USD currency gains:   ', f'{account_usd:10.2f}' + curr_sym)
    print()
    print('New end sums and open positions:')
    print('total fees paid:      ', f'{total_fees:10.2f}' + curr_sym)
    print('Verlustverrechnungstopf Termingeschaefte: ', f'{term_losses:10.2f}' + curr_sym)
    print('account end total:    ', f'{total:10.2f}' + '$')
    print_fifos(fifos)
    print()

def check(wk, output_csv, output_excel, opt_long, verbose, debugfifo):
    #print(wk)
    curr_sym = '€'
    if not convert_currency:
        curr_sym = '$'
    fifos = {}
    total = .0                # account total
    (pnl_stocks_gains, pnl_stocks_losses, pnl, account_usd) = (.0, .0, .0, .0)
    (dividends, withholding_tax, interest_recv, interest_paid) = (.0, .0, .0, .0)
    (withdrawal, fee_adjustments, total_fees, term_losses) = (.0, .0, .0, .0)
    cur_year = None
    check_account_ref = None
    new_wk = []
    for i in reversed(wk.index):
        # Date/Time,Transaction Code,Transaction Subcode,Symbol,Buy/Sell,Open/Close,\
        #   Quantity,Expiration Date,Strike,Call/Put,Price,Fees,Amount,Description,\
        #   Account Reference
        (datetime, tcode, tsubcode, symbol, buysell, openclose, quantity, expire, strike,
            callput, price, fees, amount, description, account_ref) = wk.iloc[i]
        if str(datetime)[16:] != ':00': # minimum output is minutes, seconds are 00 here
            raise
        datetime = str(datetime)[:16]
        date = datetime[:10] # year-month-day but no time
        if cur_year != datetime[:4]:
            if cur_year is not None:
                print_yearly_summary(cur_year, curr_sym, dividends, withholding_tax,
                    withdrawal, interest_recv, interest_paid, fee_adjustments,
                    pnl_stocks_gains, pnl_stocks_losses, pnl, account_usd, total_fees,
                    term_losses, total, fifos, verbose)
                (pnl_stocks_gains, pnl_stocks_losses, pnl, account_usd) = (.0, .0, .0, .0)
                (dividends, withholding_tax, interest_recv, interest_paid) = (.0, .0, .0, .0)
                (withdrawal, fee_adjustments, total_fees, term_losses) = (.0, .0, .0, .0)
            cur_year = datetime[:4]
        check_tcode(tcode, tsubcode, description)
        check_param(buysell, openclose, callput)
        if check_account_ref is None:
            check_account_ref = account_ref
        if account_ref != check_account_ref: # check if this does not change over time
            raise
        (amount, fees) = (float(amount), float(fees))
        conv_usd = get_eurusd(date)
        total_fees += usd2eur(fees, date, conv_usd)
        total += amount - fees
        eur_amount = usd2eur(amount - fees, date)
        # USD as a big integer number:
        usd_gains = fifo_add(fifos, int((amount - fees) * 10000),
            1 / conv_usd, 'account-usd', debugfifo=debugfifo)[0] / 10000.0
        account_usd += usd_gains
        asset = ''
        newdescription = ''

        if str(quantity) == 'nan':
            quantity = 1
        else:
            if int(quantity) != quantity:
                raise
            quantity = int(quantity)

        if str(price) == 'nan':
            price = .0
        if price < .0:
            raise

        header = '%s %s' % (datetime, f'{eur_amount:10.2f}' + curr_sym)
        if verbose:
            header += ' %s' % f'{usd_gains:10.2f}' + '€'
        header += ' %s' % f'{amount - fees:10.2f}' + '$'
        if verbose:
            header += ' %s' % f'{conv_usd:8.4f}'
        header += ' %5d' % quantity

        if tcode == 'Money Movement':
            local_pnl = '%.4f' % eur_amount
            term_loss = .0
            if tsubcode != 'Transfer' and fees != .0:
                raise
            if tsubcode == 'Transfer':
                local_pnl = ''
                asset = 'transfer'
                newdescription = description
                print(header, 'transferred:', description)
            elif tsubcode  in ['Deposit', 'Credit Interest']:
                if description == 'INTEREST ON CREDIT BALANCE':
                    asset = 'interest'
                    print(header, 'interest')
                    if amount > .0:
                        interest_recv += eur_amount
                    else:
                        interest_paid += eur_amount
                else:
                    if amount > .0:
                        asset = 'dividends for %s' % symbol
                        dividends += eur_amount
                        print(header, 'dividends: %s,' % symbol, description)
                    else:
                        asset = 'withholding tax for %s' % symbol
                        withholding_tax += eur_amount
                        print(header, 'withholding tax: %s,' % symbol, description)
                    newdescription = description
            elif tsubcode == 'Balance Adjustment':
                asset = 'balance adjustment'
                if opt_long:
                    print(header, 'balance adjustment')
                fee_adjustments += eur_amount
                total_fees += eur_amount
            elif tsubcode == 'Fee':
                # XXX Additional fees for dividends paid in short stock? Interest fees?
                asset = 'fees for %s' % symbol
                newdescription = description
                print(header, 'fees: %s,' % symbol, description)
                fee_adjustments += eur_amount
                total_fees += eur_amount
                if amount >= .0:
                    raise
            elif tsubcode == 'Withdrawal':
                # XXX In my case dividends paid for short stock:
                asset = 'dividends paid for %s' % symbol
                newdescription = description
                print(header, 'dividends paid: %s,' % symbol, description)
                withdrawal += eur_amount
                if amount >= .0:
                    raise
            elif tsubcode == 'Dividend':
                if amount > .0:
                    asset = 'dividends for %s' % symbol
                    dividends += eur_amount
                    print(header, 'dividends: %s,' % symbol, description)
                else:
                    asset = 'withholding tax for %s' % symbol
                    withholding_tax += eur_amount
                    print(header, 'withholding tax: %s,' % symbol, description)
                newdescription = description
        else:
            asset = symbol
            if str(expire) != 'nan':
                expire = pydatetime.datetime.strptime(expire, '%m/%d/%Y').strftime('%y-%m-%d')
                price *= 100.0
                if int(strike) == strike: # convert to integer for full numbers
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
            if tsubcode in ['Exercise', 'Assignment'] and quantity < 0:
                print('Assignment/Exercise for a long option, please move pnl on next line to stock:')
            check_trade(tsubcode, - (quantity * price), amount)
            price = abs((amount - fees) / quantity)
            price = usd2eur(price, date, conv_usd)
            (local_pnl, term_loss) = fifo_add(fifos, quantity, price, asset, debugfifo=debugfifo)
            term_losses += term_loss
            header = '%s %s' % (datetime, f'{local_pnl:10.2f}' + curr_sym)
            if verbose:
                header += ' %s' % f'{usd_gains:10.2f}' + '€'
            header += ' %s' % f'{amount-fees:10.2f}' + '$'
            if verbose:
                header += ' %s' % f'{conv_usd:8.4f}'
            print(header, '%5d' % quantity, asset)
            if check_stock:
                if local_pnl > .0:
                    pnl_stocks_gains += local_pnl
                else:
                    pnl_stocks_losses += local_pnl
            else:
                pnl += local_pnl
            description = ''
            local_pnl = '%.4f' % local_pnl
        new_wk.append([datetime, local_pnl, '%.2f' % usd_gains, '%.2f' % eur_amount,
            '%.4f' % amount, '%.4f' % fees, '%.4f' % conv_usd, quantity, asset, symbol,
            newdescription, '%.2f' % total, '%.2f' % term_loss])

    wk.drop('Account Reference', axis=1, inplace=True)

    print_yearly_summary(cur_year, curr_sym, dividends, withholding_tax,
        withdrawal, interest_recv, interest_paid, fee_adjustments, pnl_stocks_gains,
        pnl_stocks_losses, pnl, account_usd, total_fees, term_losses, total, fifos, verbose)

    #print(wk)
    new_wk = pandas.DataFrame(new_wk, columns=('datetime', 'pnl', 'usd_gains',
        'eur_amount', 'amount', 'fees', 'eurusd', 'quantity', 'asset', 'symbol',
        'description', 'account_total', 'term_loss'))
    if output_csv is not None:
        with open(output_csv, 'w') as f:
            new_wk.to_csv(f, index=False)
    if output_excel is not None:
        with pandas.ExcelWriter(output_excel) as f:
            new_wk.to_excel(f, index=False, sheet_name='Tastyworks Report') #, engine='xlsxwriter')
    #print(new_wk)

def usage():
    print('tw-pnl.py [--assume-individual-stock][--long][--usd][--output-csv=test.csv]' +
        '[--output-excel=test.xlsx][--help][--verbose] *.csv')

def main(argv):
    opt_long = False
    verbose = False
    debugfifo = False
    output_csv = None
    output_excel = None
    try:
        opts, args = getopt.getopt(argv, 'hluv', ['assume-individual-stock', 'help', 'long',
            'output-csv=', 'output-excel=', 'usd', 'verbose', 'debug-fifo'])
    except getopt.GetoptError:
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt == '--assume-individual-stock':
            global assume_stock
            assume_stock = True
        elif opt in ('-h', '--help'):
            usage()
            sys.exit()
        elif opt in ('-l', '--long'):
            opt_long = True
        elif opt == '--output-csv':
            output_csv = arg
        elif opt == '--output-excel':
            output_excel = arg
        elif opt in ('-u', '--usd'):
            global convert_currency
            convert_currency = False
        elif opt in ('-v', '--verbose'):
            verbose = True
        elif opt == '--debug-fifo':
            debugfifo = True
    if len(args) == 0:
        usage()
        sys.exit()
    read_eurusd()
    args.reverse()
    for csv_file in args:
        wk = pandas.read_csv(csv_file, parse_dates=['Date/Time']) # 'Expiration Date'])
        check(wk, output_csv, output_excel, opt_long, verbose, debugfifo)

if __name__ == '__main__':
    main(sys.argv[1:])

