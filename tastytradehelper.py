import csv
from datetime import datetime, timedelta
from io import StringIO
import os
import pandas
from pandas.api.types import union_categoricals
import urllib.request

class TastytradeHelper:
    _eurusd_rates = {}
    _eurusd_filename = 'eurusd.csv'

    @staticmethod
    def price_from_description(description: str) -> float:
        """
        Extract the price from the transaction description string and return it.
        """
        price = 0
        if len(description) == 0 or not description.startswith('Bought') and not description.startswith('Sold'):
            return price
        
        parts = description.split('@')
        assert len(parts) == 2, f"Expected 2 parts, got {len(parts)}: {parts}"
    
        price = float(parts[-1].strip().replace(',', '').replace('"', ''))
        return price
    
    @staticmethod
    def consolidate_and_sort_transactions(transactions) -> pandas.DataFrame:
        """
        Consolidate the array with DataFrames and sort them descending by date.
        Keep the category columns consistent during concatenation of the dataframes.
        """
        if len(transactions) == 1:
            consolidated_transactions = transactions[0]
        else:
            for col in set.intersection(
                *[
                    set(df.select_dtypes(include='category').columns)
                    for df in transactions
                ]
            ):
                # Generate the union category across dfs for this column
                uc = union_categoricals([df[col] for df in transactions])
                # Change to union category for all dataframes
                for df in transactions:
                     df[col] = pandas.Categorical(df[col].values, categories=uc.categories)
            consolidated_transactions = pandas.concat(transactions, ignore_index=True)
            consolidated_transactions = consolidated_transactions.sort_values(by=['Date/Time',], ascending=False)
            consolidated_transactions = consolidated_transactions.reset_index(drop=True)
        return consolidated_transactions
    
    @staticmethod
    def get_eurusd(date: str) -> float:
        """
        Get the EURUSD exchange rate for the given date.
        """
        real_date = datetime.strptime(date, '%Y-%m-%d')
        while True:
            try:
                rate = TastytradeHelper._eurusd_rates[real_date.strftime('%Y-%m-%d')]
            except KeyError:
                raise ValueError(f'No EUR/USD exchange rate available for date {date}')
            
            if rate is not None:
                return rate
            
            # Try the previous day
            real_date -= timedelta(days=1)
    
    @staticmethod
    def is_legacy_csv(csv_filename: str) -> bool:
        """ Checks the first line of the csv data file if the header fits the legacy or the current format.
        """
        header_legacy = 'Date/Time,Transaction Code,' + \
    			'Transaction Subcode,Symbol,Buy/Sell,Open/Close,Quantity,' + \
				'Expiration Date,Strike,Call/Put,Price,Fees,Amount,Description,' + \
				'Account Reference\n'
        header = 'Date,Type,Sub Type,Action,Symbol,Instrument Type,Description,Value,Quantity,' + \
        		'Average Price,Commissions,Fees,Multiplier,Root Symbol,Underlying Symbol,Expiration Date,' + \
                'Strike Price,Call or Put,Order #,Currency\n'
        with open(csv_filename, encoding='UTF8') as f:
            content = f.readlines(1)
            if content[0] == header_legacy:
                legacy_format = True
            elif content[0] == header:
                legacy_format = False
            else:
                raise ValueError('Wrong first line in csv file. Please download trade history from the Tastytrade app!')
        return legacy_format

    @staticmethod
    def read_transaction_history(csv_filename: str) -> pandas.DataFrame:
        """
        Read the Tastytrade transaction history from a CSV file and return it as a DataFrame.
        """
        csv_string = csv_filename
        if not TastytradeHelper.is_legacy_csv(csv_filename):
            csv_string = StringIO(TastytradeHelper.transform_csv(csv_filename))
        transaction_history = pandas.read_csv(csv_string, parse_dates=['Date/Time'])

        transaction_history['Expiration Date'] = transaction_history['Expiration Date'].astype('object')
        for i in ('Open/Close', 'Buy/Sell', 'Call/Put'):
            #print(wk[i].value_counts(dropna=False))
            transaction_history[i] = transaction_history[i].fillna('').astype('category')
            #print(wk[i].value_counts(dropna=False))
        for i in ('Account Reference', 'Transaction Subcode', 'Transaction Code'):
            #print(wk[i].value_counts(dropna=False))
            transaction_history[i] = transaction_history[i].astype('category')

        return transaction_history
    
    @staticmethod
    def transform_csv(csv_filename: str) -> str:
        """
        Transform the CSV file data from new data format back to the old data format.
        """
        transformed_data = 'Date/Time,Transaction Code,Transaction Subcode,Symbol,Buy/Sell,Open/Close,Quantity,Expiration Date,Strike,Call/Put,Price,Fees,Amount,Description,Account Reference'
        with open(csv_filename, encoding='UTF8') as f:
            reader = csv.reader(f, delimiter=',')
            for row in reader:
                if row[0] == 'Date':
                    continue
                date = datetime.fromisoformat(row[0][:19]).strftime('%m/%d/%Y %H:%M') # Convert ISO date to old date format

                transaction_code = row[1]
                transaction_subcode = row[2]
                action = row[3]
                symbol = row[4]
                if symbol.startswith('.'):  # Remove leading dot from symbol
                    symbol = symbol[1:]

                # Extract buy/sell and open/close from action
                buy_sell = ''
                open_close = ''
                if action.startswith('BUY'):
                    buy_sell = 'Buy'
                elif action.startswith('SELL'):
                    buy_sell = 'Sell'
                if action.endswith('TO_OPEN'):
                    open_close = 'Open'
                elif action.endswith('TO_CLOSE'):
                    open_close = 'Close'

                quantity = row[8]

                # Transform the expiration date
                if row[15] != '':
                    expiration_date = datetime.strptime(row[15], '%m/%d/%y').strftime('%m/%d/%Y')
                else:
                    expiration_date = 'n/a'

                strike = row[16]

                if len(row[17]) > 0:
                    call_put = row[17][0]
                else:
                    call_put = ''

                description = row[6]
                price = TastytradeHelper.price_from_description(description)

                fees = float(row[11])
                try:
                    commission = float(row[10])
                    fees += commission
                except ValueError:
                    pass
                fees = abs(fees) # Fees are always positive in the old format

                amount = row[7].replace(',', '')

                account_refrerence = 'account'

                transformed_data += f'\n{date},{transaction_code},{transaction_subcode},{symbol},{buy_sell},{open_close},{quantity},{expiration_date},{strike},{call_put},{price},{fees},{amount},{description},{account_refrerence}'

            return transformed_data

    @staticmethod
    def _read_eurusd_rates():
        """
        Read the EURUSD exchange rates from the CSV file eurusd.csv.
        """
        TastytradeHelper._eurusd_rates = {}
        if os.path.exists(TastytradeHelper._eurusd_filename):
            with open(TastytradeHelper._eurusd_filename, encoding='UTF8') as csv_file:
                reader = csv.reader(csv_file)
                for _ in range(5):
                    next(reader)
                for (date, usd, _) in reader:
                    if date != '' and usd != '.':
                        TastytradeHelper._eurusd_rates[date] = float(usd)
                    else:
                        TastytradeHelper._eurusd_rates[date] = None

    @staticmethod
    def update_eurusd(recent_date: datetime.date) -> bool:
        """
        Checks if the EURUSD exchange rates csv file is up to date and updates the data if necessary.
        """
        eurusd_url: str = 'https://www.bundesbank.de/statistic-rmi/StatisticDownload?tsId=BBEX3.D.USD.EUR.BB.AC.000&its_csvFormat=en&its_fileFormat=csv&mode=its&its_from=2010'
                
        # Try to open the local eurusd.csv file and check the last date in the file.
        TastytradeHelper._read_eurusd_rates()
        # access the last entry in the dictionary
        read_date = ''
        index = 0
        while read_date == '':
            index -= 1
            read_date = list(TastytradeHelper._eurusd_rates.keys())[index]
        
        last_rate_date = datetime.strptime(read_date, '%Y-%m-%d').date()
        if last_rate_date < recent_date:
            # Download the latest EURUSD exchange rates from the Bundesbank
            # and append them to the local eurusd.csv file.
            try:
                urllib.request.urlretrieve(eurusd_url, TastytradeHelper._eurusd_filename)
            except urllib.error.URLError as exc:
                return False
            # Read the updated exchange rates again
            TastytradeHelper._read_eurusd_rates()
        return True
    