from threading import Thread
import threading
import math
import time
import requests
import json
import hmac
import hashlib
import pyotp
import traceback
from numpy import format_float_positional
from binance.client import Client as BinanceClient
from mywazirx import wazirx_client
import config
	

class wrx_trade_manager(Thread):
	def __init__(self, logger, lock, cfg, base, buy_quote, sell_quote, buy_at, sell_at, conv_buy_at, conv_sell_at, qty, xferable):
		Thread.__init__(self)
		self.name = "wrx_to_bnc|" + base
		self.base = base
		self.buy_quote = buy_quote
		self.sell_quote = sell_quote
		self.buy_at = buy_at
		self.sell_at = sell_at
		self.conv_sell_at = conv_sell_at
		self.conv_buy_at = conv_buy_at
		self.qty = qty
		self.cfg = cfg
		self.lock = lock
		self.xferable = xferable
		self.logger = logger

		WRX_ACCESS_KEY = self.cfg['WRX_ACCESS_KEY']
		WRX_API_KEY = self.cfg['WRX_API_KEY']
		WRX_SECRET_KEY = self.cfg['WRX_SECRET_KEY']
		self.wrx_client = wazirx_client(self.logger, WRX_ACCESS_KEY, WRX_SECRET_KEY, WRX_API_KEY)

		BNC_API_KEY = self.cfg['BNC_API_KEY']
		BNC_SECRET_KEY = self.cfg['BNC_SECRET_KEY']
		self.bnc_client = BinanceClient(BNC_API_KEY, BNC_SECRET_KEY)

		self.min_expected_profit_usdt = self.cfg["MIN_EXPECTED_PROFIT_USDT"]
		self.wrx_totp_key = self.cfg["WRX_TOTP_KEY"]
		
		self.conv_unit = self.cfg['CONV_UNIT']
		print("Buying ", self.base + self.buy_quote, " @ ", self.buy_at, "(CV:" , self.conv_buy_at, ") QTY:", self.qty)
		print("Selling", self.base + self.sell_quote, " @ ", self.sell_at, "(CV:" , self.conv_sell_at, ")")
	
	def run(self):
		try:
			self.lock.acquire()
			print("Running thread ", self.name)

			if self.base in config.blocked_wrx_tokens:
				print("Bloked token", self.base)
				self.lock.release()
				return

			buy_vol = self.wrx_client.get_volume('buy', self.base, self.buy_quote, self.buy_at)

			if self.xferable:
				sell_vol = self.bnc_get_volume()
			else:
				sell_vol = buy_vol

			qty = min(buy_vol, sell_vol, self.qty)

			if qty <= 0:
				print("No buyer or seller. Terminating thread:", self.name)
				self.lock.release()
				return 
				
			exp_profit = (qty * self.conv_sell_at) - (qty * self.conv_buy_at)
			print("Expected profit: ", exp_profit, "USDT")
			if exp_profit < self.min_expected_profit_usdt:
				print("Low profit", exp_profit, "USDT")
				self.lock.release()
				return

			self.qty = qty

			# Place buy order 
			order_id, msg = self.wrx_client.place_order("buy", self.base, self.buy_quote, self.buy_at, self.qty)

			print("Placing buy order")
			if order_id == None:
				print("Failed to place buy order")
				self.lock.release()
				return

			# Wait for confirmation
			print("Waiting for buy order confirmation")
			confirmed_qty, pending_qty, quote_qty = self.wrx_client.wait_for_confirmation(order_id, 40)
			if not confirmed_qty or (confirmed_qty < (self.qty * 0.7)):
				# cancel order
				print("Failed to confirm buy order...canceling the order")
				self.wrx_client.cancel_order(order_id)
				if confirmed_qty:
					# If partial confirmed then selll it off
					self.wrx_client.place_order("sell", self.base, self.conv_unit, self.conv_sell_at, confirmed_qty)
				self.lock.release()
				return

			if confirmed_qty < self.qty:
				self.wrx_client.cancel_order(order_id)
				print("Confirmed buy volume is low than ordered. Confirmed:" + str(confirmed_qty) + " Odered: " + str(self.qty))

			self.qty = confirmed_qty

			if not self.xferable:
				# Place sell order on wazirx only
				print("placing sell order on wazirx")
				order_id, msg = self.wrx_client.place_order("sell", self.base, self.conv_unit, self.conv_sell_at, self.qty)
				config.blocked_wrx_tokens.append(self.base)
				self.lock.release()
				return

			# Transfer to Binance 
			print("Transfering fund to binance")
			retry = 3 
			while retry:
				ret = self.wrx_client.transfer_fund_to_binance(self.base, self.qty, self.wrx_totp_key)
				if ret != "RETRY":
					break
				
				print("Failed to transfer fund. Retrying ", retry)
				time.sleep(30)
				retry -= 1 

			if not ret:
				print("Failed to transfer funds to binance")
				#TODO: SEll it of  ?
				# Remove from transferable list
				print("Removing from xferable tokens", self.base)
				config.blocked_wrx_tokens.append(self.base)
				print("List:", config.blocked_wrx_tokens)
				self.wrx_client.place_order("sell", self.base, self.conv_unit, self.conv_sell_at, confirmed_qty)
				self.lock.release()
				return
		
			# Confirm Balance
			print("Confirming balance")
			retry = 3
			bal = 0
			while retry:
				b = self.bnc_client.get_asset_balance(asset=self.base.upper())
				print(self.base, "balance:", b)
				bal = float(b['free'])
				if bal >= self.qty:
					break
				retry -= 1
				time.sleep(5)
			
			if bal < self.qty:
				print("Transfered fund got stuck inbetween")
				self.lock.release()
				return

			# Sell on Binance 
			print("Placing sell order on binance")
			symbol = self.base.upper() + self.sell_quote.upper()
			# GET symbol price 
			symbol_info = self.bnc_client.get_symbol_info(symbol=symbol)
			price_precision, qty_precision = self.get_pricelot_format(symbol, symbol_info, self.sell_at, self.qty)

			if float(qty_precision) > self.qty:
				qty_precision = self.qty

			# Place limit order with profit
			order = self.bnc_client.order_limit_sell(
				symbol=symbol,
				quantity=qty_precision,
				price=price_precision)
		
			print("Placed sell limit order", order)
			self.lock.release()

		except Exception as e:
			track = traceback.format_exc()
			print("Exception in thread", self.name)
			print(track)
			if self.lock.locked():
				self.lock.release()

	def wrx_get_volume(self):
		market = self.base.lower() + self.buy_quote.lower()
		ts = str(int(time.time() * 1000))
		trade_side = "buy"
		price = self.buy_at
	
		WRX_ACCESS_KEY = self.cfg['WRX_ACCESS_KEY']
		WRX_API_KEY = self.cfg['WRX_API_KEY']
		WRX_SECRET_KEY = self.cfg['WRX_SECRET_KEY']
	
		session = requests.session()
		sign_str = "GET|access-key="+WRX_ACCESS_KEY+"&tonce="+ts+ "|/api/v2/depth|limit=10&market="+market;
		signature = hmac.new(str.encode(WRX_SECRET_KEY), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = WRX_HEADERS.copy()
		hdrs['access-key'] = WRX_ACCESS_KEY
		hdrs['api-key'] = WRX_API_KEY
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		p = session.get(WRX_DEPTH_URL.format(market), headers=hdrs, timeout=REQ_TIMEOUT)
		jdata = json.loads(p.text)
	
		print(jdata)
	
		volume = 0
		if trade_side == "buy":
			for e in jdata['asks']:
				if  float(e[0]) <= price:
					volume += float(e[1])
				
		elif trade_side == "sell":
			for e in jdata['bids']:
				if float(e[0]) >= price:
					volume += float(e[1])
				
		print(market, trade_side, price, volume)
		return volume


	def bnc_get_volume(self):
		market = self.base.upper() + self.sell_quote.upper()
		limit = 10
		price = self.sell_at
		trade_side = "sell"
		jdata = self.bnc_client.get_order_book(symbol=market, limit=limit)
		#print(jdata)
	
		volume = 0
		if trade_side == "buy":
			for e in jdata['asks']:
				if  float(e[0]) <= price:
					volume += float(e[1])
				
		elif trade_side == "sell":
			for e in jdata['bids']:
				if float(e[0]) >= price:
					volume += float(e[1])
				
		#print(market, trade_side, price, volume)
		return volume

	def wrx_place_order(self):
		market = self.base.lower() + self.quote.lower()
		trade_side = "buy"
		order_type = "limit"
		ts = str(int(time.time() * 1000))
		WRX_ACCESS_KEY = self.cfg['WRX_ACCESS_KEY']
		WRX_API_KEY = self.cfg['WRX_API_KEY']
		WRX_SECRET_KEY = self.cfg['WRX_SECRET_KEY']
	
		sign_str = "POST|access-key="+WRX_ACCESS_KEY+"&tonce="+ts+ "|/api/v2/orders|";
		signature = hmac.new(str.encode(WRX_SECRET_KEY), str.encode(sign_str), hashlib.sha256).hexdigest()
		
		hdrs = WRX_HEADERS.copy()
		hdrs['access-key'] = WRX_ACCESS_KEY
		hdrs['api-key'] = WRX_API_KEY
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		price = self.buy_at
		
		payload = {
			'side': trade_side,
			'ord_type': 'limit',
			'price': price,
			'volume': self.qty,
			'market': market,
		}
	
		session = requests.session()
	
		p = session.post(WRX_ORDER_URL, headers=hdrs, json=payload, timeout=REQ_TIMEOUT)
		jdata = json.loads(p.text)
	
		if "id" in jdata.keys():
			return jdata['id']
		
		if "Not enough" in jdata['message']:
			msg = "Low balance alert - \n" 
			msg += "While " + trade_side + " " + market 
			print(msg)
			# TODO: Enable notifications
			#self.send_tg_alert(msg)
		return None

	def wrx_cancel_order(self, order_id):
		market = self.base.lower() + self.quote.lower()
		order_type = "limit"
		ts = str(int(time.time() * 1000))
		WRX_ACCESS_KEY = self.cfg['WRX_ACCESS_KEY']
		WRX_API_KEY = self.cfg['WRX_API_KEY']
		WRX_SECRET_KEY = self.cfg['WRX_SECRET_KEY']
	
		sign_str = "POST|access-key="+WRX_ACCESS_KEY+"&tonce="+ts+ "|/api/v2/order/delete|";
		signature = hmac.new(str.encode(WRX_SECRET_KEY), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = WRX_HEADERS.copy()
		hdrs['access-key'] = WRX_ACCESS_KEY
		hdrs['api-key'] = WRX_API_KEY
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
	
		payload = {
			'id': order_id
		}
	
		session = requests.session()
	
		p = session.post(WRX_CANCEL_ORDER_URL, headers=hdrs, json=payload, timeout=REQ_TIMEOUT)


	def wrx_get_order_status(self, order_id):
		if not order_id:
			return False, None
		
		market = self.base.lower() + self.quote.lower()
	
		session = requests.session()
		ts = str(int(time.time() * 1000))

		WRX_ACCESS_KEY = self.cfg['WRX_ACCESS_KEY']
		WRX_API_KEY = self.cfg['WRX_API_KEY']
		WRX_SECRET_KEY = self.cfg['WRX_SECRET_KEY']
	
		sign_str = "GET|access-key="+WRX_ACCESS_KEY+"&tonce="+ts+ "|/api/v2/orders|limit=30&order_by=desc";
		signature = hmac.new(str.encode(WRX_SECRET_KEY), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = WRX_HEADERS.copy()
		hdrs['access-key'] = WRX_ACCESS_KEY
		hdrs['api-key'] = WRX_API_KEY
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		p = session.get(WRX_ORDER_URL+"?limit=30&order_by=desc", headers=hdrs, timeout=REQ_TIMEOUT)
		jdata = json.loads(p.text)
	
		for order in jdata:
			if order['id'] != order_id:
				continue
			#return order['state'], float(order['executed_volume'])
			return order['state'], float(order['funds_received']), float(order['avg_price']), float(order['origin_locked'])

		return False, None, None, None


	def wrx_wait_for_confirmation(self, order_id, count = 15):
		if not order_id:
			return False
		
		market = self.base.lower() + self.quote.lower()
	
		# wait for 15 * 2 sec to confirm buy order
		while count:
			count -= 1
			try:
				status, executed_volume, avg_price, locked = self.wrx_get_order_status(order_id)
				if status == "done":
					return executed_volume, avg_price, locked
			except Exception as e:
				print("Failed to fetch order status")
				executed_volume = 0
	
			time.sleep(5)
	

		if executed_volume > 0:
			#self.wrx_cancel_order(order_id)
			return executed_volume, avg_price, locked

		#self.wrx_cancel_order(order_id)
		return False, False, False

	def wrx_transfer_fund_to_binance(self, base, qty):
		market = base.lower() 
		ts = str(int(time.time() * 1000))

		WRX_ACCESS_KEY = self.cfg['WRX_ACCESS_KEY']
		WRX_API_KEY = self.cfg['WRX_API_KEY']
		WRX_SECRET_KEY = self.cfg['WRX_SECRET_KEY']
		WRX_TOTP_KEY = self.cfg['WRX_TOTP_KEY']
	
		url = "https://x.wazirx.com/api/v2/thirdparty/asset_transfer/init"
		sign_str = "POST|access-key="+WRX_ACCESS_KEY+"&tonce="+ts+ "|/api/v2/thirdparty/asset_transfer/init|";
		signature = hmac.new(str.encode(WRX_SECRET_KEY), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = WRX_HEADERS.copy()
		hdrs['access-key'] = WRX_ACCESS_KEY
		hdrs['api-key'] = WRX_API_KEY
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
	
		payload = {
			'amount': qty,
			'currency': base.lower()
		}
	
		session = requests.session()
	
		p = session.post(url, headers=hdrs, json=payload, timeout=REQ_TIMEOUT)
		print(p.text)

		jdata = json.loads(p.text)
		print(jdata)

		if "2fa" not in jdata:
			return False
		code = jdata['2fa']['code']


		# Genereate TOPT
		totp = pyotp.TOTP(WRX_TOTP_KEY)
		totp = totp.now()
		print("OTP:", totp)

		# Send 2fa request
		url = "https://x.wazirx.com/api/v2/thirdparty/asset_transfer/verify_2fa"

		ts = str(int(time.time() * 1000))
		sign_str = "POST|access-key="+WRX_ACCESS_KEY+"&tonce="+ts+ "|/api/v2/thirdparty/asset_transfer/verify_2fa|";
		signature = hmac.new(str.encode(WRX_SECRET_KEY), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = WRX_HEADERS.copy()
		hdrs['access-key'] = WRX_ACCESS_KEY
		hdrs['api-key'] = WRX_API_KEY
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	

	
		payload = {
			'token': totp,
			'type': "Token::Authenticator",
			'platform[label]': "web",
			'code': code
		}
	
		session = requests.session()
	
		p = session.post(url, headers=hdrs, json=payload, timeout=REQ_TIMEOUT)
		print(p.text)
		jdata = json.loads(p.text)
		if "code" in jdata and jdata['code'] == 94026:
			# OPT already used
			return False

		if jdata['status'] != "SUCCESS":
			return False

		return True

	def get_pricelot_format(self, symbol, response, priceOrg, quantityOrg):
		price = float(priceOrg)
		quantity = float(quantityOrg)
		#response = self.get_symbol_info(car.pair) #self is client btw
		priceFilterFloat = format(float(response["filters"][0]["tickSize"]), '.20f')
		lotSizeFloat = format(float(response["filters"][2]["stepSize"]), '.20f')
		# PriceFilter
		numberAfterDot = str(priceFilterFloat.split(".")[1])
		indexOfOne = int(numberAfterDot.find("1"))
		if indexOfOne == -1:
			price1 = int(price)
			price = int(price)
		else:
			price1 = math.floor(price * 10**indexOfOne) / float(10**indexOfOne)
			#price = round(float(price), int(indexOfOne - 1))
			price = '{:0.0{}f}'.format(price, int(indexOfOne - 1))
		# LotSize
		numberAfterDotLot = str(lotSizeFloat.split(".")[1])
		indexOfOneLot = int(numberAfterDotLot.find("1"))
		if indexOfOneLot == -1:
			quantity1 = int(quantity)
			quantity = int(quantity)
		else:
			#quantity = round(float(quantity), int(indexOfOneLot))
			quantity1 = math.floor(quantity * 10**indexOfOneLot) / float(10**indexOfOneLot)
			quantity = '{:0.0{}f}'.format(quantity, int(indexOfOneLot))

		price1 = format_float_positional(price1, trim='-')
		quantity1 = format_float_positional(quantity1, trim='-')
		print(f"""
		##### SELL #####
		Pair : {str(symbol)}
		Cash : {str(price)}
		Quantity : {str(quantity)}
		Price : {str(price)}
		Quantity1 : {str(quantity1)}
		Price1 : {str(price1)}
	
		    """)
	
		return price1,  quantity1




