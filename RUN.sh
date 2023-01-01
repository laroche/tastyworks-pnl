#!/bin/bash
#
# example on how to generate all tastyworks tax reports
#

# input file from Tastyworks with all transaction history as csv file:
INPUT=transaction_history.csv
#INPUT="../TW-*.csv"

YEARS="2017 2018 2019 2020 2021 2022 2023"
#YEARS="`seq 2017 2023`"

# Additional parameters:
PARAM="--assume-individual-stock"

# If you want to look at graphical output summary:
#SHOW="--show"

# Where to store the output reports:
OUTPUTDIR=tax-reports

# Keep a backup of old generated files?
SAVEOUTPUTDIR=0

# Check parameters:
if test "X$1" = "X--show" ; then
  SHOW="--show"
  shift
fi
if test "X$*" != "X" ; then
  INPUT="$*"
fi

# If no backup exists, rename existing output data dir as backup dir:
if test $SAVEOUTPUTDIR = 1 && ! test -d $OUTPUTDIR.old && test -d $OUTPUTDIR ; then
  mv $OUTPUTDIR $OUTPUTDIR.old
fi

mkdir -p $OUTPUTDIR

# tax reports for individual years:
for year in $YEARS ; do
  python3 tw-pnl.py $PARAM --tax-output=$year --output-csv=$OUTPUTDIR/tax-$year.csv $INPUT
done

# One big summary report for all years as csv and txt.
# Also one big csv file with all transactions:
python3 tw-pnl.py $PARAM $SHOW --summary=$OUTPUTDIR/tax-summary.csv --output-csv=$OUTPUTDIR/tax-all.csv $INPUT > $OUTPUTDIR/tax-summary.txt

if test -d $OUTPUTDIR.old ; then
  diff -urN $OUTPUTDIR.old $OUTPUTDIR
fi

