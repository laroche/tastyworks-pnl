#!/usr/bin/python3
#
# Copyright (C) 2020-2022 Florian La Roche <Florian.LaRoche@gmail.com>
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
# for grphical output (--show) you need at least:
#
# sudo apt-get install python3-matplotlib
#
#
# pylint: disable=C0103,C0114,C0115,C0116,C0301,C0326,C0330,E0704
#

import enum
import sys
import os
from collections import deque
import math
import datetime as pydatetime
import pandas

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
    import csv
    global eurusd
    url = 'eurusd.csv'
    if not os.path.exists(url):
        url = 'https://www.bundesbank.de/statistic-rmi/StatisticDownload?tsId=BBEX3.D.USD.EUR.BB.AC.000&its_csvFormat=en&its_fileFormat=csv&mode=its&its_from=2010'
    eurusd = {}
    with open(url, encoding='UTF8') as csv_file:
        reader = csv.reader(csv_file)
        for _ in range(5):
            next(reader)
        for (date, usd, _) in reader:
            if date != '':
                if usd != '.':
                    eurusd[date] = float(usd)
                else:
                    eurusd[date] = None

def get_eurusd(date):
    while True:
        try:
            x = eurusd[date]
        except KeyError:
            print(f'ERROR: No EURUSD conversion data available for {date},'
                ' please download newer data into the file eurusd.csv.')
            sys.exit(1)
        if x is not None:
            return x
        date = str(pydatetime.date(*map(int, date.split('-'))) - pydatetime.timedelta(days=1))

#def eur2usd(x, date, conv=None):
#    if convert_currency:
#        if conv is None:
#            return x * get_eurusd(date)
#        return x * conv
#    return x

def usd2eur(x, date, conv=None):
    if convert_currency:
        if conv is None:
            return x / get_eurusd(date)
        return x / conv
    return x

def isnan(x):
    return str(x) == 'nan'

class AssetType(enum.IntEnum):
    LongOption = 1
    ShortOption = 2
    IndStock = 3
    AktienFond = 4
    MischFond = 5
    ImmobilienFond = 6
    OtherStock = 7
    Crypto = 8
    Future = 9
    Transfer = 10
    Dividend = 11
    Interest = 12
    WithholdingTax = 13
    OrderPayments = 14
    Fee = 15

def transaction_type(asset_type):
    t = ['', 'Long-Option', 'Stillhalter-Option', 'Aktie', 'Aktienfond', 'Mischfond', 'Immobilienfond',
        'Sonstiges', 'Krypto', 'Future', 'Ein/Auszahlung', 'Dividende', 'Zinsen',
        'Quellensteuer', 'Ordergebühr', 'Brokergebühr']
    if int(asset_type) >= 1 and int(asset_type) <= 15:
        return t[asset_type]
    return ''

transaction_order = {
    'Ein/Auszahlung': 1, 'Brokergebühr': 2, 'Krypto': 3,
    'Aktienfond': 4, 'Mischfond': 5, 'Immobilienfond': 6,
    'Aktie': 7, 'Dividende': 8, 'Quellensteuer': 9,
    'Sonstiges': 10, 'Stillhalter-Option': 11,
    'Long-Option': 12, 'Future': 13, 'Zinsen': 14, 'Ordergebühr': 15,
}

def check_tcode(tcode, tsubcode, description):
    if tcode not in ('Money Movement', 'Trade', 'Receive Deliver'):
        raise Exception(f'Unknown tcode: {tcode}')
    if tcode == 'Money Movement':
        if tsubcode not in ('Transfer', 'Deposit', 'Credit Interest', 'Balance Adjustment',
            'Fee', 'Withdrawal', 'Dividend', 'Debit Interest', 'Mark to Market'):
            raise ValueError(f'Unknown tsubcode for Money Movement: {tsubcode}')
        if tsubcode == 'Balance Adjustment' and description != 'Regulatory fee adjustment' \
            and not description.startswith('Fee Correction'):
            raise ValueError(f'Unknown Balance Adjustment: {description}')
    elif tcode == 'Trade':
        if tsubcode not in ('Sell to Open', 'Buy to Close', 'Buy to Open', 'Sell to Close', 'Buy', 'Sell'):
            raise ValueError(f'Unknown tsubcode: {tsubcode}')
    elif tcode == 'Receive Deliver':
        if tsubcode not in ('Sell to Open', 'Buy to Close', 'Buy to Open', 'Sell to Close',
            'Expiration', 'Assignment', 'Exercise', 'Forward Split', 'Reverse Split',
            'Special Dividend', 'Cash Settled Assignment', 'Cash Settled Exercise',
            'Futures Settlement', 'Transfer'):
            raise ValueError(f'Unknown Receive Deliver tsubcode: {tsubcode}')
        if tsubcode == 'Assignment' and description != 'Removal of option due to assignment':
            raise ValueError(f'Assignment with description {description}')
        if tsubcode == 'Exercise' and description != 'Removal of option due to exercise':
            raise ValueError(f'Exercise with description {description}')

def check_param(buysell, openclose, callput):
    if str(buysell) not in ('nan', 'Buy', 'Sell'):
        raise ValueError(f'Unknown buysell: {buysell}')
    if str(openclose) not in ('nan', 'Open', 'Close'):
        raise ValueError(f'Unknown openclose: {openclose}')
    if str(callput) not in ('nan', 'C', 'P'):
        raise ValueError(f'Unknown callput: {callput}')

def check_trade(tsubcode, check_amount, amount, asset_type):
    #print('FEHLER:', check_amount, amount, tsubcode)
    if tsubcode in ('Buy', 'Sell', 'Cash Settled Assignment', 'Cash Settled Exercise',
        'Special Dividend', 'Futures Settlement'):
        pass
    elif tsubcode not in ('Expiration', 'Assignment', 'Exercise'):
        if asset_type == AssetType.Crypto:
            if not math.isclose(check_amount, amount, abs_tol=0.01):
                raise ValueError(f'Amount mismatch for Crypto: {check_amount} != {amount}')
        else:
            if not math.isclose(check_amount, amount, abs_tol=0.001):
                raise ValueError(f'Amount mismatch: {check_amount} != {amount}')
    else:
        if not isnan(amount) and amount != .0:
            raise
        if not isnan(check_amount) and check_amount != .0:
            raise

# https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
SP500 = ('A', 'AAL', 'AAP', 'AAPL', 'ABBV', 'ABC', 'ABT', 'ACGL', 'ACN', 'ADBE',
    'ADI', 'ADM', 'ADP', 'ADSK', 'AEE', 'AEP', 'AES', 'AFL', 'AIG', 'AIZ',
    'AJG', 'AKAM', 'ALB', 'ALGN', 'ALK', 'ALL', 'ALLE', 'AMAT', 'AMCR', 'AMD',
    'AME', 'AMGN', 'AMP', 'AMT', 'AMZN', 'ANET', 'ANSS', 'AON', 'AOS', 'APA',
    'APD', 'APH', 'APTV', 'ARE', 'ATO', 'ATVI', 'AVB', 'AVGO', 'AVY', 'AWK',
    'AXP', 'AZO', 'BA', 'BAC', 'BALL', 'BAX', 'BBWI', 'BBY', 'BDX', 'BEN',
    'BF.B', 'BIIB', 'BIO', 'BK', 'BKNG', 'BKR', 'BLK', 'BMY', 'BR', 'BRK.B',
    'BRO', 'BSX', 'BWA', 'BXP', 'C', 'CAG', 'CAH', 'CARR', 'CAT', 'CB', 'CBOE',
    'CBRE', 'CCI', 'CCL', 'CDAY', 'CDNS', 'CDW', 'CE', 'CEG', 'CF', 'CFG',
    'CHD', 'CHRW', 'CHTR', 'CI', 'CINF', 'CL', 'CLX', 'CMA', 'CMCSA', 'CME',
    'CMG', 'CMI', 'CMS', 'CNC', 'CNP', 'COF', 'COO', 'COP', 'COST', 'CPB',
    'CPRT', 'CPT', 'CRL', 'CRM', 'CSCO', 'CSGP', 'CSX', 'CTAS', 'CTLT', 'CTRA',
    'CTSH', 'CTVA', 'CVS', 'CVX', 'CZR', 'D', 'DAL', 'DD', 'DE', 'DFS', 'DG',
    'DGX', 'DHI', 'DHR', 'DIS', 'DISH', 'DLR', 'DLTR', 'DOV', 'DOW', 'DPZ',
    'DRI', 'DTE', 'DUK', 'DVA', 'DVN', 'DXC', 'DXCM', 'EA', 'EBAY', 'ECL',
    'ED', 'EFX', 'EIX', 'EL', 'ELV', 'EMN', 'EMR', 'ENPH', 'EOG', 'EPAM',
    'EQIX', 'EQR', 'EQT', 'ES', 'ESS', 'ETN', 'ETR', 'ETSY', 'EVRG', 'EW',
    'EXC', 'EXPD', 'EXPE', 'EXR', 'F', 'FANG', 'FAST', 'FCX', 'FDS', 'FDX',
    'FE', 'FFIV', 'FIS', 'FISV', 'FITB', 'FLT', 'FMC', 'FOX', 'FOXA', 'FRC',
    'FRT', 'FSLR', 'FTNT', 'FTV', 'GD', 'GE', 'GEN', 'GILD', 'GIS', 'GL',
    'GLW', 'GM', 'GNRC', 'GOOG', 'GOOGL', 'GPC', 'GPN', 'GRMN', 'GS', 'GWW',
    'HAL', 'HAS', 'HBAN', 'HCA', 'HD', 'HES', 'HIG', 'HII', 'HLT', 'HOLX',
    'HON', 'HPE', 'HPQ', 'HRL', 'HSIC', 'HST', 'HSY', 'HUM', 'HWM', 'IBM',
    'ICE', 'IDXX', 'IEX', 'IFF', 'ILMN', 'INCY', 'INTC', 'INTU', 'INVH', 'IP',
    'IPG', 'IQV', 'IR', 'IRM', 'ISRG', 'IT', 'ITW', 'IVZ', 'J', 'JBHT', 'JCI',
    'JKHY', 'JNJ', 'JNPR', 'JPM', 'K', 'KDP', 'KEY', 'KEYS', 'KHC', 'KIM',
    'KLAC', 'KMB', 'KMI', 'KMX', 'KO', 'KR', 'L', 'LDOS', 'LEN', 'LH', 'LHX',
    'LIN', 'LKQ', 'LLY', 'LMT', 'LNC', 'LNT', 'LOW', 'LRCX', 'LUMN', 'LUV',
    'LVS', 'LW', 'LYB', 'LYV', 'MA', 'MAA', 'MAR', 'MAS', 'MCD', 'MCHP', 'MCK',
    'MCO', 'MDLZ', 'MDT', 'MET', 'META', 'MGM', 'MHK', 'MKC', 'MKTX', 'MLM',
    'MMC', 'MMM', 'MNST', 'MO', 'MOH', 'MOS', 'MPC', 'MPWR', 'MRK', 'MRNA',
    'MRO', 'MS', 'MSCI', 'MSFT', 'MSI', 'MTB', 'MTCH', 'MTD', 'MU', 'NCLH',
    'NDAQ', 'NDSN', 'NEE', 'NEM', 'NFLX', 'NI', 'NKE', 'NOC', 'NOW', 'NRG',
    'NSC', 'NTAP', 'NTRS', 'NUE', 'NVDA', 'NVR', 'NWL', 'NWS', 'NWSA', 'NXPI',
    'O', 'ODFL', 'OGN', 'OKE', 'OMC', 'ON', 'ORCL', 'ORLY', 'OTIS', 'OXY',
    'PARA', 'PAYC', 'PAYX', 'PCAR', 'PCG', 'PEAK', 'PEG', 'PEP', 'PFE', 'PFG',
    'PG', 'PGR', 'PH', 'PHM', 'PKG', 'PKI', 'PLD', 'PM', 'PNC', 'PNR', 'PNW',
    'POOL', 'PPG', 'PPL', 'PRU', 'PSA', 'PSX', 'PTC', 'PWR', 'PXD', 'PYPL',
    'QCOM', 'QRVO', 'RCL', 'RE', 'REG', 'REGN', 'RF', 'RHI', 'RJF', 'RL',
    'RMD', 'ROK', 'ROL', 'ROP', 'ROST', 'RSG', 'RTX', 'SBAC', 'SBNY', 'SBUX',
    'SCHW', 'SEDG', 'SEE', 'SHW', 'SIVB', 'SJM', 'SLB', 'SNA', 'SNPS', 'SO',
    'SPG', 'SPGI', 'SRE', 'STE', 'STLD', 'STT', 'STX', 'STZ', 'SWK', 'SWKS',
    'SYF', 'SYK', 'SYY', 'T', 'TAP', 'TDG', 'TDY', 'TECH', 'TEL', 'TER', 'TFC',
    'TFX', 'TGT', 'TJX', 'TMO', 'TMUS', 'TPR', 'TRGP', 'TRMB', 'TROW', 'TRV',
    'TSCO', 'TSLA', 'TSN', 'TT', 'TTWO', 'TXN', 'TXT', 'TYL', 'UAL', 'UDR',
    'UHS', 'ULTA', 'UNH', 'UNP', 'UPS', 'URI', 'USB', 'V', 'VFC', 'VICI',
    'VLO', 'VMC', 'VNO', 'VRSK', 'VRSN', 'VRTX', 'VTR', 'VTRS', 'VZ', 'WAB',
    'WAT', 'WBA', 'WBD', 'WDC', 'WEC', 'WELL', 'WFC', 'WHR', 'WM', 'WMB',
    'WMT', 'WRB', 'WRK', 'WST', 'WTW', 'WY', 'WYNN', 'XEL', 'XOM', 'XRAY',
    'XYL', 'YUM', 'ZBH', 'ZBRA', 'ZION', 'ZTS')

# old stock symbols who got merged, renamed, removed:
SP500old = ('FB', 'PVH')

# https://en.wikipedia.org/wiki/NASDAQ-100
NASDAQ100 = ('ATVI', 'ADBE', 'ADP', 'ABNB', 'ALGN', 'GOOGL', 'GOOG', 'AMZN', 'AMD',
    'AEP', 'AMGN', 'ADI', 'ANSS', 'AAPL', 'AMAT', 'ASML', 'AZN', 'TEAM',
    'ADSK', 'BKR', 'BIIB', 'BKNG', 'AVGO', 'CDNS', 'CHTR', 'CTAS', 'CSCO',
    'CTSH', 'CMCSA', 'CEG', 'CPRT', 'CSGP', 'COST', 'CRWD', 'CSX', 'DDOG',
    'DXCM', 'FANG', 'DLTR', 'EBAY', 'EA', 'ENPH', 'EXC', 'FAST', 'FISV',
    'FTNT', 'GILD', 'GFS', 'HON', 'IDXX', 'ILMN', 'INTC', 'INTU', 'ISRG', 'JD',
    'KDP', 'KLAC', 'KHC', 'LRCX', 'LCID', 'LULU', 'MAR', 'MRVL', 'MELI',
    'META', 'MCHP', 'MU', 'MSFT', 'MRNA', 'MDLZ', 'MNST', 'NFLX', 'NVDA',
    'NXPI', 'ORLY', 'ODFL', 'PCAR', 'PANW', 'PAYX', 'PYPL', 'PEP', 'PDD',
    'QCOM', 'REGN', 'RIVN', 'ROST', 'SGEN', 'SIRI', 'SBUX', 'SNPS', 'TMUS',
    'TSLA', 'TXN', 'VRSK', 'VRTX', 'WBA', 'WBD', 'WDAY', 'XEL', 'ZM', 'ZS')

REITS = ('ARE', 'AMT', 'AVB', 'BXP', 'CPT', 'CBRE', 'CCI', 'DLR', 'DRE', 'EQUIX',
    'EQR', 'ESS', 'EXR', 'FRT', 'PEAK', 'HST', 'IRM', 'KIM', 'MAA', 'PLD',
    'PSA', 'O', 'REG', 'SBAC', 'SPG', 'UDR', 'VTR', 'VICI', 'VNO', 'WELL', 'WY')

# Read all companies of the SP500 from wikipedia.
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
    # XXX print REITS: df['GICS Sector'] == 'Real Estate'

def read_nasdaq100():
    table = pandas.read_html('https://en.wikipedia.org/wiki/NASDAQ-100')
    df = table[4]
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
def is_stock(symbol, tsubcode):
    # Crypto assets like BTC/USD or ETH/USD:
    if symbol[-4:] == '/USD':
        return AssetType.Crypto
    #if symbol in ('SPY','IWM','QQQ'):
    #    return AssetType.AktienFond
    # Well known ETFs:
    if symbol in ('DIA','DXJ','EEM','EFA','EFA','EWW','EWZ','FEZ','FXB','FXE','FXI',
        'GDX','GDXJ','IWM','IYR','KRE','OIH','QQQ','TQQQ',
        'RSX','SMH','SPY','NOBL','UNG','XBI','XHB','XLB',
        'XLE','XLF','XLI','XLK','XLP','XLU','XLV','XME','XOP','XRT','XLRE'):
        return AssetType.OtherStock # AktienFond
    # Just an example, unfortunately EQQQ cannot be traded with Tastyworks:
    if symbol in ('EQQQ',):
        return AssetType.AktienFond
    if symbol in ('TLT','HYG','IEF','GLD','SLV','VXX','UNG','USO'):
        return AssetType.OtherStock
    # Well known individual stock names:
    if (symbol in SP500 or symbol in SP500old or symbol in NASDAQ100) and symbol not in REITS:
        return AssetType.IndStock
    if symbol.startswith('/'):
        if tsubcode not in ('Buy', 'Sell', 'Futures Settlement'):
            raise ValueError(f'Unknown subcode: {tsubcode}')
        return AssetType.Future
    # The conservative way is to throw an exception if we are not sure.
    if not assume_stock:
        raise ValueError(f'No idea if this is a stock: {symbol}\n' +
            'Use the option --assume-individual-stock to assume individual stock ' +
            'for all unknown symbols.')
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
def fifo_add(fifos, quantity, price, price_usd, asset, date=None, tax_free=False, debug=False):
    prevyear = prev_year(date)
    (pnl, pnl_notax) = (.0, .0)
    if quantity == 0:
        return (pnl, pnl_notax)
    if debug:
        #print_fifos(fifos)
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
            p = quantity * (price - fifo[0][0])
            if date is None or \
                (fifo[0][3] > prevyear and quantity < 0 and
                not fifo[0][4] and not tax_free):
                pnl -= p
            else:
                pnl_notax -= p
            fifo[0][2] += quantity
            if fifo[0][2] == 0:
                fifo.popleft()
                if len(fifo) == 0:
                    del fifos[asset]
            return (pnl, pnl_notax)
        # Remove the oldest FIFO entry and continue
        # the loop for further entries (or add the
        # remaining entries into the FIFO).
        p = fifo[0][2] * (price - fifo[0][0])
        if date is None or \
            (fifo[0][3] > prevyear and quantity < 0 and
            not fifo[0][4] and not tax_free):
            pnl += p
        else:
            pnl_notax += p
        quantity += fifo[0][2]
        fifo.popleft()
    # Just add this to the FIFO queue:
    fifo.append([price, price_usd, quantity, date, tax_free])
    return (pnl, pnl_notax)

# Check if the first entry in the FIFO
# is 'long' the underlying or 'short'.
def fifos_islong(fifos, asset):
    return fifos[asset][0][2] > 0

def fifos_sum_usd(fifos):
    sum_usd = .0
    for fifo in fifos:
        if fifo != 'account-usd':
            #for (price, price_usd, quantity, date, tax_free) in fifos[fifo]:
            for (_, price_usd, quantity, _, _) in fifos[fifo]:
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

#def print_fifos(fifos):
#    print('open positions:')
#    for fifo in fifos:
#        print(fifo, fifos[fifo])

# account-usd should always be the same as total together with
# EURUSD conversion data. So just a sanity check:
def check_total(fifos, total):
    #for (price, price_usd, quantity, date, tax_free) in fifos['account-usd']:
    for (_, _, quantity, _, _) in fifos['account-usd']:
        total -= quantity / 10000
    if abs(total) > 0.004:
        print(total)
        raise

# Graphical output of some summary data:
# How to change date-format output with pandas:
# https://stackoverflow.com/questions/30133280/pandas-bar-plot-changes-date-format
def show_plt(df):
    import matplotlib.pyplot as plt

    df2 = df.copy()
    for i in ('Net-Total', 'GuV', 'USD-Gewinne'):
        df2[i] = pandas.to_numeric(df2[i]) # df2[i].astype(float)
    df2['Datum/Zeit'] = pandas.to_datetime(df2['Datum/Zeit'])
    df2.set_index('Datum/Zeit', inplace=True)

    monthly_totals = df2.resample('MS').sum()
    monthly_last = df2.resample('MS').last() # .ohlc() .mean()
    monthly_min = monthly_last['Net-Total'].min() * 0.9
    date_monthly = [x.strftime('%Y-%m') for x in monthly_totals.index]
    ax = monthly_totals.plot(kind='bar', y='GuV', title='Monthly PnL Summary')
    ax.set(xlabel='Date', ylabel='PnL')
    plt.subplots_adjust(bottom=0.2)
    ax.set_xticklabels(date_monthly)
    ax = monthly_totals.plot(kind='bar', y='USD-Gewinne', title='Monthly USD Gains')
    ax.set(xlabel='Date', ylabel='USD Gains')
    plt.subplots_adjust(bottom=0.2)
    ax.set_xticklabels(date_monthly)
    ax = monthly_last.plot(kind='bar', y='Net-Total', title='Monthly Net Total')
    ax.set(xlabel='Date', ylabel='Net-Total')
    plt.subplots_adjust(bottom=0.2)
    ax.set_xticklabels(date_monthly)
    plt.ylim(bottom=monthly_min)

    quarterly_totals = df2.resample('QS').sum()
    quarterly_last = df2.resample('QS').last() # .ohlc() .mean()
    quarterly_min = quarterly_last['Net-Total'].min() * 0.9
    date_quarterly = [x.strftime('%Y-%m') for x in quarterly_totals.index]
    ax = quarterly_totals.plot(kind='bar', y='GuV', title='Quarterly PnL Summary')
    ax.set(xlabel='Date', ylabel='PnL')
    plt.subplots_adjust(bottom=0.2)
    ax.set_xticklabels(date_quarterly)
    ax = quarterly_totals.plot(kind='bar', y='USD-Gewinne', title='Quarterly USD Gains')
    ax.set(xlabel='Date', ylabel='USD Gains')
    plt.subplots_adjust(bottom=0.2)
    ax.set_xticklabels(date_quarterly)
    ax = quarterly_last.plot(kind='bar', y='Net-Total', title='Quarterly Net Total')
    ax.set(xlabel='Date', ylabel='Net-Total')
    plt.subplots_adjust(bottom=0.2)
    ax.set_xticklabels(date_quarterly)
    plt.ylim(bottom=quarterly_min)

    #plt.yscale('log')

    plt.show()

# Append "row" into pandas DataFrame "df".
def df_append_row(df, row):
    #df = df.append(pandas.Series(row), ignore_index=True)
    df.loc[len(df)] = row
    #df = df.sort_index().reset_index(drop=True)
    return df

# Take all transactions and create summaries for differnet
# trading classes.
def get_summary(new_wk, tax_output, min_year, max_year):
    # generate new (empty) pandas dataframe:
    if tax_output:
        min_year = max_year = int(tax_output)
    years = list(range(min_year, max_year + 1))
    years_total = years + ['total']
    index = ('Einzahlungen', 'Auszahlungen', 'Brokergebühren',
        'Alle Gebühren in USD', 'Alle Gebühren in Euro',
        'Währungsgewinne USD', 'Währungsgewinne USD (steuerfrei)',
        'Währungsgewinne USD Gesamt',
        'Krypto-Gewinne', 'Krypto-Verluste',
        'Anlage SO', 'Anlage SO Steuerbetrag', 'Anlage SO Verlustvortrag',
        'Investmentfondsgewinne', 'Investmentfondsverluste',
        'Anlage KAP-INV',
        'Aktiengewinne (Z20)', 'Aktienverluste (Z23)', 'Aktien Gesamt',
        'Aktien Steuerbetrag', 'Aktien Verlustvortrag',
        'Sonstige Gewinne', 'Sonstige Verluste', 'Sonstige Gesamt',
        'Stillhalter-Gewinne', 'Stillhalter-Verluste', 'Stillhalter Gesamt',
        'Durchschnitt behaltene Prämien pro Tag',
        'Stillhalter-Gewinne Calls (FIFO)', 'Stillhalter-Verluste Calls (FIFO)',
        'Stillhalter Calls Gesamt (FIFO)',
        'Stillhalter-Gewinne Puts (FIFO)', 'Stillhalter-Verluste Puts (FIFO)',
        'Stillhalter Puts Gesamt (FIFO)',
        'Stillhalter-Gewinne (FIFO)', 'Stillhalter-Verluste (FIFO)',
        'Stillhalter Gesamt (FIFO)',
        'Long-Optionen-Gewinne', 'Long-Optionen-Verluste',
        'Long-Optionen Gesamt',
        'Future-Gewinne', 'Future-Verluste', 'Future Gesamt',
        'zusätzliche Ordergebühren',
        'Dividenden', 'bezahlte Dividenden', 'Quellensteuer (Z41)',
        'Zinseinnahmen', 'Zinsausgaben', 'Zinsen Gesamt',
        'Z19 Ausländische Kapitalerträge',
        'Z21 Termingeschäftsgewinne+Stillhalter',
        'Z24 Termingeschäftsverluste',
        'KAP+KAP-INV', 'KAP+KAP-INV KErSt+Soli', 'KAP+KAP-INV Verlustvortrag',
        'Cash Balance USD', 'Net Liquidating Value')
    data = []
    for _ in index:
        data.append([.0] * len(years_total))
    stats = pandas.DataFrame(data, columns=years_total, index=index)
    # check all transactions and record summary data per year:
    for i in new_wk.index:
        fees = .0
        cash_total = .0
        net_total = .0
        if tax_output:
            (date, type, pnl, eur_amount, _, _, _, _, callput,
                tax_free, usd_gains, usd_gains_notax) = new_wk.iloc[i]
        else:
            (date, type, pnl, eur_amount, _, fees, _, _, _, _, callput,
                tax_free, usd_gains, usd_gains_notax, _, cash_total, net_total) = new_wk.iloc[i]
        year = int(date[:4])
        # steuerfreie Zahlungen:
        if type in ('Brokergebühr', 'Ordergebühr', 'Zinsen', 'Dividende', 'Quellensteuer'):
            if not bool(tax_free):
                raise ValueError(f'tax_free is False for type "{type}". Full row: "{new_wk.iloc[i]}"')
        # keine steuerfreien Zahlungen:
        if type in ('Ein/Auszahlung', 'Aktie', 'Aktienfond', 'Mischfond',
            'Immobilienfond', 'Sonstiges', 'Long-Option', 'Future'):
            if bool(tax_free):
                raise ValueError(f'tax_free is True for type "{type}". Full row: "{new_wk.iloc[i]}"')
        # Cash und Net Total am Ende vom Jahr feststellen. Letzte Info ist Jahresende:
        stats.loc['Cash Balance USD', year] = float(cash_total)
        stats.loc['Net Liquidating Value', year] = float(net_total)
        # Währungsgewinne:
        stats.loc['Währungsgewinne USD', year] += float(usd_gains)
        stats.loc['Währungsgewinne USD (steuerfrei)', year] += float(usd_gains_notax)
        # sum of all fees paid:
        stats.loc['Alle Gebühren in USD', year] += float(fees)
        stats.loc['Alle Gebühren in Euro', year] += usd2eur(float(fees), date[:10])
        # PNL aufbereiten:
        if pnl == '':
            pnl = .0
        else:
            pnl = float(pnl)
        # Die verschiedenen Zahlungen:
        if type == 'Ein/Auszahlung':
            if float(eur_amount) < .0:
                stats.loc['Auszahlungen', year] += float(eur_amount)
            else:
                stats.loc['Einzahlungen', year] += float(eur_amount)
        elif type == 'Brokergebühr':
            stats.loc['Brokergebühren', year] += pnl
        elif type in ('Aktienfond', 'Mischfond', 'Immobilienfond'):
            if pnl < .0:
                stats.loc['Investmentfondsverluste', year] += pnl
            else:
                stats.loc['Investmentfondsgewinne', year] += pnl
        elif type == 'Krypto':
            if pnl < .0:
                stats.loc['Krypto-Verluste', year] += pnl
            else:
                stats.loc['Krypto-Gewinne', year] += pnl
        elif type == 'Aktie':
            if pnl < .0:
                stats.loc['Aktienverluste (Z23)', year] += pnl
            else:
                stats.loc['Aktiengewinne (Z20)', year] += pnl
        elif type == 'Sonstiges':
            if pnl < .0:
                stats.loc['Sonstige Verluste', year] += pnl
            else:
                stats.loc['Sonstige Gewinne', year] += pnl
        elif type == 'Long-Option':
            if pnl < .0:
                stats.loc['Long-Optionen-Verluste', year] += pnl
            else:
                stats.loc['Long-Optionen-Gewinne', year] += pnl
        elif type == 'Stillhalter-Option':
            if callput == 'C':
                if pnl < .0:
                    stats.loc['Stillhalter-Verluste Calls (FIFO)', year] += pnl
                else:
                    stats.loc['Stillhalter-Gewinne Calls (FIFO)', year] += pnl
            else:
                if pnl < .0:
                    stats.loc['Stillhalter-Verluste Puts (FIFO)', year] += pnl
                else:
                    stats.loc['Stillhalter-Gewinne Puts (FIFO)', year] += pnl
            if pnl < .0:
                stats.loc['Stillhalter-Verluste (FIFO)', year] += pnl
            else:
                stats.loc['Stillhalter-Gewinne (FIFO)', year] += pnl
            eur_amount = float(eur_amount)
            if eur_amount < .0:
                stats.loc['Stillhalter-Verluste', year] += eur_amount
            else:
                stats.loc['Stillhalter-Gewinne', year] += eur_amount
            # Kontrolle: Praemien sind alle steuerfrei, Glattstellungen nicht:
            if not bool(tax_free):
                if eur_amount > .0:
                    raise AssertionError(f'Premium is tax free, assignments not. Found "{eur_amount}" EUR.')
            else:
                if eur_amount < .0:
                    raise AssertionError(f'Premium is tax free, assignments not. Found "{eur_amount}" EUR.')
        elif type == 'Ordergebühr':
            stats.loc['zusätzliche Ordergebühren', year] += pnl
        elif type == 'Dividende':
            if pnl < .0:
                stats.loc['bezahlte Dividenden', year] += pnl
            else:
                stats.loc['Dividenden', year] += pnl
        elif type == 'Quellensteuer':
            stats.loc['Quellensteuer (Z41)', year] += pnl
        elif type == 'Zinsen':
            if pnl < .0:
                stats.loc['Zinsausgaben', year] += pnl
            else:
                stats.loc['Zinseinnahmen', year] += pnl
        elif type == 'Future':
            if pnl < .0:
                stats.loc['Future-Verluste', year] += pnl
            else:
                stats.loc['Future-Gewinne', year] += pnl
        else:
            print(type, i)
            raise
    # add sums of data:
    for year in years:
        stats.loc['Währungsgewinne USD Gesamt', year] = \
            stats.loc['Währungsgewinne USD', year] + stats.loc['Währungsgewinne USD (steuerfrei)', year]
        stats.loc['Aktien Gesamt', year] = aktien_year = \
            stats.loc['Aktiengewinne (Z20)', year] + stats.loc['Aktienverluste (Z23)', year]
        if year > min_year:
            aktien_year += stats.loc['Aktien Verlustvortrag', year - 1]
        aktien_verlust = .0
        if aktien_year < .0:
            aktien_verlust = aktien_year
            aktien_year = .0
        stats.loc['Aktien Steuerbetrag', year] = aktien_year
        stats.loc['Aktien Verlustvortrag', year] = aktien_verlust
        stats.loc['Sonstige Gesamt', year] = \
            stats.loc['Sonstige Gewinne', year] + stats.loc['Sonstige Verluste', year]
        stats.loc['Stillhalter Gesamt', year] = \
            stats.loc['Stillhalter-Gewinne', year] + stats.loc['Stillhalter-Verluste', year]
        stats.loc['Durchschnitt behaltene Prämien pro Tag', year] = stats.loc['Stillhalter Gesamt', year] / 250
        stats.loc['Stillhalter Calls Gesamt (FIFO)', year] = \
            stats.loc['Stillhalter-Gewinne Calls (FIFO)', year] + stats.loc['Stillhalter-Verluste Calls (FIFO)', year]
        stats.loc['Stillhalter Puts Gesamt (FIFO)', year] = \
            stats.loc['Stillhalter-Gewinne Puts (FIFO)', year] + stats.loc['Stillhalter-Verluste Puts (FIFO)', year]
        stats.loc['Stillhalter Gesamt (FIFO)', year] = \
            stats.loc['Stillhalter-Gewinne (FIFO)', year] + stats.loc['Stillhalter-Verluste (FIFO)', year]
        stats.loc['Long-Optionen Gesamt', year] = \
            stats.loc['Long-Optionen-Gewinne', year] + stats.loc['Long-Optionen-Verluste', year]
        stats.loc['Future Gesamt', year] = \
            stats.loc['Future-Gewinne', year] + stats.loc['Future-Verluste', year]
        stats.loc['Zinsen Gesamt', year] = \
            stats.loc['Zinseinnahmen', year] + stats.loc['Zinsausgaben', year]
        stats.loc['Anlage SO', year] = \
            stats.loc['Währungsgewinne USD', year] + \
            stats.loc['Krypto-Gewinne', year] + stats.loc['Krypto-Verluste', year]
        anlage_so = stats.loc['Anlage SO', year]
        if year > min_year:
            anlage_so += stats.loc['Anlage SO Verlustvortrag', year - 1]
        anlage_so_verlust = .0
        if anlage_so < .0:
            anlage_so_verlust = anlage_so
        if anlage_so < 600.0:
            anlage_so = .0
        stats.loc['Anlage SO Steuerbetrag', year] = anlage_so
        stats.loc['Anlage SO Verlustvortrag', year] = anlage_so_verlust
        stats.loc['Anlage KAP-INV', year] = \
            stats.loc['Investmentfondsgewinne', year] + stats.loc['Investmentfondsverluste', year]
        z21 = \
            stats.loc['Long-Optionen-Gewinne', year] + stats.loc['Future-Gewinne', year] + \
            stats.loc['Stillhalter Gesamt', year]
        z24 = \
            stats.loc['Long-Optionen-Verluste', year] + stats.loc['Future-Verluste', year]
        stats.loc['Z19 Ausländische Kapitalerträge', year] = \
            stats.loc['Aktien Gesamt', year] + \
            stats.loc['Sonstige Gesamt', year] + \
            z21 + \
            stats.loc['bezahlte Dividenden', year] + \
            stats.loc['Dividenden', year] + \
            stats.loc['Zinsen Gesamt', year] + \
            stats.loc['zusätzliche Ordergebühren', year]
        if year >= 2021:
            stats.loc['Z21 Termingeschäftsgewinne+Stillhalter', year] = z21
            stats.loc['Z24 Termingeschäftsverluste', year] = z24
        else:
            stats.loc['Z19 Ausländische Kapitalerträge', year] += z24
        stats.loc['KAP+KAP-INV', year] = \
            stats.loc['Z19 Ausländische Kapitalerträge', year] + \
            stats.loc['Anlage KAP-INV', year]
        kerstsoli = stats.loc['KAP+KAP-INV', year] * 0.26375
        if year > min_year:
            kerstsoli += stats.loc['KAP+KAP-INV Verlustvortrag', year - 1]
        verlustvortrag = .0
        if kerstsoli < .0:
            verlustvortrag = kerstsoli
            kerstsoli = .0
        stats.loc['KAP+KAP-INV KErSt+Soli', year] = kerstsoli
        stats.loc['KAP+KAP-INV Verlustvortrag', year] = verlustvortrag
    # limit to two decimal digits
    for i in stats.index:
        for year in years:
            stats.loc[i, year] = float(f'{stats.loc[i, year]:.2f}')
    # sum of data over all years (not useful in some cases):
    for i in stats.index:
        total = .0
        for year in years:
            total += stats.loc[i, year]
        stats.loc[i, 'total'] = float(f'{total:.2f}')
    # XXX Compute unrealized sums of short options.
    return stats

def append_yearly_stats(df, tax_output, stats, min_year, max_year):
    end = [''] * 5
    years = list(range(min_year, max_year + 1))
    if tax_output:
        end = []
        years = [int(tax_output)]
    for year in years:
        df = df_append_row(df, ['', '', '', '', '', '', '', '', '', '', '', ''] + end)
        df = df_append_row(df, ['', '', '', '', '', '', '', '', '', '', '', ''] + end)
        df = df_append_row(df, [f'Tastyworks Kapitalflussrechnung {year}', '', '', '', '', '', '', '', '', '', '', ''] + end)
        df = df_append_row(df, ['', '', '', '', '', '', '', '', '', '', '', ''] + end)
        for i in stats.index:
            # XXX enable these again if data is complete also for yearly stats:
            if tax_output and i in ('Cash Balance USD', 'Net Liquidating Value', 'Alle Gebühren in USD', 'Alle Gebühren in Euro'):
                continue
            if i in ('Alle Gebühren in USD', 'Cash Balance USD', 'Net Liquidating Value'):
                df = df_append_row(df, [i, '', '', '', '', '', stats.loc[i, year], 'USD', '', '', '', ''] + end)
            else:
                df = df_append_row(df, [i, '', '', '', '', '', stats.loc[i, year], 'Euro', '', '', '', ''] + end)
    return df

# XXX hack for future multiples
# check https://tastyworks.freshdesk.com/support/solutions/articles/43000435192
# /GC and /MCL are not needed, these are the default multipliers
mul_dict = {
    # SP500/Nasdaq/Russel2000:
    '/ES': 50.0, '/MES': 5.0, '/NQ': 20.0, '/MNQ': 2.0, '/RTY': 50.0, '/M2K': 5.0,
    # silver and gold:
    '/GC': 100.0, '/MGC': 10.0, '/SI': 5000.0, '/SIL': 1000.0,
    # oil and gas:
    '/CL': 1000.0, '/MCL': 100.0, '/QM': 500.0, '/NG': 10000.0,
    # bitcoin:
    '/BTC': 5.0, '/MBT': .1,
    # interest rates:
    '/ZT': 2000.0, '/ZF': 1000.0, '/ZN': 1000.0, '/ZB': 1000.0, '/UB': 1000.0,
    # currencies:
    '/6E': 125000.0,
    # corn:
    '/ZW': 50.0, '/ZS': 50.0, '/ZC': 50.0,
}

def get_multiplier(asset):
    if asset[:4] in mul_dict:
        return mul_dict[asset[:4]]
    if asset[:3] in mul_dict:
        return mul_dict[asset[:3]]
    return 100.0

def check(all_wk, output_summary, output_csv, output_excel, tax_output, show, verbose, debug):
    if len(all_wk) == 1:
        wk = all_wk[0]
    else:
        wk = pandas.concat(all_wk)
        wk.sort_values(by=['Date/Time',], ascending=False, inplace=True)
        wk.reset_index(drop=True, inplace=True)
    splits = {}               # save data for stock/option splits
    fifos = {}
    cash_total = .0           # account cash total
    cur_year = None
    (min_year, max_year) = (0, 0)
    prev_datetime = None
    check_account_ref = None
    new_wk = []
    for i in reversed(wk.index):
        # Date/Time,Transaction Code,Transaction Subcode,Symbol,Buy/Sell,Open/Close,\
        #   Quantity,Expiration Date,Strike,Call/Put,Price,Fees,Amount,Description,\
        #   Account Reference
        if debug:
            print(wk.iloc[i].to_string())
        (datetime, tcode, tsubcode, symbol, buysell, openclose, quantity, expire, strike,
            callput, price, fees, amount, description, account_ref) = wk.iloc[i]
        if str(datetime)[16:] != ':00': # minimum output is minutes, seconds are 00 here
            raise
        datetime = str(datetime)[:16]
        if prev_datetime is not None and prev_datetime > datetime:
            raise
        prev_datetime = datetime
        date = datetime[:10] # year-month-day but no time
        cur_year = datetime[:4]
        if int(cur_year) > max_year:
            max_year = int(cur_year)
        if int(cur_year) < min_year or min_year == 0:
            min_year = int(cur_year)
        check_tcode(tcode, tsubcode, description)
        check_param(buysell, openclose, callput)
        if check_account_ref is None:
            check_account_ref = account_ref
        if len(all_wk) == 1 and account_ref != check_account_ref: # check if this does not change over time
            raise
        (amount, fees) = (float(amount), float(fees))
        # option/stock splits are tax neutral, so zero out amount/fees for it:
        if tcode == 'Receive Deliver' and tsubcode in ('Forward Split', 'Reverse Split'):
            (amount, fees) = (.0, .0)
        conv_usd = get_eurusd(date)
        cash_total += amount - fees
        eur_amount = usd2eur(amount - fees, date)
        # look at currency conversion gains:
        tax_free = False
        if tsubcode in ('Credit Interest', 'Debit Interest', 'Dividend',
            'Fee', 'Balance Adjustment', 'Special Dividend'):
            tax_free = True
        if tsubcode == 'Deposit':
            if description != 'ACH DEPOSIT':
                tax_free = True
        if tsubcode == 'Withdrawal' and (not isnan(symbol) or description[:5] == 'FROM '):
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
        if False:
            # Do not distinguish between price/amount and fees (which are alway tax free)
            # for currency gains:
            (usd_gains, usd_gains_notax) = fifo_add(fifos, int((amount - fees) * 10000),
                1 / conv_usd, 1, 'account-usd', date, tax_free)
            (usd_gains, usd_gains_notax) = (usd_gains / 10000.0, usd_gains_notax / 10000.0)
        else:
            (usd_gains, usd_gains_notax) = fifo_add(fifos, int(amount * 10000),
                1 / conv_usd, 1, 'account-usd', date, tax_free)
            (usd_gains, usd_gains_notax) = (usd_gains / 10000.0, usd_gains_notax / 10000.0)
            (usd_gains1, usd_gains_notax1) = fifo_add(fifos, int((- fees) * 10000),
                1 / conv_usd, 1, 'account-usd', date, True)
            (usd_gains1, usd_gains_notax1) = (usd_gains1 / 10000.0, usd_gains_notax1 / 10000.0)
            (usd_gains, usd_gains_notax) = (usd_gains + usd_gains1, usd_gains_notax + usd_gains_notax1)

        asset = ''
        newdescription = ''

        if isnan(quantity):
            quantity = 1
        else:
            if tcode == 'Receive Deliver' and tsubcode in ('Forward Split', 'Reverse Split'):
                pass # splits might have further data, not quantity
            elif int(quantity) != quantity:
                # Hardcode AssetType.Crypto here again:
                if symbol[-4:] != '/USD':
                    raise
            else:
                quantity = int(quantity)

        if isnan(price):
            price = .0
        if price < .0:
            raise ValueError(f'Price must be positive, but is {price}')

        if tcode == 'Money Movement':
            local_pnl = f'{eur_amount:.4f}'
            if tsubcode != 'Transfer' and fees != .0:
                raise ValueError('Money Movement with fees')
            if tsubcode == 'Transfer' or (tsubcode == 'Deposit' and description == 'ACH DEPOSIT'):
                local_pnl = ''
                asset = 'transfer'
                newdescription = description
                asset_type = AssetType.Transfer
            elif tsubcode in ('Deposit', 'Credit Interest', 'Debit Interest'):
                if isnan(symbol):
                    asset = 'interest'
                    asset_type = AssetType.Interest
                    if description != 'INTEREST ON CREDIT BALANCE':
                        newdescription = description
                else:
                    if amount > .0:
                        asset = f'dividends for {symbol}'
                        asset_type = AssetType.Dividend
                    else:
                        asset = f'withholding tax for {symbol}'
                        asset_type = AssetType.WithholdingTax
                    newdescription = description
            elif tsubcode == 'Balance Adjustment':
                asset = 'balance adjustment'
                asset_type = AssetType.OrderPayments
            elif tsubcode == 'Fee':
                if description == 'INTL WIRE FEE':
                    local_pnl = ''
                    asset = 'fee'
                    asset_type = AssetType.Fee
                    newdescription = description
                else:
                    # XXX In my case: stock borrow fee:
                    asset = f'stock borrow fees for {symbol}'
                    asset_type = AssetType.Interest
                    newdescription = description
                    if amount >= .0:
                        raise
            elif tsubcode == 'Withdrawal':
                if not isnan(symbol):
                    # XXX In my case: dividends paid for short stock:
                    asset = f'dividends paid for {symbol}'
                    asset_type = AssetType.Dividend
                    newdescription = description
                    if amount >= .0:
                        raise
                else:
                    if description[:5] == 'FROM ':
                        asset = 'interest'
                        asset_type = AssetType.Interest
                        if description != 'INTEREST ON CREDIT BALANCE':
                            newdescription = description
                    else:
                        # account deposit/withdrawal
                        local_pnl = ''
                        asset = 'transfer'
                        asset_type = AssetType.Transfer
                        newdescription = description
            elif tsubcode == 'Dividend':
                if amount > .0:
                    asset = f'dividends for {symbol}'
                    asset_type = AssetType.Dividend
                else:
                    asset = f'withholding tax for {symbol}'
                    asset_type = AssetType.WithholdingTax
                newdescription = description
            elif tsubcode == 'Mark to Market':
                asset = f'mark-to-market for {symbol}'
                asset_type = AssetType.Future
                newdescription = description
        elif tcode == 'Receive Deliver' and tsubcode in ('Forward Split', 'Reverse Split'):
            # XXX: We might check that the two relevant entries have the same data for 'amount'.
            x = symbol + '-' + date
            # quantity for splits seems to be more like strike price and how it changes.
            # We use it to calculate the split ration / reverse ratio.
            if (tsubcode == 'Forward Split' and str(buysell) == 'Sell') or \
               (tsubcode == 'Reverse Split' and str(buysell) == 'Buy'):
                splits[x] = quantity
            else:
                oldquantity = splits[x]
                ratio = quantity / oldquantity
                if int(ratio) == ratio:
                    ratio = int(ratio)
                #print(symbol, quantity, oldquantity, ratio)
                fifos_split(fifos, symbol, ratio)
        elif tcode == 'Receive Deliver' and tsubcode in ('Exercise', 'Assignment') and symbol == 'SPX':
            # SPX Options already have a "Cash Settled Exercise/Assignment" tsubcode that handels all
            # trade relevant data. So we just delete this Exercise/Assignment line altogether.
            # XXX Add a check there is no relevant transaction data included here.
            pass
        else:
            asset = symbol
            if not isnan(expire):
                expire = pydatetime.datetime.strptime(expire, '%m/%d/%Y').strftime('%y-%m-%d')
                price *= get_multiplier(asset)
                if int(strike) == strike: # convert to integer for full numbers
                    strike = int(strike)
                asset = f'{symbol} {callput}{strike} {expire}'
                asset_type = AssetType.LongOption
                if not isnan(expire) and ((str(buysell) == 'Sell' and str(openclose) == 'Open') or
                    (str(buysell) == 'Buy' and str(openclose) == 'Close') or
                    (tsubcode in ('Expiration', 'Exercise', 'Assignment', 'Cash Settled Assignment', 'Cash Settled Exercise') and not fifos_islong(fifos, asset))):
                    asset_type = AssetType.ShortOption
            else:
                asset_type = is_stock(symbol, tsubcode)
            # 'buysell' is not set correctly for 'Expiration'/'Exercise'/'Assignment' entries,
            # so we look into existing positions to check if we are long or short (we cannot
            # be both, so this test should be safe):
            if str(buysell) == 'Sell' or \
                (tsubcode in ('Expiration', 'Exercise', 'Assignment', 'Cash Settled Assignment', 'Cash Settled Exercise') and fifos_islong(fifos, asset)):
                #print('Switching quantity from long to short:')
                quantity = - quantity
            if tsubcode in ('Exercise', 'Assignment', 'Cash Settled Assignment', 'Cash Settled Exercise') and quantity < 0:
                print('Assignment/Exercise for a long option, please move pnl on next line to stock:')
            #if tsubcode in ('Cash Settled Assignment', 'Cash Settled Exercise'):
            #    quantity = 1.0
            check_trade(tsubcode, - (quantity * price), amount, asset_type)
            price_usd = abs((amount - fees) / quantity)
            price = usd2eur(price_usd, date, conv_usd)
            (local_pnl, _) = fifo_add(fifos, quantity, price, price_usd, asset)
            if asset_type == AssetType.IndStock:
                pass
            elif asset_type == AssetType.Future:
                if tsubcode not in ('Buy', 'Sell', 'Futures Settlement'):
                    raise ValueError(f'Unknown tsubcode for future: {tsubcode}')
                # XXX For futures we just add all payments as-is for taxes. We should add them
                # up until final closing instead. This should be changed. ???
                local_pnl = eur_amount
            else:
                if cur_year >= '2018':
                    # Teilfreistellungen: https://www.gesetze-im-internet.de/invstg_2018/__20.html
                    if asset_type == AssetType.AktienFond:
                        local_pnl *= 0.70
                    elif asset_type == AssetType.MischFond:
                        local_pnl *= 0.85
                    elif asset_type == AssetType.ImmobilienFond:
                        local_pnl *= 0.20
            description = ''
            local_pnl = f'{local_pnl:.4f}'

        #check_total(fifos, cash_total)

        net_total = cash_total + fifos_sum_usd(fifos)

        if local_pnl != '':
            local_pnl = f'{float(local_pnl):.2f}'
        if tax_output:
            if datetime[:4] == tax_output:
                new_wk.append([datetime[:10], transaction_type(asset_type), local_pnl,
                        f'{eur_amount:.2f}', f'{amount - fees:.4f}', f'{conv_usd:.4f}',
                        quantity, asset, callput,
                        tax_free, f'{usd_gains:.2f}', f'{usd_gains_notax:.2f}'])
        else:
            new_wk.append([datetime, transaction_type(asset_type), local_pnl,
                f'{eur_amount:.2f}', f'{amount:.4f}', f'{fees:.4f}', f'{conv_usd:.4f}',
                quantity, asset, symbol, callput,
                tax_free, f'{usd_gains:.2f}', f'{usd_gains_notax:.2f}',
                newdescription, f'{cash_total:.2f}', f'{net_total:.2f}'])

    #wk.drop('Account Reference', axis=1, inplace=True)
    if tax_output:
        new_wk = sorted(new_wk, key=lambda x: transaction_order[x[1]])
        new_wk = pandas.DataFrame(new_wk, columns=('Datum', 'Transaktions-Typ', 'GuV',
            'Euro-Preis', 'USD-Preis', 'EurUSD', 'Anzahl', 'Asset', 'callput',
            'Steuerneutral', 'USD-Gewinne', 'USD-Gewinne steuerneutral'))
    else:
        new_wk = pandas.DataFrame(new_wk, columns=('Datum/Zeit', 'Transaktions-Typ', 'GuV',
            'Euro-Preis', 'USD-Preis', 'USD-Gebühren', 'EurUSD', 'Anzahl', 'Asset',
            'Basiswert', 'callput',
            'Steuerneutral', 'USD-Gewinne', 'USD-Gewinne steuerneutral',
            'Beschreibung', 'USD Cash Total', 'Net-Total'))
    stats = get_summary(new_wk, tax_output, min_year, max_year)
    if tax_output:
        stats.drop('total', axis=1, inplace=True)
    print(stats.to_string())
    if output_summary:
        with open(output_summary, 'w', encoding='UTF8') as f:
            stats.to_csv(f)
    if show:
        show_plt(new_wk)
    new_wk = append_yearly_stats(new_wk, tax_output, stats, min_year, max_year)
    new_wk.drop('callput', axis=1, inplace=True)
    if verbose:
        print(new_wk.to_string())
    if output_csv is not None:
        with open(output_csv, 'w', encoding='UTF8') as f:
            new_wk.to_csv(f, index=False)
    if output_excel is not None:
        with pandas.ExcelWriter(output_excel) as f:
            new_wk.to_excel(f, index=False, sheet_name='Tastyworks Report') #, engine='xlsxwriter')

# check if the first line of the csv line contains the correct header:
def check_csv(csv_file):
    with open(csv_file, encoding='UTF8') as f:
        content = f.readlines()
    if len(content) < 1 or content[0] != 'Date/Time,Transaction Code,' + \
        'Transaction Subcode,Symbol,Buy/Sell,Open/Close,Quantity,' + \
        'Expiration Date,Strike,Call/Put,Price,Fees,Amount,Description,' + \
        'Account Reference\n':
        print('ERROR: Wrong first line in csv file.')
        sys.exit(1)

def usage():
    print('tw-pnl.py [--assume-individual-stock][--tax-output=2021][--usd]' +
        '[--summary=summary.csv][--output-csv=test.csv][--output-excel=test.xlsx][--help]' +
        '[--verbose][--debug][--show] *.csv')

def main(argv):
    import getopt
    #print_sp500()
    #print_nasdaq100()
    #sys.exit(0)
    verbose = False
    debug = False
    output_summary = None
    output_csv = None
    output_excel = None
    tax_output = None
    #tax_output = '2021'
    show = False
    try:
        opts, args = getopt.getopt(argv, 'dhuv', ['assume-individual-stock',
            'help', 'summary=', 'output-csv=', 'output-excel=',
            'show', 'tax-output=', 'usd', 'verbose', 'debug'])
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
        elif opt == '--output-csv':
            output_csv = arg
        elif opt == '--output-excel':
            output_excel = arg
        elif opt in ('-u', '--usd'):
            global convert_currency
            convert_currency = False
        elif opt in ('-v', '--verbose'):
            verbose = True
        elif opt in ('-d', '--debug'):
            debug = True
        elif opt == '--show':
            show = True
        elif opt == '--summary':
            output_summary = arg
        elif opt == '--tax-output':
            tax_output = arg
    if len(args) == 0:
        usage()
        sys.exit()
    read_eurusd()
    args.reverse()
    all_wk = []
    for csv_file in args:
        check_csv(csv_file)
        all_wk.append(pandas.read_csv(csv_file, parse_dates=['Date/Time']))
    check(all_wk, output_summary, output_csv, output_excel, tax_output, show, verbose, debug)

if __name__ == '__main__':
    main(sys.argv[1:])
