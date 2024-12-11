#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#        rabo2ofx.py
#
#        Copyright 2015,2016,2018 Guus Bonnema <gbonnema@xs4all.nl>
#
#        Based on source from ing2ofx.py by Arie van Dobben for ING (GPL v 3)
#            Copyright 2013 Arie van Dobben <avandobben@gmail.com>
#
#        This program is free software: you can redistribute it and/or modify
#        it under the terms of the GNU General Public License as published by
#        the Free Software Foundation, either version 3 of the License, or
#        (at your option) any later version.
#
#        This program is distributed in the hope that it will be useful,
#        but WITHOUT ANY WARRANTY; without even the implied warranty of
#        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#        GNU General Public License for more details.
#
#        You should have received a copy of the GNU General Public License
#        along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# 
# 2021-11-24 guus adding option to override date_posted for processing date in stead of interest date
#                 adding a simple counter of overrides per account
# 2019-08-21 guus adding option for homebank to not skip internal transactions
#                 corrected argument processing
#                 no longer force filename to lowercase.
# 2018-11-xx guus added minor statistics
# 2018-11-11 guus added config files for processing account transfers, independent of files.
# 2018-11-04 guus prevent processing transfers twice provided transactions are in the same file
# 2018-11-03 guus Removed obsolete function
# 2018-11-03 lvdgraaff Removed erroneous double end header in xml output
# 2018-04-07 guus  Adapted to version 1.0 of Rabobank csv files (download from Rabobank)
#                  New field layout and first row is header row
# 2016-01-02 guus  Adapted to undocumented version of Rabobank csv files (exported as .txt files)
# 

"""
The intent of this script is to convert rabo csv files to ofx files. These
csv files you can download when logged in to www.rabo.nl as customer of Rabo.
The intention is to create OFX files for GnuCash (www.gnucash.org) and if requested
for homebank. The difference between GnuCash and HomeBank is that rabo2ofx will
only generate *one* transaction for an internal transfer for GnuCash and 2 transactions
for an internal transfer for HomeBank. HomeBank has the ability to conclude that it
is an internal transfer by matching the two transactions.

This script is adapted from ing2ofx.py by Arie van Dobben (Copyright 2013) which
in turn is based on pb2ofx.pl Copyright 2008, 2009, 2010 Peter Vermaas,
originally found @ http://blog.maashoek.nl/2009/07/gnucash-en-internetbankieren/
which is now dead.

Find the ofx specification at http://www.ofx.net/

== Documentation ==

[nov 2021] On request: 
created an option to override the date posted with the current date of the transaction.
Added a counter per account for number of overrides. 

[aug 2019]
Decided to use HomeBank next to GnuCash. For homebank the program needs to
emit all transactions, irrespective of being internal transfer or not.

[jan 2018]
Since approximately Jan 2018, the Rabo bank changed the layout or the
CSV files. The layout is documented in 
https://www.rabobank.nl/images/format-description-csv-en_29939190.pdf.

[nov 2018]
Added the layout for a config file is an ini format compliant with the python
configparser. The default filename is "config.rabo2ofx.ini". Currently no plans to
change the name through program options.

The configfile contains one section: "[accounts]" with one entry "order=[<list of accountnumbers>].
There will be an example configfile in the distribution so people can use this as a base for their
own config.

== Documentation until 2018 ==
Conversion of RABO bank download csv file (comma separated).
Started from incomplete and old RABO docs. deducted file structure from live
transactions (web + download).

The RABO csv contains all fields separated by comma's and surrounded by double
quotes. The current (sept 2015) csv file contains the following fields:

    Length    type    offset  description
    18        alfanum    0       Accountnumber from downloaded account (IBAN)
    03        alfanum    1       Currency code    (usually EUR)
    08        date       2       The interest date, format: EEYYMMDD
    01        DC         3       The debit / credit code: 'D' or 'C'
    14        amount     4       Transaction amount, format: 9(11).9(2)
    18        alfanum    5       Counter accountnumber, IBAN format
    24        alfanum    6       The name for the counter account number
    08        date       7       The transaction date, format: EEYYMMDD
    02        alfanum    8       Booking code. Currently values are:

    code | description            | OFX 'TXNTYPE'
    -----|------------------------|---------------------
    ac   | acceptgiro             | XFER
    ba   | betaalautomaat         | POS
    bc   | betalen contactloos    | POS
    bg   | bankgiro opdracht      | XFER
    cb   | crediteuren betaling   | XFER
    ck   | chipknip               | POS
    db   | diverse boekingen      | OTHER
    eb   | bedrijven euro-incasso | DIRECTDEBIT
    ei   | euro incasso           | DIRECTDEBIT
    fb   | finbox                 |
    ga   | geldautomaat euro      | ATM
    gb   | geldautomaat vv        | ATM
    id   | ideal                  | PAYMENT
    kh   | kashandeling           | 
    ma   | machtiging             | DIRECTDEBIT
    sb   | salaris betaling       | XFER
    tb   | eigen rekening         | XFER
    sp   | spoedbetaling          |
    CR   | tegoed                 |
    D    | tekort                 |

    The program assigns DEBIT or CREDIT as OFX TXNTYPE for all codes left blank.

    06        alfanum 9           Budgetcode, a free field for budgetting
    32 x 6    alfanum 10 - 15     Description: 6 fields.
                                  For [ba] (betaalautomaat) descr[0] is often
                                  the payee.
    32        alfanum 16          transaction reference
    32        alfanum 17          payee (IncassantID):
                                    often an IBAN number (not necessarily)
    32        alfanum 18          debit authorization code
                                    (Machtigingscode voor incasso)

The last 2 fields are also filled for other than "ma" bookingcode
(for instance for bookingcode "ei").

For bookingcode "db" counter_account_code and counter_account_holder
are not always filled.


"""
import sys
import csv
import re
import argparse
import datetime
import os
import configparser


#
# Version history in a dict to easily present changes
#

MAINTAINERS = {"gbo": "Guus Bonnema"}

HISTORY = {
    "1.0": ("Initial version", "2015-12-30", "gbo"),
    "1.01": ("Correction for description of db: add space between " +
             "name and description.", "2015-12-30", "gbo"),
    "1.02": ("Added sequence to fitid for same amount, same date.",
             "2016-01-02", "gbo"),
    "2.00 dev": ("(in development) CSV format updated to new RABO format (no docs available).",
                 "2018-04-03", "gbo"),
    "2.10": ("Added config to process transfers in a reasonable manner", "2018-11-11", "gbo"),
    "2.11": ("Added minor statistic", "2018-11-14", "gbo"),
    "2.12": ("Added homebank option", "2019-08-21", "gbo"),
    "2.12.1": ("Added minor edits and docs", "2019-08-23", "gbo"),
    "2.13": ("Added OFX booking codes", "2019-08-23", "gbo"),
    "2.14": ("Added override date posted option", "2021-11-24", "gbo"),
    }

VERSION = "2.13"
# Needed for version argument
VERSION_STRING = '%%(prog)s version %s (%s: [%s] %s)' % (VERSION,
                                                         HISTORY[VERSION][2],
                                                         HISTORY[VERSION][1],
                                                         HISTORY[VERSION][0])

""" First parse the command line arguments. """
PARSER = argparse.ArgumentParser(prog='rabo2ofx',
                                 description="""
    The intent of this script is to convert rabo csv files to ofx files. These
    csv files you can download when logged in to www.rabo.nl as customer of Rabo.
    The intention is to create OFX files for GnuCash (www.gucash.org) or HomeBank.
    Remark: HomeBank gets all transactions. GnuCash skips one side of an internal transfer.
                                 """)
PARSER.add_argument('csvfile', help='A csvfile to process')
PARSER.add_argument('--outfile', '-o', dest='outfile',
                    help='Output filename', default=None)
PARSER.add_argument('--directory','-d', dest='dir',
                    help='Directory to store output, default is ./ofx, ofx_hb for HomeBank', default='ofx')
PARSER.add_argument('--homebank', '-H', dest='homebank', action='store_true',
                    help='Generate ofx file for HomeBank application')
PARSER.add_argument('--comma', '-c', dest='dec_comma',
                    help="Convert decimal point to decimal comma, default is decimal_point",
                    action='store_true')
PARSER.add_argument('--version', '-v', action='version',
                    version=VERSION_STRING)
ARGS = PARSER.parse_args()


# ********************************************************************************
# ************** Class CsvFile     ***********************************************
class CsvFile():
    """ Read the csv file into a list intended for ofx"""

    keyAccount = 'acctNr'
    keyCurrency = 'currency'
    keyBIC = 'BIC'
    keySerialNumber = 'serNr'
    keyDate = 'Date'
    keyInterestDate = 'interestDate'
    keyAmount = 'amount'
    keyBalanceAfterTxn = 'balance'
    keyCounterAcctNr = 'counterAcctNr'
    keyCounterAcctName = 'counterAcctName'
    keyCounterPartyName = 'counterPartyName'
    keyInitiatingPartyName = 'initPartyName'
    keyCounterPartyBIC = 'counterPartyBIC'
    keyBookCode = 'bookCode'
    keyBatchId = 'batchId'
    keyTxRef = 'txRef'
    keyMachtigingskenmerk = 'machtigingskenmerk'
    keyIncassantID = 'incassantID'
    keyBetalingsKenmerk = 'betalingskenmerk'
    keyDescr1 = 'descr1'
    keyDescr2 = 'descr2'
    keyDescr3 = 'descr3'
    keyRedenRetour = 'redenRetour'
    keyOriginalAmount = 'oorspronkelijk bedrag'
    keyOriginalCurrency = 'oorspronkelijke munt'
    keyExchangeRate = 'exchangeRate'
    keyAuthCode = 'authCode'

    #Description of book codes for the Rabo
    bookcode = {
        "ac": "acceptgiro",
        "ba": "betaalautomaat",
        "bc": "betalen contactloos",
        "bg": "bankgiro opdracht",
        "cb": "crediteuren betaling",
        "ck": "chipknip",
        "db": "diverse boekingen",
        "eb": "bedrijven euro-incasso",
        "ei": "euro-incasso",
        "fb": "finbox",
        "ga": "geldautomaat euro",
        "gb": "geldautomaat vv",
        "id": "ideal",
        "kh": "kashandeling",
        "ma": "machtiging",
        "sb": "salarisbetaling",
        "tb": "eigen rekening",
        "sp": "spoedbetaling",
        "CR": "tegoed",
        "D": "tekort"
    }

    def __init__(self, overrides):
        self.transactions = list()
        #transnr = 0
        self.fitid = {}

        with open(ARGS.csvfile, 'r', newline='', encoding='iso-8859-1') as csvfile:
            fieldnames = (self.keyAccount, self.keyCurrency, self.keyBIC,
                          self.keySerialNumber, self.keyDate, self.keyInterestDate,
                          self.keyAmount, self.keyBalanceAfterTxn,
                          self.keyCounterAcctNr, self.keyCounterAcctName,
                          self.keyCounterPartyName, self.keyInitiatingPartyName,
                          self.keyCounterPartyBIC, self.keyBookCode,
                          self.keyBatchId, self.keyTxRef,
                          self.keyMachtigingskenmerk, self.keyIncassantID,
                          self.keyBetalingsKenmerk,
                          self.keyDescr1, self.keyDescr2, self.keyDescr3,
                          self.keyRedenRetour,
                          self.keyOriginalAmount, self.keyOriginalCurrency,
                          self.keyExchangeRate
                         )
            #Open the csvfile as a Dictreader
            csvreader = csv.DictReader(csvfile, delimiter=',', quotechar='"',
                                       fieldnames=fieldnames)
            # We have our own fieldnames, so delete the first row containing descriptions
            # Since 1-1-2018 the csv files contain a header row as first line
            linenr = 0
            for row in csvreader:
                linenr = linenr + 1
                if linenr == 1:
                    continue        # skip the first line
                if not row:
                    continue
                ofx_data = self.create_ofx(row, overrides)
                self.transactions.append(ofx_data)

    def create_ofx(self, row, overrides):
        """ Main processor where ofx records are constructed. """
        nr_overrides = 0
        (times_override, account) = self.map_account(row, overrides)
        nr_overrides += times_override
        (times_override, trntype) = self.map_transaction_type(row, overrides)
        nr_overrides += times_override
        (times_override, dtposted) = self.map_date_posted(row, overrides)
        nr_overrides += times_override
        (times_override, trnamt) = self.map_amount(row, overrides)
        nr_overrides += times_override
        # remark: serialnumber is unique per account, but only filled for checking account
        # later savings account will have it filled too.
        fitid = self.map_fitid(account, row[self.keySerialNumber], trnamt, dtposted)
        (times_override, accountto) = self.map_account_to(row, overrides)
        nr_overrides += times_override
        (times_override, name, memo) = self.map_memo_name(row, overrides)
        nr_overrides += times_override

        return {'account': account,
                'trntype': trntype, 'dtposted': dtposted,
                'trnamt': trnamt, 'fitid': fitid,
                'name': name, 'accountto': accountto, 'memo': memo,
                'nr_overrides': nr_overrides}

    def map_account(self, row, overrides):
        """ map account without spaces """
        return (0, row[self.keyAccount].replace(" ", ""))

    def map_transaction_type(self, row, overrides):
        """ map transaction type to debit and credit """
        # Map transaction amount to trntype ('+' = 'DEBIT', '-' || '[\d]' = 'CREDIT')
        if row[self.keyBookCode] == 'ac':
            trntype = 'XFER'
        elif row[self.keyBookCode] == 'ba':
            trntype = 'POS'
        elif row[self.keyBookCode] == 'bc':
            trntype = 'POS'
        elif row[self.keyBookCode] == 'bg':
            trntype = 'XFER'
        elif row[self.keyBookCode] == 'cb':
            trntype = 'XFER'
        elif row[self.keyBookCode] == 'ck':
            trntype = 'POS'
        elif row[self.keyBookCode] == 'db':
            trntype = 'OTHER'
        elif row[self.keyBookCode] == 'eb':
            trntype = 'DIRECTDEBIT'
        elif row[self.keyBookCode] == 'ei':
            trntype = 'DIRECTDEBIT'
        elif row[self.keyBookCode] == 'ga':
            trntype = 'ATM'
        elif row[self.keyBookCode] == 'gb':
            trntype = 'ATM'
        elif row[self.keyBookCode] == 'id':
            trntype = 'PAYMENT'
        elif row[self.keyBookCode] == 'ma':
            trntype = 'DIRECTDEBIT'
        elif row[self.keyBookCode] == 'sb':
            trntype = 'XFER'
        elif row[self.keyBookCode] == 'tb':
            trntype = 'XFER'
        elif row[self.keyAmount].startswith('-'):
            trntype = 'DEBIT'
        else:
            trntype = 'CREDIT'
        return (0, trntype)

    def map_date_posted(self, row, overrides):
        """ map date posted without dashes """
        # The DTPOSTED in ofx is in yyyymmddhhmmss format
        # input is formatted in yyyy-mm-dd
        # needs conversion
        #
        # check override
        nr_overrides = 0
        date = row[self.keyInterestDate]
        if  overrides['force_date_posted'] and date != row[self.keyDate] :
            nr_overrides += 1
            date = row[self.keyDate]
        pattern = re.compile(r"\-")
        date = pattern.sub("", date)
        return (nr_overrides, date)

    def map_amount(self, row, overrides):
        """ map amount replacing comma to point or v.v. """
        amt = row[self.keyAmount]
        # convert to comma or point depending on arguments (default decimal point)
        if ARGS.dec_comma:
            amt = amt.replace(".", ",")
        else:
            amt = amt.replace(",", ".")
        return (0, amt)

    def map_balance(self, row, overrides):
        """ map balance to amount replacing comma to point or v.v. """
        amt = row[self.keyBalanceAfterTxn]
        # convert to comma or point depending on arguments (default decimal point)
        if ARGS.dec_comma:
            amt = amt.replace(".", ",")
        else:
            amt = amt.replace(",", ".")
        return (0, amt)

    def map_fitid(self, account, volgnr, trnamt, dtposted):
        """ Construct Fitid """
        # the FITID is composed of the date and amount
        # plus dcCode
        # Since version 1 account + volgnr is sufficient for checker accounts.
        # for a unique FITID, we add a sequence number per date
        # Warning: don't spread transactions for one date accross import files!
        # Or they will not be processed due to duplicate FITID.
        if float(trnamt) >= 0:
            dc_code = "C"
        else:
            dc_code = "D"
        # before 1st Jan 2018, fitid did not have benefit of volgnr.
        # to keep fitid compliant with history, ignore volgnr if before 2018
        if volgnr and dtposted > "20171231":
            key = account + volgnr
        else:
            key = dtposted \
                      + trnamt.replace(",", "") \
                              .replace(".", "") \
                              .replace("-", "") \
                              .replace("+", "") \
                      + dc_code
        # check if fitid already exists. Normally with 'volgnr' it should not.
        sequence = 0
        if key in self.fitid:
            sequence = self.fitid[key]
            sequence = sequence + 1
        fitid = key + str(sequence)
        # save fitid in array for later reference
        self.fitid[key] = sequence
        # return the now unique fitid
        return fitid

    def map_account_to(self, row, overrides):
        """ map counter account to account_to. """
        return (0, row[self.keyCounterAcctNr])

    def map_memo_name(self, row, overrides):
        """Map several description fields to memo and construct name"""
        # Constructing description depends on bookcode

        # in general, we copy counterAcct information
        if row[self.keyCounterAcctNr] and row[self.keyCounterAcctName]:
            glue = " "
        else:
            glue = ""
        name = row[self.keyCounterAcctNr] + glue \
                + row[self.keyCounterAcctName]

        descr = row[self.keyDescr1] + row[self.keyDescr2] + row[self.keyDescr3]
        descr = descr.strip()
        # For 'db' and 'ba' we create a different description
        # For 'ac' the "betalingskenmerk" is a separate field (optional)
        if row[self.keyBookCode] == 'ba' and not name:
            name = row[self.keyDescr1]
            descr = row[self.keyDescr2] + row[self.keyDescr3]
        elif row[self.keyBookCode] == "db":
            if name:
                glue = " "
            else:
                glue = ""
            name = "[" + row[self.keyBookCode] + "] " \
                    + self.bookcode[row[self.keyBookCode]] + glue \
                    + name
        elif row[self.keyBookCode] == "ac":
            descr = descr + "betalingskenmerk " + row[self.keyBetalingsKenmerk]

        memo = descr.replace("&", "&amp")
        return (0, name, memo)

# ************** End Class CsvFile ***********************************************
# ********************************************************************************

# ********************************************************************************
# ************** Class Cfg         ***********************************************
class Cfg():
    """ class Cfg. """

    def __init__(self):
        config = configparser.ConfigParser()
        # use default filename for now
        configfile = "config.rabo2ofx.ini"
        self.config_accounts = list()
        self.config_overrides = dict()
        if os.path.exists(os.path.join(os.getcwd(), configfile)):
            config.read(configfile)
            config.sections()
            # store all accounts in uppercase
            for acc in config['accounts'].values():
                self.config_accounts.append(acc.upper())
            # get any overrides
##            if 'override' in config:
            for key in config['override']:
                self.config_overrides[key] = config['override'][key]


    def run(self):
        """ dummy run section for config class """
        print("*************** Config file ***************** ")
        msg = "Main account."
        for account in self.config_accounts:
            print(account + " " + msg)
            msg = "Subordinate to all previous accounts."
        print
        print("override")
        print
        print("force_date_posted")

    def main_accounts(self, account):
        """ Return the main accounts in a list """
        # if the named account is not in the config file, all accounts in the config are
        # regarded to be transfer accounts. Remember: must be uppercase
        main_accounts = set()
        for acc in self.config_accounts:
            main = acc
            # stop when we encounter the same account
            if main == account:
                break;
            main_accounts.add(main)

        return main_accounts

    def get_override(self, key):
        """ Return override requested if available """
        #
        return config_override[key]



# ************** End Class Cfg     ***********************************************
# ********************************************************************************
# ************** Class OfxWriter   ***********************************************

class OfxWriter():
    """ class OfxWriter. """

    date = datetime.date.today()
    nowdate = str(date.strftime("%Y%m%d"))
    processed_accounts = set()
    cfg = None
    csv = None
    filename = None
    filepath = None
    dir = None

    def __init__(self, cfg):
        #create path to ofxfile
        if ARGS.outfile:
            self.filename = ARGS.outfile
        else:
            self.filename = re.sub(".[cC][sS][vV]$", ".ofx", ARGS.csvfile)

        # Check the Config
        if not isinstance(cfg, Cfg):
            print ("cfg is not an instance of Cfg")
        self.cfg = cfg

        if ARGS.homebank:
            dir = 'ofx_hb'
        else:
            dir = ARGS.dir
        #if directory does not exists, create it.
        if not os.path.exists(os.path.join(os.getcwd(), dir)):
            os.makedirs(os.path.join(os.getcwd(), dir))

        self.dir = dir

        self.filepath = os.path.join(os.getcwd(), dir, self.filename)

        #Initiate a csv object with data in list of dictionaries.
        self.csv = CsvFile(cfg.config_overrides)

    def run(self):
        """ Run the generation of ofx records. """
        #Determine unique accounts and start and end dates
        mindate = 999999999
        maxdate = 0

        if ARGS.homebank:
            version_type = 'HomeBank'
        else:
            version_type = 'GnuCash'

        # print some statistics:
        print("           Output to " + self.dir + " (" + version_type + " version)" )
        print
        print("TRANSACTIONS: " + str(len(self.csv.transactions)))
        print("IN:           " + ARGS.csvfile)
        print("OUT:          " + self.filename)
        print

        accounts = dict()
        # Gather account numbers
        for trns in self.csv.transactions:
            accNr = trns['account']
            if accNr in accounts:
                account_rec = accounts[accNr]
            else:
                account_rec = dict()
                account_rec['txn_ctr'] = 0
                account_rec['txn_skip'] = 0
                account_rec['txn_processed'] = 0
                account_rec['nr_overrides'] = 0
                accounts[accNr] = account_rec
            if int(trns['dtposted']) < mindate:
                mindate = int(trns['dtposted'])
            if int(trns['dtposted']) > maxdate:
                maxdate = int(trns['dtposted'])

        ctr_accounts_processed = len(accounts)

        ctr_txns_processed = 0;
        ctr_txns_skipped_transfer = 0;

        #open ofx file, if file exists, it gets overwritten
        with open(self.filepath, 'w') as ofxfile:
            message_header = construct_message_header(self.nowdate)
            ofxfile.write(message_header)

            # Check all transactions once for each account
            # so the OFX xml can be ordered per account
            for account in accounts:
                account_message_start = construct_account_start(account, mindate, maxdate)
                ofxfile.write(account_message_start)

                # register which accounts to ignore in acountto i.e. are transfers to
                # earlier processed accounts
                transfer_accounts = self.gather_transfer_accounts(account)

                for trns in self.csv.transactions:
                    if trns['account'] == account:
                        message_transaction = construct_txn(trns)
                        accounts[account]['txn_ctr'] += 1
                        # guard against processing transfer between accounts twice for GnuCash
                        if trns['accountto'] in transfer_accounts and not ARGS.homebank:
                            accounts[account]['txn_skip'] += 1
                            # ignore nr_overrides
                        else:
                            accounts[account]['txn_processed'] += 1
                            accounts[account]['nr_overrides'] += trns['nr_overrides']
                            ofxfile.write(message_transaction)

                account_message_end = construct_account_end()
                ofxfile.write(account_message_end)
                # Remember this account was already processed
                self.processed_accounts.add(account)

            message_footer = construct_message_footer()
            ofxfile.write(message_footer)

            # Check accounts processed versus found accounts
            print("\taccountnumber     processed  skip   sum   overrides")
            for account in accounts:
                sys.stdout.write('\t%s '% account)      # prevent '\n'
                print("%(txn_processed)8d %(txn_skip)5d %(txn_ctr)5d %(nr_overrides)11d"%accounts[account] )
            print ("\t-")
            if len(self.processed_accounts) > len(self.cfg.config_accounts):
                print("warning: it seems you have more accounts in your file(s)")
                print("         than in your config.")
                print("         This carries the risk of double transfers if you use GnuCash.")
                print("")
                print("         Add all accounts you download to your")
                print("         config file and rerun the program.")
                print("         There is an example config in this directory.")
                print("         You can find the accounts processed in the stats above.")
                print
                print("         The config file is called 'config.rabo2ofx.ini'.")
                print("")
            if self.cfg.config_overrides:
                print("---- overrides        -----")
                for key in self.cfg.config_overrides:
                    print(key + " = " + self.cfg.config_overrides[key])

    def gather_transfer_accounts(self, account):
        """ Make sure all main accounts in config or already processed are
        treated as transfers, i.e. ignored."""

        if account in self.cfg.config_accounts:
            transfer_accounts = self.cfg.main_accounts(account)
        else:
            transfer_accounts = set()
            for acc in self.cfg.config_accounts:
                transfer_accounts.add(acc)
        for acc in self.processed_accounts:
            if acc not in self.cfg.config_accounts:
                transfer_accounts.add(acc);
        return transfer_accounts

# ************** End Class OfxWriter ***********************************************

def construct_message_header(date):
    """ Construct and return the starting message for the file. """
    message_header = """
<OFX>
   <SIGNONMSGSRSV1>
      <SONRS>                            <!-- Begin signon -->
         <STATUS>                        <!-- Begin status aggregate -->
            <CODE>0</CODE>               <!-- OK -->
            <SEVERITY>INFO</SEVERITY>
         </STATUS>
         <DTSERVER>%(nowdate)s</DTSERVER>   <!-- Oct. 29, 1999, 10:10:03 am -->
         <LANGUAGE>ENG</LANGUAGE>        <!-- Language used in response -->
         <DTPROFUP>%(nowdate)s</DTPROFUP>   <!-- Last update to profile-->
         <DTACCTUP>%(nowdate)s</DTACCTUP>   <!-- Last account update -->
         <FI>                            <!-- ID of receiving institution -->
            <ORG>NCH</ORG>               <!-- Name of ID owner -->
            <FID>1001</FID>              <!-- Actual ID -->
         </FI>
      </SONRS>                           <!-- End of signon -->
   </SIGNONMSGSRSV1>
   <BANKMSGSRSV1>
      <STMTTRNRS>                        <!-- Begin response -->
         <TRNUID>1001</TRNUID>           <!-- Client ID sent in request -->
         <STATUS>                     <!-- Start status aggregate -->
            <CODE>0</CODE>            <!-- OK -->
            <SEVERITY>INFO</SEVERITY>
         </STATUS>""" % {"nowdate": date}

    return message_header

def construct_message_footer():
    """ Construct and return the ending message for the file. """
    message_footer = """
      </STMTTRNRS>                        <!-- End of transaction -->
   </BANKMSGSRSV1>
</OFX>
      """
    return message_footer

def construct_account_start(account, mindate, maxdate):
    """ Construct and return the message containing account start message. """
    message_begin = """
        <STMTRS>                         <!-- Begin statement response -->
           <CURDEF>EUR</CURDEF>
           <BANKACCTFROM>                <!-- Identify the account -->
              <BANKID>RABONL2U</BANKID> <!-- Routing transit or other FI ID -->
              <ACCTID>%(account)s</ACCTID> <!-- Account number -->
              <ACCTTYPE>CHECKING</ACCTTYPE><!-- Account type -->
           </BANKACCTFROM>               <!-- End of account ID -->
           <BANKTRANLIST>                <!-- Begin list of statement trans. -->
              <DTSTART>%(mindate)s</DTSTART>
              <DTEND>%(maxdate)s</DTEND>""" % {"account": account,
                                               "mindate": mindate, "maxdate": maxdate}
    return message_begin

def construct_account_end():
    """ Construct and return the message containing account end message """
    message_end = """
              </BANKTRANLIST>                   <!-- End list of statement\
                       trans. -->
              <LEDGERBAL>                       <!-- Ledger balance \
                  aggregate -->
               <BALAMT>0</BALAMT>
               <DTASOF>199910291120</DTASOF><!-- Bal date: 10/29/99, 11:20 am -->
            </LEDGERBAL>                      <!-- End ledger balance -->
         </STMTRS>"""
    return message_end

def construct_txn(trns):
    """ Construct and return the message containing transaction message """
    message_transaction = """
                  <STMTTRN>
                     <TRNTYPE>%(trntype)s</TRNTYPE>
                     <DTPOSTED>%(dtposted)s</DTPOSTED>
                     <TRNAMT>%(trnamt)s</TRNAMT>
                     <FITID>%(fitid)s</FITID>
                     <NAME>%(name)s</NAME>
                     <BANKACCTTO>
                        <BANKID></BANKID>
                        <ACCTID>%(accountto)s</ACCTID>
                        <ACCTTYPE>CHECKING</ACCTTYPE>
                     </BANKACCTTO>
                     <MEMO>%(memo)s</MEMO>
                  </STMTTRN>""" % trns
    return message_transaction


if __name__ == "__main__":
    # Cfg will have empty list if there is no config file
    cfg = Cfg()
    OFX = OfxWriter(cfg)
    OFX.run()
