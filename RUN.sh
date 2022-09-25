#!/bin/bash
#
# example on how to generate all tastyworks tax reports
#

# input file from Tastyworks with all transaction history as csv file:
INPUT=transaction_history.csv
#INPUT="../TW-*.csv"

YEARS="2017 2018 2019 2020 2021 2022"
#YEARS="`seq 2017 2022`"

# Additional parameters:
PARAM="--assume-individual-stock"

# If you want to look at graphical output summary:
#SHOW="--show"

# Where to store the output reports:
OUTPUTDIR=tax-reports

mkdir -p $OUTPUTDIR

# tax reports for individual years:
for year in $YEARS ; do
  python3 tw-pnl.py $PARAM --tax-output=$year --output-csv=$OUTPUTDIR/tax-$year.csv $INPUT
done

# One big summary report for all years as csv and txt.
# Also one big csv file with all transactions:
python3 tw-pnl.py $PARAM $SHOW --summary=$OUTPUTDIR/tax-summary.csv --output-csv=$OUTPUTDIR/tax-all.csv $INPUT > $OUTPUTDIR/tax-summary.txt

