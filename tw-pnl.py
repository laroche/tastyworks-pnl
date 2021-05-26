#!/usr/bin/python3
#
# Copyright (C) 2020-2021 Florian La Roche <Florian.LaRoche@gmail.com>
# https://github.com/laroche/tastyworks-pnl
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
# pylint: disable=C0103,C0111,C0114,C0116,C0326,C0330
#

import enum
import sys
import os
import getopt
from collections import deque
import math
import datetime as pydatetime
import pandas
from constants import ETFS, STOCKS

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

def isnan(x):
    return str(x) == 'nan'

def get_eurusd(date, debug=False):
    while True:
        try:
            x = eurusd[date]
        except KeyError:
            print('ERROR: No EURUSD conversion data available for %s,'
                ' please download newer data into the file eurusd.csv.' % date)
            sys.exit(1)
        if not isnan(x):
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
    if tcode not in ('Money Movement', 'Trade', 'Receive Deliver'):
        raise
    if tcode == 'Money Movement':
        if tsubcode not in ('Transfer', 'Deposit', 'Credit Interest', 'Balance Adjustment',
            'Fee', 'Withdrawal', 'Dividend', 'Debit Interest'):
            raise
        if tsubcode == 'Balance Adjustment' and description != 'Regulatory fee adjustment':
            raise
    elif tcode == 'Trade':
        if tsubcode not in ('Sell to Open', 'Buy to Close', 'Buy to Open', 'Sell to Close'):
            raise
    elif tcode == 'Receive Deliver':
        if tsubcode not in ('Sell to Open', 'Buy to Close', 'Buy to Open', 'Sell to Close',
            'Expiration', 'Assignment', 'Exercise', 'Forward Split'):
            raise
        if tsubcode == 'Assignment' and description != 'Removal of option due to assignment':
            raise
        if tsubcode == 'Exercise' and description != 'Removal of option due to exercise':
            raise

def check_param(buysell, openclose, callput):
    if str(buysell) not in ('nan', 'Buy', 'Sell'):
        raise
    if str(openclose) not in ('nan', 'Open', 'Close'):
        raise
    if str(callput) not in ('nan', 'C', 'P'):
        raise

def check_trade(tsubcode, check_amount, amount):
    #print('FEHLER:', check_amount, amount)
    if tsubcode not in ('Expiration', 'Assignment', 'Exercise'):
        if not math.isclose(check_amount, amount, abs_tol=0.001):
            raise
    else:
        if not isnan(amount) and amount != .0:
            raise
        if not isnan(check_amount) and check_amount != .0:
            raise

class AssetType(enum.Enum):
    Option = 1
    IndStock = 2
    AktienFond = 3
    MischFond = 4
    ImmobilienFond = 5
    OtherStock = 6


def read_sp500():
    table = pandas.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
    df = table[0]
    df.drop('SEC filings', axis=1, inplace=True)
    return df

def print_sp500():
    import pprint
    df = read_sp500()
    #df['Symbol'] = df['Symbol'].str.replace('.', '/')
    symbols = df['Symbol'].values.tolist()
    symbols.sort()
    p = pprint.pformat(symbols, width=79, compact=True, indent=4)
    print(p)

def read_nasdaq100():
    table = pandas.read_html('https://en.wikipedia.org/wiki/NASDAQ-100')
    df = table[3]
    return df

def print_nasdaq100():
    import pprint
    df = read_nasdaq100()
    #df['Ticker'] = df['Ticker'].str.replace('.', '/')
    symbols = df['Ticker'].values.tolist()
    p = pprint.pformat(symbols, width=79, compact=True, indent=4)
    print(p)


# Is the symbol a individual stock or anything else
# like an ETF or fond?
def is_stock(symbol):
    # Well known ETFs:
    if symbol in ETFS:
        return AssetType.OtherStock # AktienFond
    if symbol in ('TLT','HYG','IEF','GLD','SLV','VXX','UNG','USO'):
        return AssetType.OtherStock
    # Well known individual stock names:
    if symbol in STOCKS:
        return AssetType.IndStock
    # The conservative way is to through an exception if we are not sure.
    if not assume_stock:
        print('No idea if this is a stock:', symbol)
        print('Use the option --assume-individual-stock to assume ' +
            'individual stock for all unknown symbols.')
        raise
    # Just assume this is a normal stock if not in the above list
    return AssetType.IndStock

def sign(x):
    if x >= 0:
        return 1
    return -1

# return date of one year earlier:
def prev_year(date):
    if date is None:
        return None
    return str(int(date[:4]) - 1) + date[4:]

# 'fifos' is a dictionary with 'asset' names. It contains a FIFO
# 'deque()' with a list of 'price' (as float), 'price_usd' (as float),
# 'quantity' (as integer), 'date' of purchase and 'tax_free'.
def fifo_add(fifos, quantity, price, price_usd, asset, is_option, date=None,
    tax_free=False, debug=False, debugfifo=False, debugcurr=False):
    prevyear = prev_year(date)
    (pnl, pnl_notax, term_losses) = (.0, .0, .0)
    if quantity == 0:
        return (pnl, pnl_notax, term_losses)
    if debug:
        print_fifos(fifos)
        print('fifo_add', quantity, price, asset)
    # Find the right FIFO queue for our asset:
    if fifos.get(asset) is None:
        fifos[asset] = deque()
    fifo = fifos[asset]
    # If the queue is empty, just add it to the queue:
    while len(fifo) > 0:
        # If we add assets into the same trading direction,
        # just add the asset into the queue. (Buy more if we are
        # already long, or sell more if we are already short.)
        if sign(fifo[0][2]) == sign(quantity):
            break
        # Here we start removing entries from the FIFO.
        # Check if the FIFO queue has enough entries for
        # us to finish:
        if abs(fifo[0][2]) >= abs(quantity):
            if is_option and quantity > 0:
                pnl -= quantity * price
            else:
                p = quantity * (price - fifo[0][0])
                if date is None or \
                    (fifo[0][3] > prevyear and quantity < 0 and \
                    not fifo[0][4] and not tax_free):
                    pnl -= p
                else:
                    pnl_notax -= p
                    if date is not None and debugcurr:
                        print(fifo[0][3], '%.2f' % (-p / 10000.0),
                            'over one year ago or paying back loan or tax free')
                if is_option and quantity < 0 and p > .0:
                    #print('Termingeschäft-Verlust von %.2f:' % p)
                    term_losses += p
            if debugfifo:
                print('DEBUG FIFO: %s: del %7d * %8.2f (new: %8.2f) = %8.2f pnl' \
                    % (asset, quantity, fifo[0][0], price, pnl))
            fifo[0][2] += quantity
            if fifo[0][2] == 0:
                fifo.popleft()
                if len(fifo) == 0:
                    del fifos[asset]
            return (pnl, pnl_notax, term_losses)
        # Remove the oldest FIFO entry and continue
        # the loop for further entries (or add the
        # remaining entries into the FIFO).
        if is_option and quantity > 0:
            pnl += fifo[0][2] * price
        else:
            p = fifo[0][2] * (price - fifo[0][0])
            if date is None or \
                (fifo[0][3] > prevyear and quantity < 0 and \
                not fifo[0][4] and not tax_free):
                pnl += p
            else:
                pnl_notax += p
                if date is not None and debugcurr:
                    print(fifo[0][3], '%.2f' % (p / 10000.0),
                        'over one year ago or paying back loan or tax free')
            if is_option and quantity < 0 and p < .0:
                #print('Termingeschäft-Verlust von %.2f:' % -p)
                term_losses -= p
        if debugfifo:
            print('DEBUG FIFO: %s: del %7d * %8.2f (new: %8.2f) = %8.2f pnl' \
                % (asset, -fifo[0][2], fifo[0][0], price, pnl))
        quantity += fifo[0][2]
        fifo.popleft()
    # Just add this to the FIFO queue:
    fifo.append([price, price_usd, quantity, date, tax_free])
    # selling an option is taxed directly as income
    if is_option and quantity < 0:
        pnl -= quantity * price
    if debugfifo:
        print('DEBUG FIFO: %s: add %7d * %8.2f = %8.2f pnl' \
            % (asset, quantity, price, pnl))
    return (pnl, pnl_notax, term_losses)

# Check if the first entry in the FIFO
# is 'long' the underlying or 'short'.
def fifos_islong(fifos, asset):
    return fifos[asset][0][2] > 0

def fifos_sum_usd(fifos):
    sum_usd = .0
    for fifo in fifos:
        if fifo != 'account-usd':
            for (price, price_usd, quantity, date, tax_free) in fifos[fifo]:
                sum_usd += price_usd * quantity
    return sum_usd

# stock (and option) split
def fifos_split(fifos, asset, ratio):
    for fifo in fifos:
        # adjust stock for split:
        if fifo == asset:
            for f in fifos[fifo]:
                f[0] = f[0] / ratio
                f[1] = f[1] / ratio
                f[2] = f[2] * ratio
        # XXX: implement option strike adjustment
        # fifo == asset + ' ' + 'P/C' + Strike + ' '

def print_fifos(fifos):
    print('open positions:')
    for fifo in fifos:
        print(fifo, fifos[fifo])

# account-usd should always be the same as total together with
# EURUSD conversion data. So just a sanity check:
def check_total(fifos, total):
    for (price, price_usd, quantity, date, tax_free) in fifos['account-usd']:
        total -= quantity / 10000
    if abs(total) > 0.004:
        print(total)
        raise

def show_plt(df):
    import matplotlib.pyplot as plt
    for i in ('account_total', 'net_total', 'pnl', 'usd_gains', 'term_loss'):
        df[i] = pandas.to_numeric(df[i]) # df[i].astype(float)
    #df.plot(x='datetime', y=['account_total', 'pnl', 'term_loss'])
    df.plot(y=['net_total'])
    df.plot(y=['account_total'])
    df.plot(kind='bar', y=['pnl', 'usd_gains', 'term_loss'])
    df.plot(kind='bar', y=['usd_gains'])
    df.plot(kind='bar', y=['term_loss'])
    plt.show()

def print_yearly_summary(cur_year, curr_sym, dividends, withholding_tax,
        withdrawal, interest_recv, interest_paid, fee_adjustments, pnl_stocks_gains,
        pnl_stocks_losses, pnl, account_usd, account_usd_notax, total_fees,
        term_losses, total, fifos, verbose):
    print()
    print('Total sums paid and received in the year %s:' % cur_year)
    if dividends != .0 or withholding_tax != .0 or verbose:
        print('dividends received:      ', f'{dividends:10.2f}' + curr_sym)
        print('withholding tax paid:    ', f'{withholding_tax:10.2f}' + curr_sym)
    if withdrawal != .0:
        print('dividends paid:          ', f'{withdrawal:10.2f}' + curr_sym)
    print('interest received:       ', f'{interest_recv:10.2f}' + curr_sym)
    if interest_paid != .0:
        print('interest paid:           ', f'{interest_paid:10.2f}' + curr_sym)
    print('fee adjustments:         ', f'{fee_adjustments:10.2f}' + curr_sym)
    if pnl_stocks_gains != .0 or pnl_stocks_losses != .0 or verbose:
        print('pnl stocks gains:        ', f'{pnl_stocks_gains:10.2f}' + curr_sym)
        print('pnl stocks losses:       ', f'{pnl_stocks_losses:10.2f}' + curr_sym)
    print('pnl other:               ', f'{pnl:10.2f}' + curr_sym)
    print('pnl total:               ', '%10.2f' % (dividends + \
        withdrawal + interest_recv + interest_paid + fee_adjustments + \
        pnl_stocks_gains + pnl_stocks_losses + pnl) + curr_sym)
    print('USD currency gains:      ', f'{account_usd:10.2f}' + curr_sym)
    print('USD curr. gains (no tax):', f'{account_usd_notax:10.2f}' + curr_sym)
    print('losses future contracts: ', f'{-term_losses:10.2f}' + curr_sym)
    print()
    print('New end sums and open positions:')
    print('total fees paid:         ', f'{total_fees:10.2f}' + curr_sym)
    print('account cash balance:    ', f'{total:10.2f}' + '$')
    print_fifos(fifos)
    print()

def check(wk, output_csv, output_excel, opt_long, verbose, show, debugfifo):
    #print(wk)
    splits = {}               # save data for stock/option splits
    curr_sym = '€'
    if not convert_currency:
        curr_sym = '$'
    fifos = {}
    total = .0                # account total
    (pnl_stocks_gains, pnl_stocks_losses, pnl) = (.0, .0, .0)
    (account_usd, account_usd_notax) = (.0, .0)
    (dividends, withholding_tax, interest_recv, interest_paid) = (.0, .0, .0, .0)
    (withdrawal, fee_adjustments, total_fees, term_losses) = (.0, .0, .0, .0)
    cur_year = None
    prev_datetime = None
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
        if prev_datetime is not None and prev_datetime > datetime:
            raise
        prev_datetime = datetime
        date = datetime[:10] # year-month-day but no time
        if cur_year != datetime[:4]:
            if cur_year is not None:
                print_yearly_summary(cur_year, curr_sym, dividends, withholding_tax,
                    withdrawal, interest_recv, interest_paid, fee_adjustments,
                    pnl_stocks_gains, pnl_stocks_losses, pnl, account_usd, account_usd_notax,
                    total_fees, term_losses, total, fifos, verbose)
                (pnl_stocks_gains, pnl_stocks_losses, pnl) = (.0, .0, .0)
                (account_usd, account_usd_notax) = (.0, .0)
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
        # option/stock splits are tax neutral, so zero out amount/fees for it:
        if tcode == 'Receive Deliver' and tsubcode == 'Forward Split':
            (amount, fees) = (.0, .0)
        conv_usd = get_eurusd(date)
        total_fees += usd2eur(fees, date, conv_usd)
        total += amount - fees
        eur_amount = usd2eur(amount - fees, date)
        # look at currency conversion gains:
        tax_free = False
        if tsubcode in ('Deposit', 'Credit Interest', 'Debit Interest', 'Dividend',
            'Fee', 'Balance Adjustment'):
            tax_free = True
        if tsubcode == 'Withdrawal' and not isnan(symbol):
            tax_free = True
        # Stillhalterpraemien gelten als Zufluss und nicht als Anschaffung
        # und sind daher steuer-neutral:
        # XXX We use "Sell-to-Open" to find all "Stillhaltergeschäfte". This works
        # ok for me, but what happens if we have one long option and sell two? Will
        # Tastyworks split this into two transactions or keep this? With keeping this
        # as one transaction, we should split the currency gains transaction as well.
        # Could we detect this bad case within transactions?
        if tcode != 'Money Movement' and \
            not isnan(expire) and str(buysell) == 'Sell' and str(openclose) == 'Open':
            tax_free = True
        # USD as a big integer number:
        (usd_gains, usd_gains_notax, _) = fifo_add(fifos, int((amount - fees) * 10000),
            1 / conv_usd, 1, 'account-usd', False, date, tax_free, debugfifo=debugfifo)
        (usd_gains, usd_gains_notax) = (usd_gains / 10000.0, usd_gains_notax / 10000.0)
        account_usd += usd_gains
        account_usd_notax += usd_gains_notax

        asset = ''
        newdescription = ''

        if isnan(quantity):
            quantity = 1
        else:
            if tcode == 'Receive Deliver' and tsubcode == 'Forward Split':
                pass # splits might have further data, not quantity
            elif int(quantity) != quantity:
                raise
            else:
                quantity = int(quantity)

        if isnan(price):
            price = .0
        if price < .0:
            raise

        header = '%s %s' % (datetime, f'{eur_amount:10.2f}' + curr_sym)
        if verbose:
            header += ' %s' % f'{usd_gains:10.2f}' + '€'
        header += ' %s' % f'{amount - fees:10.2f}' + '$'
        #if verbose:
        #    header += ' %s' % f'{conv_usd:8.4f}'
        if tcode != 'Receive Deliver' or tsubcode != 'Forward Split':
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
            elif tsubcode in ('Deposit', 'Credit Interest', 'Debit Interest'):
                if isnan(symbol):
                    asset = 'interest'
                    if amount > .0:
                        interest_recv += eur_amount
                    else:
                        interest_paid += eur_amount
                    if description != 'INTEREST ON CREDIT BALANCE':
                        newdescription = description
                        print(header, 'interest:', description)
                    else:
                        print(header, 'interest')
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
                # XXX In my case: stock borrow fee:
                asset = 'stock borrow fees for %s' % symbol
                newdescription = description
                print(header, 'stock borrow fees: %s,' % symbol, description)
                fee_adjustments += eur_amount
                total_fees += eur_amount
                if amount >= .0:
                    raise
            elif tsubcode == 'Withdrawal':
                if not isnan(symbol):
                    # XXX In my case: dividends paid for short stock:
                    asset = 'dividends paid for %s' % symbol
                    newdescription = description
                    print(header, 'dividends paid: %s,' % symbol, description)
                    withdrawal += eur_amount
                    if amount >= .0:
                        raise
                else:
                    # account deposit/withdrawal
                    local_pnl = ''
                    asset = 'transfer'
                    newdescription = description
                    print(header, 'transferred:', description)
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
        elif tcode == 'Receive Deliver' and tsubcode == 'Forward Split':
            # XXX: We might check that the two relevant entries have the same data for 'amount'.
            x = symbol + '-' + date
            # quantity for splits seems to be more like strike price and how it changes.
            # We use it to calculate the split ration / reverse ratio.
            if str(buysell) == 'Sell':
                splits[x] = quantity
            else:
                oldquantity = splits[x]
                ratio = quantity / oldquantity
                if int(ratio) == ratio:
                    ratio = int(ratio)
                #print(symbol, quantity, oldquantity, ratio)
                fifos_split(fifos, symbol, ratio)
        else:
            asset = symbol
            if not isnan(expire):
                expire = pydatetime.datetime.strptime(expire, '%m/%d/%Y').strftime('%y-%m-%d')
                price *= 100.0
                if int(strike) == strike: # convert to integer for full numbers
                    strike = int(strike)
                asset = '%s %s%s %s' % (symbol, callput, strike, expire)
                asset_type = AssetType.Option
            else:
                asset_type = is_stock(symbol)
            # 'buysell' is not set correctly for 'Expiration'/'Exercise'/'Assignment' entries,
            # so we look into existing positions to check if we are long or short (we cannot
            # be both, so this test should be safe):
            if str(buysell) == 'Sell' or \
                (tsubcode in ('Expiration', 'Exercise', 'Assignment') and fifos_islong(fifos, asset)):
                quantity = - quantity
            if tsubcode in ('Exercise', 'Assignment') and quantity < 0:
                print('Assignment/Exercise for a long option, please move pnl on next line to stock:')
            check_trade(tsubcode, - (quantity * price), amount)
            price_usd = abs((amount - fees) / quantity)
            price = usd2eur(price_usd, date, conv_usd)
            (local_pnl, _, term_loss) = fifo_add(fifos, quantity, price, price_usd, asset,
                asset_type == AssetType.Option, debugfifo=debugfifo)
            term_losses += term_loss
            header = '%s %s' % (datetime, f'{local_pnl:10.2f}' + curr_sym)
            if verbose:
                header += ' %s' % f'{usd_gains:10.2f}' + '€'
            header += ' %s' % f'{amount-fees:10.2f}' + '$'
            #if verbose:
            #    header += ' %s' % f'{conv_usd:8.4f}'
            print(header, '%5d' % quantity, asset)
            if asset_type == AssetType.IndStock:
                if local_pnl > .0:
                    pnl_stocks_gains += local_pnl
                else:
                    pnl_stocks_losses += local_pnl
            else:
                if cur_year >= '2018':
                    if asset_type == AssetType.AktienFond:
                        local_pnl *= 0.70
                    elif asset_type == AssetType.MischFond:
                        local_pnl *= 0.85
                    elif asset_type == AssetType.ImmobilienFond:
                        local_pnl *= 0.20
                pnl += local_pnl
            description = ''
            local_pnl = '%.4f' % local_pnl

        #check_total(fifos, total)

        net_total = total + fifos_sum_usd(fifos)

        new_wk.append([datetime, local_pnl, '%.4f' % usd_gains, '%.4f' % usd_gains_notax,
            '%.4f' % eur_amount, '%.4f' % amount, '%.4f' % fees, '%.4f' % conv_usd,
            quantity, asset, symbol, newdescription, '%.2f' % total, '%.2f' % net_total,
            '%.4f' % term_loss, tax_free])

    wk.drop('Account Reference', axis=1, inplace=True)

    print_yearly_summary(cur_year, curr_sym, dividends, withholding_tax,
        withdrawal, interest_recv, interest_paid, fee_adjustments, pnl_stocks_gains,
        pnl_stocks_losses, pnl, account_usd, account_usd_notax, total_fees, term_losses,
        total, fifos, verbose)

    #print(wk)
    new_wk = pandas.DataFrame(new_wk, columns=('datetime', 'pnl', 'usd_gains', 'usd_gains_notax',
        'eur_amount', 'amount', 'fees', 'eurusd', 'quantity', 'asset', 'symbol',
        'description', 'account_total', 'net_total', 'term_loss', 'tax_free'))
    if output_csv is not None:
        with open(output_csv, 'w') as f:
            new_wk.to_csv(f, index=False)
    if output_excel is not None:
        with pandas.ExcelWriter(output_excel) as f:
            new_wk.to_excel(f, index=False, sheet_name='Tastyworks Report') #, engine='xlsxwriter')
    #print(new_wk)

    if show:
        show_plt(new_wk)

def check_csv(csv_file):
    with open(csv_file) as f:
        content = f.readlines()
    if len(content) < 1 or content[0] != 'Date/Time,Transaction Code,' + \
        'Transaction Subcode,Symbol,Buy/Sell,Open/Close,Quantity,' + \
        'Expiration Date,Strike,Call/Put,Price,Fees,Amount,Description,' + \
        'Account Reference\n':
        print('ERROR: Wrong first line in csv file.')
        sys.exit(1)

def usage():
    print('tw-pnl.py [--assume-individual-stock][--long][--usd]' + \
        '[--output-csv=test.csv][--output-excel=test.xlsx][--help]' + \
        '[--verbose] *.csv')

def main(argv):
    opt_long = False
    verbose = False
    debugfifo = False
    output_csv = None
    output_excel = None
    show = False
    try:
        opts, args = getopt.getopt(argv, 'hluv', ['assume-individual-stock',
            'help', 'long', 'output-csv=',
            'output-excel=', 'show', 'usd', 'verbose', 'debug-fifo'])
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
        elif opt == '--show':
            show = True
        elif opt == '--debug-fifo':
            debugfifo = True
    if len(args) == 0:
        usage()
        sys.exit()
    read_eurusd()
    args.reverse()
    for csv_file in args:
        check_csv(csv_file)
        wk = pandas.read_csv(csv_file, parse_dates=['Date/Time']) # 'Expiration Date'])
        check(wk, output_csv, output_excel, opt_long, verbose, show, debugfifo)

if __name__ == '__main__':
    main(sys.argv[1:])

