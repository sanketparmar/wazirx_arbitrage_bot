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
from binance.client import Client as BinanceClient
import requests
import json


# Custom libs bewow this 
curr_path = os.path.dirname(os.path.realpath(__file__)) 
lib_path = curr_path + "/../libs/"
sys.path.append(lib_path)

from myutils import get_logger, tg_alert, Heartbeat
from myutils import printred, printgreen, printyellow, printgrey, ctext
from config import *
import config
from mywazirx import wazirx_client
from wrx_to_bnc import wrx_trade_manager
from bnc_to_wrx import bnc_trade_manager

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

BNC_API_KEY = CONFIG['BNC_API_KEY']
BNC_SECRET_KEY = CONFIG['BNC_SECRET_KEY']

# INR LIMIT PER TRADE
USDT_TRADE_LIMIT = CONFIG['USDT_TRADE_LIMIT']

# Expected profit per trade in USDT
MIN_EXPECTED_PROFIT_USDT = CONFIG['MIN_EXPECTED_PROFIT_USDT']

# THRESHOLD differnce PERC
THRESHOLD_DIFF_PERC = CONFIG['THRESHOLD_DIFF_PERC']

# Banned tocken lists
WRX_ALLOWED_QUOTE_TOKENS = CONFIG['WRX_ALLOWED_QUOTE_TOKENS']
WRX_SKIP_BASE_TOKENS = CONFIG['WRX_SKIP_BASE_TOKENS']
BNC_ALLOWED_QUOTE_TOKENS = CONFIG['BNC_ALLOWED_QUOTE_TOKENS']
BNC_SKIP_BASE_TOKENS = CONFIG['BNC_SKIP_BASE_TOKENS']

# Request delay in sec
SLEEP_TIME = CONFIG['SLEEP_TIME']

# REQUEST TIMEOUT (connect, read) 
REQ_TIMEOUT = CONFIG['REQ_TIMEOUT']

# MAX active threads 
MAX_ACTIVE_THREADS = CONFIG['MAX_ACTIVE_THREADS']

#CONVERT ALL PRICE TO
CONV_UNIT = CONFIG['CONV_UNIT']


#### Main starts from here

# Get the logger
logfile = curr_path +"/logs/wrx2bnc_" + conf_name + "_main.log"
logger = get_logger("main", logfile, logging.INFO, True)

hbthrd = Heartbeat("wrx2bnc HB", conf_name, 60)
hbthrd.daemon = True
hbthrd.start()
printgreen("HB thread started")


tg_client = tg_alert(TG_ALD_API_KEY, TG_ALD_GRP_ID)

# To restrict frequtend url request
cached_token_lists = TTLCache(maxsize=10, ttl=900)

# To restrict totp usage
#TODO: Do we need this ? 
cache_30sec = TTLCache(maxsize=100, ttl=30)

bnc_pair_map = {}

#config.wrx_xferable_tokens = ['usdt', 'btc', 'bnb', 'wrx', 'zil', 'eth', 'ada', 'link', 'waves', 'band', 'dgb', 'doge', 'eos', 'atom', 'zec', 'algo', 'uni', 'xtz', 'hbar', 'enj', 'vet', 'dot', 'xem', 'yfi', 'ren', 'egld', 'grs', 'comp', 'kava', 'aave', 'cos', 'inj', 'snx', 'sushi', 'dock', 'avax', 'iotx', 'aion', 'bal', 'bnt', 'uma', 'ksm', 'luna', 'grt', 'paxg', 'zrx', 'ankr', 'xym', 'ckb', 'vib', 'paxg', 'gto', 'tko', 'crv', 'mana', 'dexe', 'etc', 'ftm', 'fet', 'fil', 'win', 'sc', 'cvc', 'cake', 'iost', 'ftt', 'avax', 'luna', 'ava', 'xvg', 'shib', 'bzrx', 'ftm', 'ark', 'hnt', 'one', 'kmd', 'zrx', 'ankr', 'ardr', 'rep', 'blz', 'celr', 'link', 'chz', 'cos']
#config.bnc_xferable_tokens = ['xem', 'bzrx', 'gto', 'vet', 'paxg', 'shib', 'xvg', 'iotx', 'bnt', 'usdt', 'doge', 'hbar', 'hnt', 'comp', 'waves', 'dock', 'chz', 'aion', 'dgb', 'zrx', 'kava', 'kmd', 'iost', 'cake', 'dot', 'uma', 'band', 'ava', 'btc', 'dexe', 'cvc', 'avax', 'tko', 'ark', 'egld', 'win', 'ftm', 'enj', 'inj', 'crv', 'ftt', 'one', 'grt', 'grs', 'ankr', 'sushi', 'lend', 'algo', 'atom', 'sc', 'aave', 'blz', 'uni', 'link', 'ckb', 'wrx', 'snx', 'yfi', 'luna', 'xtz', 'ardr', 'mana', 'ksm', 'cos', 'fil', 'eos', 'xym', 'bal', 'vib', 'fet', 'etc', 'bnb', 'celr', 'eth', 'zec', 'ren', 'rep', 'zil', 'ada']

#cached_token_lists['wrx_xferable_tokens'] = 1 
#cached_token_lists['bnc_xferable_tokens'] = 1 


# Create Wazirx Client
wrx_client = wazirx_client(logger, WRX_ACCESS_KEY, WRX_SECRET_KEY, WRX_API_KEY) 
bnc_client = BinanceClient(BNC_API_KEY, BNC_SECRET_KEY)

wrx_lock = threading.Lock()
bnc_lock = threading.Lock()

while True:
	try:
		
		if 'bnc_pair_data' not in cached_token_lists:
			logger.info("Fetching binance pair map")
			sinfo = bnc_client.get_exchange_info()

			for e in sinfo['symbols']:
				if e['status'] != "TRADING":
					continue

				bnc_pair_map[e['symbol']] = {
						'b': e['baseAsset'].lower(),
						'q': e['quoteAsset'].lower() }

				cached_token_lists['bnc_pair_data'] = 1
	
		if 'wrx_xferable_tokens' not in cached_token_lists:
			logger.info("Fetching xferable tokens from wazirx")
			data = wrx_client.get_bnc_xferable_tokens()

			config.wrx_xferable_tokens.clear()
			for t in data:
				config.wrx_xferable_tokens.append(t)
		
			cached_token_lists['wrx_xferable_tokens'] = 1 

		if 'bnc_xferable_tokens' not in cached_token_lists:
			logger.info("Fetching xferable tokens from binance")
			ses = requests.session()
			p = ses.get(BNC_XFERABLE_TOKEN_URL, timeout=REQ_TIMEOUT)
			
			jdata = json.loads(p.text)
			
			config.bnc_xferable_tokens.clear()
			for t in jdata['data']:
				config.bnc_xferable_tokens.append(t['assetCode'].lower())
		
			cached_token_lists['bnc_xferable_tokens'] = 1 

		if 'blocked_wrx_tokens' not in cached_token_lists:
			logger.info("Fetching tg bot blocked tokens")
			msgs = tg_client.get_bot_update()
			#print(msgs)
			wrx_lock.acquire()
			for msg in msgs:
				if "text" not in msg['message']:
					continue
				t = msg['message']['text'].lower()
				txtmsgs = t.split("\n")
				for m in txtmsgs:
					#print("telegram", m) #re, *syms = m.split(" ")
					pre, *syms = m.split(" ")
					if not pre or not syms:
						print(m, " not valid format")
						continue

					if pre == "b":
						config.blocked_wrx_tokens.extend(syms)
					if pre == "a":
						config.blocked_wrx_tokens = list(set(config.blocked_wrx_tokens) - set(syms))

					config.blocked_wrx_tokens = list(set(config.blocked_wrx_tokens))

			wrx_lock.release()
			msg = "NEW WRX BLOCKED TOKENS[" +conf_name+"]\n"
			msg += " ".join(config.blocked_wrx_tokens)
			print(msg)
			if msgs:
				tg_client.send_alert(msg)
			cached_token_lists['blocked_wrx_tokens'] = 1 

		arbt_ds = {}
		jdata = wrx_client.get_ticker_data()
		quote_rate = {}

		for t in WRX_ALLOWED_QUOTE_TOKENS:
			if t == CONV_UNIT:
				continue

			#quote_rate[CONV_UNIT + t] = {}
			if CONV_UNIT + t in jdata:
				if CONV_UNIT + t not in quote_rate:
					quote_rate[CONV_UNIT + t] = {}
				quote_rate[CONV_UNIT + t]['sell'] = float(jdata[CONV_UNIT + t]["sell"])
				quote_rate[CONV_UNIT + t]['buy'] = float(jdata[CONV_UNIT + t]["buy"])
			elif t + CONV_UNIT in jdata:
				if t+CONV_UNIT not in quote_rate:
					quote_rate[t+CONV_UNIT] = {}
			
				# TODO: RECHEKC LOGIC
				quote_rate[t+CONV_UNIT]['sell'] = float(jdata[t+CONV_UNIT]["buy"])
				quote_rate[t+CONV_UNIT]['buy'] = float(jdata[t+CONV_UNIT]["sell"])
			else:
				self.error("No valid pair found for quote conversion. " + CONV_UNIT + t)

		for pair in jdata.keys():
			data = jdata[pair]
			base_token = data['base_unit']
			quote_token = data['quote_unit']

			if quote_token not in WRX_ALLOWED_QUOTE_TOKENS:
				continue

			if base_token in WRX_SKIP_BASE_TOKENS:
				continue

		

			if float(data['sell']) == 0 or float(data['buy']) == 0:
				continue
	
			if base_token not in arbt_ds:
				arbt_ds[base_token] = {}

			xch_quote_token = "WAZIRX_" + quote_token


			arbt_ds[base_token][xch_quote_token] = {
				"quote_token": xch_quote_token,
				"sell": float(data['sell']),
				"buy" : float(data['buy']),
				"sell_unit": float(USDT_TRADE_LIMIT) / float(data['sell']),
				"buy_unit": float(USDT_TRADE_LIMIT) / float(data['buy']),

			}
			
			if quote_token == CONV_UNIT:
				arbt_ds[base_token][xch_quote_token]["conv_buy"] = arbt_ds[base_token][xch_quote_token]["buy"]
				arbt_ds[base_token][xch_quote_token]["conv_sell"] = arbt_ds[base_token][xch_quote_token]["sell"]
			elif CONV_UNIT + quote_token in quote_rate:
				arbt_ds[base_token][xch_quote_token]["conv_buy"] = arbt_ds[base_token][xch_quote_token]["buy"] / quote_rate[CONV_UNIT + quote_token]['sell']
				arbt_ds[base_token][xch_quote_token]["conv_sell"] = arbt_ds[base_token][xch_quote_token]["sell"] / quote_rate[CONV_UNIT + quote_token]['buy']
			elif quote_token + CONV_UNIT in quote_rate:
				arbt_ds[base_token][xch_quote_token]["conv_buy"] = arbt_ds[base_token][xch_quote_token]["buy"] * quote_rate[quote_token + CONV_UNIT]['sell']
				arbt_ds[base_token][xch_quote_token]["conv_sell"] = arbt_ds[base_token][xch_quote_token]["sell"] * quote_rate[quote_token + CONV_UNIT]['buy']

			arbt_ds[base_token][xch_quote_token]['sell_unit'] = float(USDT_TRADE_LIMIT) / arbt_ds[base_token][xch_quote_token]["conv_sell"]
			arbt_ds[base_token][xch_quote_token]['buy_unit'] = float(USDT_TRADE_LIMIT) / arbt_ds[base_token][xch_quote_token]["conv_buy"]



		ses = requests.session()
		p = ses.get(BNC_TICKER_URL, timeout=REQ_TIMEOUT)
		jdata = json.loads(p.text)
		quote_rate.clear()
		bnc_price_data = {}

		for data in jdata:
			symbol = data['symbol']

			if symbol not in bnc_pair_map:
				continue

			base_token = bnc_pair_map[symbol]['b']
			quote_token = bnc_pair_map[symbol]['q']

			if base_token+quote_token not in bnc_price_data:
				bnc_price_data[base_token+quote_token] = {}

			bnc_price_data[base_token+quote_token] = {
							"sell": float(data['askPrice']),
							"buy": float(data['bidPrice'])
						}

		for t in BNC_ALLOWED_QUOTE_TOKENS:
			if t == CONV_UNIT:
				continue

			if CONV_UNIT + t in bnc_price_data:
				if CONV_UNIT + t not in quote_rate:
					quote_rate[CONV_UNIT + t] = {}
				quote_rate[CONV_UNIT + t]['sell'] = float(bnc_price_data[CONV_UNIT + t]["sell"])
				quote_rate[CONV_UNIT + t]['buy'] = float(bnc_price_data[CONV_UNIT + t]["buy"])
			elif t + CONV_UNIT in bnc_price_data:
				# TODO: RECHEKC LOGIC
				if t + CONV_UNIT  not in quote_rate:
					quote_rate[t + CONV_UNIT] = {}

				quote_rate[t + CONV_UNIT]['sell'] = float(bnc_price_data[t+CONV_UNIT]["buy"])
				quote_rate[t + CONV_UNIT]['buy'] = float(bnc_price_data[t+CONV_UNIT]["sell"])
			else:
				print("No valid pair found for quote conversion")

		#print("Quote rate:", quote_rate)
		for data in jdata:
			symbol = data['symbol']

			if symbol not in bnc_pair_map:
				continue

			base_token = bnc_pair_map[symbol]['b']
			quote_token = bnc_pair_map[symbol]['q']

			if quote_token not in BNC_ALLOWED_QUOTE_TOKENS:
				continue

			if base_token in BNC_SKIP_BASE_TOKENS:
				continue

			if base_token not in arbt_ds:
				continue

			
			if base_token in config.blocked_wrx_tokens:
				continue

			xch_quote_token = "BINANCE_" + quote_token

			arbt_ds[base_token][xch_quote_token] = {
				"quote_token": xch_quote_token,
				"sell": float(data['askPrice']),
				"buy" : float(data['bidPrice']),
				#"sell_unit": float(USDT_TRADE_LIMIT) / float(data['askPrice']),
				#"buy_unit": float(USDT_TRADE_LIMIT) / float(data['bidPrice']),
			}

			if quote_token == CONV_UNIT:
				arbt_ds[base_token][xch_quote_token]["conv_buy"] = arbt_ds[base_token][xch_quote_token]["buy"]
				arbt_ds[base_token][xch_quote_token]["conv_sell"] = arbt_ds[base_token][xch_quote_token]["sell"]
			elif CONV_UNIT + quote_token in quote_rate:
				arbt_ds[base_token][xch_quote_token]["conv_buy"] = arbt_ds[base_token][xch_quote_token]["buy"] / quote_rate[CONV_UNIT + quote_token]['sell']
				arbt_ds[base_token][xch_quote_token]["conv_sell"] = arbt_ds[base_token][xch_quote_token]["sell"] / quote_rate[CONV_UNIT + quote_token]['buy']

			elif quote_token + CONV_UNIT in quote_rate:
				arbt_ds[base_token][xch_quote_token]["conv_buy"] = arbt_ds[base_token][xch_quote_token]["buy"] * quote_rate[quote_token + CONV_UNIT]['sell']
				arbt_ds[base_token][xch_quote_token]["conv_sell"] = arbt_ds[base_token][xch_quote_token]["sell"] * quote_rate[quote_token + CONV_UNIT]['buy']

			# Update qty
			arbt_ds[base_token][xch_quote_token]['sell_unit'] = float(USDT_TRADE_LIMIT) / arbt_ds[base_token][xch_quote_token]["conv_sell"]
			arbt_ds[base_token][xch_quote_token]['buy_unit'] = float(USDT_TRADE_LIMIT) / arbt_ds[base_token][xch_quote_token]["conv_buy"]

			#print("base: ", base_token)
			#print("quote ", quote_token)
			#printdict(quote_rate)


        

		#printdict(arbt_ds)

		for base_token in arbt_ds.keys():

			if len(arbt_ds[base_token].keys()) < 2:
				continue

			# Sell to this price
			max_buy_price = max([sub["conv_buy"] for sub in arbt_ds[base_token].values() if "conv_buy" in sub.keys()])                                                                                 
			# Buy from this price 
			min_sell_price = min([sub["conv_sell"] for sub in arbt_ds[base_token].values() if "conv_sell" in sub.keys()])
			perc_diff = ((max_buy_price - min_sell_price) / min_sell_price ) * 100

			if perc_diff < THRESHOLD_DIFF_PERC:
				#print("Mininum threashold perc diff doesn't match. Perc diff:", perc_diff, " Expected:", THRESHOLD_DIFF_PERC)
				continue


			#print(base_token, "Mininum threashold perc diff doesn't match. Perc diff:", perc_diff, " Expected:", THRESHOLD_DIFF_PERC)

			#printdict(arbt_ds[base_token])
			# We will sell higer to actual buyer 
			buy_quote_x = [sub['quote_token'] for sub in arbt_ds[base_token].values() if sub["conv_buy"] == max_buy_price][0] 
			# We will buy low from actual seller 
			sell_quote_x = [sub['quote_token'] for sub in arbt_ds[base_token].values() if sub["conv_sell"] == min_sell_price][0] 
			#print("buy_quote", buy_quote_x, "sell_quote_x", sell_quote_x)
			#printdict(arbt_ds)
			# NOw ONWORDS, BUY, SELL is from our perspective
			sell_xchange, sell_quote = buy_quote_x.split("_")
			sell_price = arbt_ds[base_token][buy_quote_x]["buy"]
			conv_sell_price = arbt_ds[base_token][buy_quote_x]["conv_buy"]
			buy_xchange, buy_quote = sell_quote_x.split("_")
			buy_price = arbt_ds[base_token][sell_quote_x]["sell"]
			conv_buy_price = arbt_ds[base_token][sell_quote_x]["conv_sell"]
			#print("sell_xchange", sell_xchange, "sell quote", sell_quote)
			#print("buy_xchange", buy_xchange, "buy quote", buy_quote)
			#print("buy_price:", buy_price, "sell_price", sell_price)
			#if sell_quote != buy_quote:
			#	continue

			buy_qty = arbt_ds[base_token][buy_quote_x]['sell_unit']

			k = base_token + "_" + buy_xchange + "_" +sell_xchange
			if k not in cache_30sec:
				cache_30sec[k] = 0
			elif cache_30sec[k] > 5 and perc_diff < 3:
				printyellow(k + " is time restricted")
				continue

			#printdict(arbt_ds[base_token])

			#printgrey("Buy " + str(base_token) + " from " + str(buy_xchange) + " @ " + str(buy_price))
			#printgrey("Sell " + str(base_token) + " from " + str(sell_xchange) + " @ " + str(sell_price))
			#printgrey("Perc diff: " + str(perc_diff) + "%")

			xferable = False
			pair = base_token + sell_quote 
			if buy_xchange == "WAZIRX":
				logfile = curr_path +"/logs/wrx2bnc_" + conf_name + "_" + pair + ".log"
				wrx_logger = get_logger(pair, logfile, logging.INFO, True)

				# Create Wazirx thread here
				if base_token in config.wrx_xferable_tokens:
					xferable = True

				if xferable == False and perc_diff < 5:
					# DO nothing
					pass
				else:
					#printdict(arbt_ds[base_token])
					#printgrey("Buy " + str(base_token) + " from " + str(buy_xchange) + " @ " + str(buy_price))
					#printgrey("Sell " + str(base_token) + " from " + str(sell_xchange) + " @ " + str(sell_price))
					#printgrey("Perc diff: " + str(perc_diff) + "%")


					thrd = wrx_trade_manager(wrx_logger, wrx_lock, CONFIG, base_token, buy_quote, sell_quote, buy_price, sell_price, conv_buy_price, conv_sell_price, buy_qty, xferable)
					thrd.daemon = True
					thrd.start()
					cache_30sec[k] += 1

					#print("################# " + str(xferable) + str(perc_diff))
					time.sleep(5)
						
	
			else:
				#logfile = curr_path +"/logs/bnc2wrx_" + conf_name + "_" + pair + ".log"
				#bnc_logger = get_logger(pair, logfile, logging.INFO, True)
				## Create Binance thread here only if base is xferable  
				#if base_token in bnc_xferable_tokens:
				#	thrd = bnc_trade_manager(bnc_logger, bnc_lock, CONFIG, base_token, sell_quote, buy_price, sell_price, buy_qty, xferable)
				#	thrd.daemon = True
				#	thrd.start()
				#	cache_30sec[k] += 1
				#else: 
				#	printgrey(base_token + "is not transferable from binance to wazirx")
				pass

		print(".")
		time.sleep(1)

	except KeyboardInterrupt:
		sys.exit()
	except Exception as e:
		track = traceback.format_exc()
		print(track)
		print("Exception")
		if wrx_lock.locked():
			wrx_lock.release()
		if bnc_lock.locked():
			bnc_lock.release()
	
	

