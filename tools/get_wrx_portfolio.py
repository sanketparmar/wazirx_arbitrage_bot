#!/usr/bin/env python3
import os
import sys
import time
import logging
from threading import Thread
import threading
import traceback
from cachetools import TTLCache
from print_dict import pd as printdict
from datetime import datetime
import json


# Custom libs bewow this 
curr_path = os.path.dirname(os.path.realpath(__file__)) 
lib_path = curr_path + "/../libs/"
sys.path.append(lib_path)

from myutils import get_logger, tg_alert, Heartbeat
from myutils import printred, printgreen, printyellow, printgrey, ctext
from config import *
from mywazirx import wazirx_client

if len(sys.argv) != 3:
	print("Please enter json conf file with profile.")
	sys.exit()

user_conf = sys.argv[1]
user_profile = sys.argv[2]


f = open(user_conf, "r")
USER_CONF = json.loads(f.read())

if "common" not in USER_CONF or user_profile not in USER_CONF:
	print("Not a valid config file or profile. Please check config file")
	print("Valid options", USER_CONF.keys())
	sys.exit()


conf_name = user_conf.split(os.sep)[-1] + "_" + user_profile

CONFIG = {**DEFAULT_CONFIG, **USER_CONF["common"]}

# Update as per the local config
CONFIG = {**CONFIG, **USER_CONF[user_profile]}



# TELEGRAM GROUP API KEYS
TG_ALD_API_KEY = CONFIG['TG_ALD_API_KEY']
TG_ALD_GRP_ID = CONFIG['TG_ALD_GRP_ID']

# WazirX API 
WRX_ACCESS_KEY = CONFIG['WRX_ACCESS_KEY']
WRX_SECRET_KEY = CONFIG['WRX_SECRET_KEY']
WRX_API_KEY = CONFIG['WRX_API_KEY']

WRX_MIN_INR_LIMIT = CONFIG['WRX_MIN_INR_LIMIT']
WRX_MIN_USDT_LIMIT = CONFIG['WRX_MIN_USDT_LIMIT']
WRX_MIN_WRX_LIMIT = CONFIG['WRX_MIN_WRX_LIMIT']

# INR LIMIT PER TRADE
INR_TRADE_LIMIT = CONFIG['INR_TRADE_LIMIT']

# Expected profit per trade in INR
MIN_EXPECTED_PROFIT_INR = CONFIG['MIN_EXPECTED_PROFIT_INR']

# THRESHOLD differnce PERC
THRESHOLD_DIFF_PERC = CONFIG['THRESHOLD_DIFF_PERC']

# Banned tocken lists
SKIP_BASE_TOKENS = CONFIG['SKIP_BASE_TOKENS']
SKIP_QUOTE_TOKENS = CONFIG['SKIP_QUOTE_TOKENS']

# Request delay in sec
SLEEP_TIME = CONFIG['SLEEP_TIME']

# REQUEST TIMEOUT (connect, read) 
REQ_TIMEOUT = CONFIG['REQ_TIMEOUT']

# MAX active threads 
MAX_ACTIVE_THREADS = CONFIG['MAX_ACTIVE_THREADS']

# Create Wazirx Client
wrx_client = wazirx_client(None, WRX_ACCESS_KEY, WRX_SECRET_KEY, WRX_API_KEY) 
val, holdings = wrx_client.get_portfolio_value()
#print(conf_name,  "wrx portfolio value:", "{:.2f}".format(val), "Rs.")
print(conf_name,  "Wazirx Portfolio: " + "{:.2f}".format(val) + " Rs. Total Holdings: " + str(holdings)+"\n")
