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

class trade_manager(Thread):
	def __init__(self, base, quote_sell, sell_price, quote_buy, buy_price, qty, xchange_base, xchange_quote, xchange_side, xchange_rate):
		Thread.__init__(self)
		self.name = base+"_"+quote_buy+"_"+quote_sell
		self.base = base
		self.quote_sell = quote_sell
		self.quote_buy = quote_buy
		self.buy_price = buy_price
		self.sell_price = sell_price
		self.xchange_base = xchange_base
		self.xchange_quote = xchange_quote
		self.xchange_side = xchange_side 
		self.xchange_rate = xchange_rate
		self.qty = qty

		self.tg_alert = tg_alert(TG_ALD_API_KEY, TG_ALD_GRP_ID)

		logfile = curr_path +"/logs/WRX_" + conf_name + "_"+ self.name + ".log"
		self.logger = get_logger(self.name, logfile, logging.INFO, True)

		self.logger.info("Created new thread object for " + self.name)
		self.logger.info("Base: " + base)
		self.logger.info("Buy Quote:"+ str(quote_buy))
		self.logger.info("Buy Price:"+ str(buy_price))
		self.logger.info("Sell Quote:" + str(quote_sell))
		self.logger.info("Sell Price:" + str(sell_price))
		self.logger.info("Qty: " + str(qty))
		self.logger.info("xchange base:" + str(xchange_base))
		self.logger.info("xchange quote:" + str(xchange_quote))
		self.logger.info("xchange side:" + xchange_side)
		self.logger.info("xchange rate:" + str(xchange_rate))
	
	def run(self):

		wrx_client = wazirx_client(self.logger, WRX_ACCESS_KEY, WRX_SECRET_KEY, WRX_API_KEY) 

		# Put buy order 
		self.logger.info("Placing buy order")
		order_id, msg = wrx_client.place_order("buy", self.base, self.quote_buy, self.buy_price, self.qty)
		if order_id == None:
			#prev_pair_sell_order_id = None
			self.logger.error("Failed to place buy order" +  msg)
			if "Not enough" in msg:
				msg = "[" + conf_name + "] Low balance alert - \n" 
				msg += "While buying " + self.base +  self.quote_buy
				self.tg_alert.send_alert(msg)

			return

		# Wait for confirmation for 30 sec
		self.logger.info("Waiting for 30 sec for buy confirmation")
		confirmed_qty, pending_qty, quote_qty = wrx_client.wait_for_confirmation(order_id, 30)
		self.logger.info("BUY confirmed_qty: " + str(confirmed_qty) + " Pending qrt: " + str(pending_qty) + " Quote qty:" + str(quote_qty))
		if not confirmed_qty:
			# cancel order
			#prev_pair_sell_order_id = None
			self.logger.error("Failed to confirm buy order...canceling the order")
			wrx_client.cancel_order(order_id)
			return

		# If confirmed less than 70%, Place market order
		if confirmed_qty / (confirmed_qty + pending_qty) < 0.7:
			self.logger.error("Partially confirm buy order...canceling the order")
			wrx_client.cancel_order(order_id)
	
			# Place sell order at buyin price
			self.logger.error("Confirmed qty is low. Placing sell order")
			wrx_client.place_order("sell", self.base, self.quote_buy, self.buy_price, confirmed_qty)
			return

		elif pending_qty:
			self.logger.error("Partially confirm buy order...canceling the order")
			wrx_client.cancel_order(order_id)
	
		if confirmed_qty < self.qty:
			self.logger.info("Confirmed buy volume is low than ordered. Confirmed:" + str(confirmed_qty) + " Odered: " + str(self.qty))

		self.qty = confirmed_qty

		# place sell order
		self.logger.info("Placing sell order")
		order_id, msg = wrx_client.place_order("sell", self.base, self.quote_sell, self.sell_price, self.qty)
		if order_id == None:
			self.logger.error("Failed to place sell order", msg)
			return
			
		# Wait for confirmation for max 10 mins 
		self.logger.info("Waiting for 900 sec for sell confirmation")
		confirmed_qty, pending_qty, quote_qty = wrx_client.wait_for_confirmation(order_id, 1200)

		self.logger.info("Sell confirmed_qty: " + str(confirmed_qty) + " Pending qrt: " + str(pending_qty) + " Quote qty:" + str(quote_qty))
		if not confirmed_qty:
			# cancel order
			#prev_pair_sell_order_id = None
			self.logger.error("Failed to confirm sell order...canceling the order")
			wrx_client.cancel_order(order_id)
			time.sleep(5) # to reflect the bal into wallet

			# Sell original pair at  market price
			price = wrx_client.get_price("sell", self.base, self.quote_sell, self.sell_price)
			# place sell order

			order_id, msg = wrx_client.place_order("sell", self.base, self.quote_sell, price, self.qty)
			return

		if pending_qty != 0:
			# cancel order
			self.logger.error("Partially confirm sell order...canceling the order")
			wrx_client.cancel_order(order_id)

			time.sleep(5) # to reflect the bal into wallet
			# Sell original pair at  market price
			price = wrx_client.get_price("sell", self.base, self.quote_sell, self.sell_price)
			# place sell order

			order_id, msg = wrx_client.place_order("sell", self.base, self.quote_sell, price, pending_qty)
			return


		self.qty = quote_qty

		# Put exchange order
		self.logger.info("Getting best price for xchange trade")
		best_price = wrx_client.get_price(self.xchange_side, self.xchange_base, self.xchange_quote, self.qty)
		self.logger.info("Best price for xchange trade: " + str(best_price) + " Calcuated price for xchange_rate: " + str(self.xchange_rate))

		if best_price == 0:
			return

		if self.xchange_side == "buy":
			self.qty = float(self.qty) / float(best_price)

		self.logger.info("Placing coin exhange order")
		wrx_client.place_order(self.xchange_side, self.xchange_base, self.xchange_quote, best_price, self.qty)
		
			

#### Main starts from here

running_thread_list = {}
time_resticted_list = TTLCache(maxsize=100, ttl=120)


# Get the logger
logfile = curr_path +"/logs/wrx2wrx_" + conf_name + "_main.log"
logger = get_logger("main", logfile, logging.INFO, True)
# Create Wazirx Client
wrx_client = wazirx_client(logger, WRX_ACCESS_KEY, WRX_SECRET_KEY, WRX_API_KEY) 


hbthrd = Heartbeat("wrx2wrx", conf_name, 60, wrx_client = wrx_client)
hbthrd.daemon = True
hbthrd.start()
printgreen("HB thread started")

while True:
	try:
		if (threading.active_count() >= MAX_ACTIVE_THREADS):
			printgrey("Max active threads" + str(threading.active_count()))
			for thread in threading.enumerate(): 
				printgrey("Active:" + thread.name)
			time.sleep(10)
			continue

		tdata = wrx_client.get_ticker_data()
		arbt_data = {}	

		# GET THE INR PRICE
		usdtinr_last_price = float(tdata['usdtinr']['last'])
		usdtinr_buy_price = float(tdata['usdtinr']['buy'])
		usdtinr_sell_price = float(tdata['usdtinr']['sell'])
		wrxinr_last_price = float(tdata['wrxinr']['last'])
		wrxinr_buy_price = float(tdata['wrxinr']['buy'])
		wrxinr_sell_price = float(tdata['wrxinr']['sell'])
		btcinr_last_price = float(tdata['btcinr']['last'])
		btcinr_buy_price = float(tdata['btcinr']['buy'])
		btcinr_sell_price = float(tdata['btcinr']['sell'])

		# caclulate quote token trade limits based on INR_TRADE_LIMIT
		USDT_TRADE_LIMIT = int(INR_TRADE_LIMIT / usdtinr_buy_price)
		WRX_TRADE_LIMIT = int(INR_TRADE_LIMIT / wrxinr_buy_price)
		BTC_TRADE_LIMIT = int(INR_TRADE_LIMIT / btcinr_buy_price)

		for pair in tdata.keys():
			data = tdata[pair]

			base = data['base_unit']
			quote = data['quote_unit']
			if base in SKIP_BASE_TOKENS or quote in SKIP_QUOTE_TOKENS:
				continue

			if float(data['sell']) == 0 or float(data['buy']) == 0:
				continue
	
			if base not in arbt_data:
				arbt_data[base] = {}
	
			arbt_data[base][quote] = {
				"quote_unit": quote,
				"sell": float(data['sell']),
				"buy" : float(data['buy']),
				"last": float(data['last'])
			}

		# following code convers quote units into INR 
		for base_token in list(arbt_data.keys()):
			# We need atlease 2 quotes
			if len(arbt_data[base_token].keys()) < 2 and base_token != "usdt":
				del arbt_data[base_token]
				continue
			for quote_coin in arbt_data[base_token].keys():
				if quote_coin == "inr":
					#TODO: Should we use usdt buy and sell price or only sell as it is best possible
					arbt_data[base_token][quote_coin]["conv_buy"] = arbt_data[base_token][quote_coin]["buy"] 
					arbt_data[base_token][quote_coin]["conv_sell"] = arbt_data[base_token][quote_coin]["sell"] 
					arbt_data[base_token][quote_coin]["buy_units"] = float(INR_TRADE_LIMIT / arbt_data[base_token][quote_coin]["buy"])
					arbt_data[base_token][quote_coin]["sell_units"] = float(INR_TRADE_LIMIT / arbt_data[base_token][quote_coin]["sell"])
	
				elif quote_coin == "usdt":
					arbt_data[base_token][quote_coin]["conv_buy"] = arbt_data[base_token][quote_coin]["buy"] * usdtinr_sell_price
					arbt_data[base_token][quote_coin]["conv_sell"] = arbt_data[base_token][quote_coin]["sell"] * usdtinr_buy_price
					arbt_data[base_token][quote_coin]["buy_units"] = float(USDT_TRADE_LIMIT / arbt_data[base_token][quote_coin]["buy"])
					arbt_data[base_token][quote_coin]["sell_units"] = float(USDT_TRADE_LIMIT / arbt_data[base_token][quote_coin]["sell"])
	
	
				elif quote_coin == "wrx":
					arbt_data[base_token][quote_coin]["conv_buy"] = arbt_data[base_token][quote_coin]["buy"] * wrxinr_sell_price
					arbt_data[base_token][quote_coin]["conv_sell"] = arbt_data[base_token][quote_coin]["sell"] * wrxinr_buy_price
					arbt_data[base_token][quote_coin]["buy_units"] = float(WRX_TRADE_LIMIT / arbt_data[base_token][quote_coin]["buy"])
					arbt_data[base_token][quote_coin]["sell_units"] = float(WRX_TRADE_LIMIT / arbt_data[base_token][quote_coin]["sell"])
	
	
				elif quote_coin == "btc":
					arbt_data[base_token][quote_coin]["conv_buy"] = arbt_data[base_token][quote_coin]["buy"] * btcinr_sell_price
					arbt_data[base_token][quote_coin]["conv_sell"] = arbt_data[base_token][quote_coin]["sell"] * btcinr_buy_price
					arbt_data[base_token][quote_coin]["buy_units"] = float(BTC_TRADE_LIMIT / arbt_data[base_token][quote_coin]["buy"])
					arbt_data[base_token][quote_coin]["sell_units"] = float(BTC_TRADE_LIMIT / arbt_data[base_token][quote_coin]["sell"])

		for base_token in arbt_data.keys():
			# BUY at MAX
			max_price = max([sub["conv_buy"] for sub in arbt_data[base_token].values() if "conv_buy" in sub.keys()]) 
			# SELL at MIN
			min_price = min([sub["conv_sell"] for sub in arbt_data[base_token].values() if "conv_sell" in sub.keys()])
			perc_diff = ((max_price - min_price) / min_price ) * 100

			if perc_diff < THRESHOLD_DIFF_PERC:
				continue
	
			# We will sell higer to actual buyer
			act_buy_price_quote_token = [sub['quote_unit'] for sub in arbt_data[base_token].values() if sub["conv_buy"] == max_price][0]
			# We will buy low from actual seller
			act_sell_price_quote_token = [sub['quote_unit'] for sub in arbt_data[base_token].values() if sub["conv_sell"] == min_price][0]

			buy_vol = wrx_client.get_volume('buy', base_token, act_sell_price_quote_token, arbt_data[base_token][act_sell_price_quote_token]['sell'])
			sell_vol = wrx_client.get_volume('sell', base_token, act_buy_price_quote_token, arbt_data[base_token][act_buy_price_quote_token]['buy'])
			#printyellow("Buy vol from trade book" + str(buy_vol))
			#printyellow("Sell vol from trade book" +str(sell_vol))
			#printyellow("Calculated vol " + str(arbt_data[base_token][act_sell_price_quote_token]['sell_units']))


			volume = min(arbt_data[base_token][act_sell_price_quote_token]['sell_units'], buy_vol, sell_vol)
			if volume <= 0:
				#print(base_token, "Low buy/sell volume")
				continue

			# check for min trading , INR 50, WRX 50, USDT 2
			buy_trade_units = volume * arbt_data[base_token][act_sell_price_quote_token]['sell']
			sell_trade_units = volume * arbt_data[base_token][act_buy_price_quote_token]['buy']

			if (act_sell_price_quote_token == "inr" and buy_trade_units < WRX_MIN_INR_LIMIT):
				#print(base_token, "low buy volume for ",act_sell_price_quote_token, "volume:", buy_trade_units)
				continue

			if (act_sell_price_quote_token == "usdt" and buy_trade_units < WRX_MIN_USDT_LIMIT):
				#print(base_token, "low buy volume for ",act_sell_price_quote_token, "volume:", buy_trade_units)
				continue

			if (act_sell_price_quote_token == "wrx" and buy_trade_units < WRX_MIN_WRX_LIMIT):
				#print(base_token, "low buy volume for ",act_sell_price_quote_token, "volume:", buy_trade_units)
				continue
			
			if (act_buy_price_quote_token == "inr" and sell_trade_units < WRX_MIN_INR_LIMIT):
				#print(base_token, "low sell volume for ", act_buy_price_quote_token, "volume:", sell_trade_units)
				continue

			if (act_buy_price_quote_token == "usdt" and sell_trade_units < WRX_MIN_USDT_LIMIT):
				#print(base_token, "low sell volume for ", act_buy_price_quote_token, "volume:", sell_trade_units)
				continue

			if (act_buy_price_quote_token == "wrx" and sell_trade_units < WRX_MIN_WRX_LIMIT):
				#print(base_token, "low sell volume for ", act_buy_price_quote_token, "volume:", sell_trade_units)
				continue

			# Before putting order, Check minimum expected profit 
			buy_total = arbt_data[base_token][act_sell_price_quote_token]['conv_sell'] * volume 
			sell_total = arbt_data[base_token][act_buy_price_quote_token]['conv_buy'] * volume

			if sell_total - buy_total < MIN_EXPECTED_PROFIT_INR:
				#printyellow("Expected profit is very low, skip this trade")
				continue
			
			quote_buy =  act_sell_price_quote_token
			buy_price = arbt_data[base_token][act_sell_price_quote_token]['sell']
			quote_sell = act_buy_price_quote_token
			sell_price = arbt_data[base_token][act_buy_price_quote_token]['buy']

			if quote_sell in arbt_data.keys():
				xchange_base = quote_sell
				xchange_quote = quote_buy
				xchange_side = "sell"
				xchange_rate = arbt_data[xchange_base][xchange_quote]['sell']
			elif quote_buy in arbt_data.keys():
				xchange_base = quote_buy
				xchange_quote = quote_sell
				xchange_side = "buy"
				xchange_rate = arbt_data[xchange_base][xchange_quote]['buy']
			else:
				print("Invalid pair", quote_buy, quote_sell)
				continue

			s = base_token+"_"+quote_buy+"_"+quote_sell
			if s in running_thread_list.keys() and running_thread_list[s].is_alive():
				print(s + " thread is alredy runnig and not finished")
				continue

			if perc_diff < 1 and s in time_resticted_list.keys():
				print(s + " trade is timing resticted")
				printdict(time_resticted_list)
				continue

			printgreen("Starting thread for " + s)

			thrd = trade_manager(base_token, quote_sell, sell_price, quote_buy, buy_price, volume, xchange_base, xchange_quote, xchange_side, xchange_rate)

			thrd.daemon = True
			running_thread_list[s] = thrd
			time_resticted_list[s] = str(datetime.now()) 
			thrd.start()
			
		printgrey(".")
		time.sleep(SLEEP_TIME)

	
	except KeyboardInterrupt:
		sys.exit()
	except Exception as e:
		prev_traded_pair = ""
		prev_pair_sell_order_id = None

		track = traceback.format_exc()
		printred("Exception")
		printyellow(track)
		time.sleep(5)
