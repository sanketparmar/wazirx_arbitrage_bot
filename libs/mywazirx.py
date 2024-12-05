import requests
import json
from datetime import datetime
import hmac
import hashlib
import time
import traceback
import pyotp

#WazriX API URLS
WRX_TICKER_URL = "https://x.wazirx.com/api/v2/tickers"
WRX_CREATE_ORDER_URL = "https://x.wazirx.com/api/v3/order"
WRX_GET_ORDERS_URL = "https://x.wazirx.com/api/v3/orders"
WRX_GET_ORDER_URL = "https://x.wazirx.com/api/v3/order"
WRX_CANCEL_ORDER_URL = "https://x.wazirx.com/api/v2/order/delete"
WRX_DEPTH_URL = "https://x.wazirx.com/api/v2/depth"
WRX_XFERABLE_TOKEN_URL = "https://x.wazirx.com/api/v2/thirdparty/asset_transfer/currencies?thirdparty=binance"
WRX_FUND_TRANSFER_INIT_URL = "https://x.wazirx.com/api/v2/thirdparty/asset_transfer/init"
WRX_VERIFY_2FA_URL = "https://x.wazirx.com/api/v2/thirdparty/asset_transfer/verify_2fa"
WRX_FUND_BALANCE = "https://x.wazirx.com/api/v2/funds"
WRX_GLOBAL_CONFIG_URL = "https://x.wazirx.com/api/v2/global_configs"

class wazirx_client:
	def __init__(self, logger, access_key, secret_key, api_key, totp_key= None, timeout = (10,10)):
		self.logger = logger
		self.access_key = access_key
		self.secret_key = secret_key
		self.api_key = api_key
		self.totp_key = totp_key
		self.req_timeout = timeout

		self.headers = {
			"Host": "x.wazirx.com",
			"Connection": "keep-alive",
			"access-key": self.access_key,
			"api-key": self.api_key,
			#"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36",
			"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 10; RMX1851 Build/QKQ1.190918.001)",
			"DNT": "1",
			"content-type": "application/json",
			"Accept": "/",
			"Origin": "https://wazirx.com",
			"Sec-Fetch-Site": "same-site",
			"Sec-Fetch-Mode": "cors",
			"Sec-Fetch-Dest": "empty",
			"Referer": "https://wazirx.com/",
			"Accept-Language": "en-US,en;q=0.9",
		}

	def get_ticker_data(self):
		ses = requests.session()
		p = ses.get(WRX_TICKER_URL, timeout=self.req_timeout)
		jdata = json.loads(p.text)

		return jdata

	def place_order(self, side, base, quote, limit_price, volume, order_type = "limit"):
		market = base.lower() + quote.lower()
		self.logger.debug("Placing" + side + " order. Currency:" + market + " price:" + str(limit_price) + "volume:" + str(volume))

		ts = str(int(time.time() * 1000))
		sign_str = "POST|access-key="+self.access_key+"&tonce="+ts+ "|/api/v3/order|";
		signature = hmac.new(str.encode(self.secret_key), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = self.headers.copy()
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		payload = {
			'side': side,
			'ord_type': order_type,
			'price': limit_price,
			'volume': volume,
			'market': market,
		}
	
		session = requests.session()
	
		p = session.post(WRX_CREATE_ORDER_URL, headers=hdrs, json=payload, timeout=self.req_timeout)
		jdata = json.loads(p.text)
		self.logger.debug(market + " " + side +" order return data:" + str(jdata))
	
		if "id" in jdata.keys():
			order_id = jdata['id']
			msg = "Success"

		else:
			order_id = None
			msg = jdata['message']

		return order_id, msg


	def cancel_order(self, order_id):
		self.logger.debug("Canceling order:" + str(order_id))
		ts = str(int(time.time() * 1000))
		sign_str = "POST|access-key="+self.access_key+"&tonce="+ts+ "|/api/v2/order/delete|";
		signature = hmac.new(str.encode(self.secret_key), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = self.headers.copy()
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
	
		payload = {
			'id': order_id
		}
	
		session = requests.session()
	
		p = session.post(WRX_CANCEL_ORDER_URL, headers=hdrs, json=payload, timeout=self.req_timeout)
		self.logger.debug("Cancel order id return data:" + str(p.text))
	
	def get_order_status(self, order_id):
		if not order_id:
			return False, None, None, None
		
		session = requests.session()
		ts = str(int(time.time() * 1000))
		param = "id="+str(order_id)+"&need_trades=false"
		sign_str = "GET|access-key="+self.access_key+"&tonce="+ts+ "|/api/v3/order|"+param;
		signature = hmac.new(str.encode(self.secret_key), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = self.headers.copy()
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		p = session.get(WRX_GET_ORDER_URL+"?"+param, headers=hdrs, timeout=self.req_timeout)
		order = json.loads(p.text)
	
		if "state" in order:
			self.logger.debug("Order status:" + str(order))
			state = order['state']
			pending_vol = float(order['volume'])
			executed_vol = float(order['origin_volume']) - pending_vol
			quote_vol = executed_vol * float(order['avg_price'])
			return state, executed_vol, pending_vol, quote_vol

		return False, None, None, None


	def wait_for_confirmation(self, order_id, wait = 30):
		
		if not order_id:
			return False
		sleep_sec = 5 
		count = wait / sleep_sec	
		executed_vol = 0
		pending_vol = 0
		quote_vol = 0
		while count:
			count -= 1
			try:
				status, executed_vol, pending_vol, quote_vol = self.get_order_status(order_id)
				if status == "done":
					#return executed_volume, pending_vol
					return executed_vol, pending_vol, quote_vol
			except Exception as e:
				self.logger.error("Exception while fetching order status for " + str(order_id))
				track = traceback.format_exc()
				print(track)
				executed_volume = 0
	
			time.sleep(sleep_sec)

		return executed_vol, pending_vol, quote_vol

	def get_volume(self, side, base, quote, price):
		market = base.lower() + quote.lower()
		ts = str(int(time.time() * 1000))
	
		session = requests.session()
		sign_str = "GET|access-key="+self.access_key+"&tonce="+ts+ "|/api/v2/depth|limit=10&market="+market;
		signature = hmac.new(str.encode(self.secret_key), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = self.headers.copy()
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		p = session.get(WRX_DEPTH_URL+"?limit=10&market="+market, headers=hdrs, timeout=self.req_timeout)
		jdata = json.loads(p.text)
	
		volume = 0
		if side == "buy":
			for e in jdata['asks']:
				if  float(e[0]) <= price:
					volume += float(e[1])
				
		elif side == "sell":
			for e in jdata['bids']:
				if float(e[0]) >= price:
					volume += float(e[1])
				
		#print(market, trade_side, price, volume)
		return volume

	def get_price(self, side, base, quote, price):
		market = base.lower() + quote.lower()
		ts = str(int(time.time() * 1000))
	
		session = requests.session()
		sign_str = "GET|access-key="+self.access_key+"&tonce="+ts+ "|/api/v2/depth|limit=10&market="+market;
		signature = hmac.new(str.encode(self.secret_key), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = self.headers.copy()
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		p = session.get(WRX_DEPTH_URL+"?limit=10&market="+market, headers=hdrs, timeout=self.req_timeout)
		jdata = json.loads(p.text)
	
		price = 0
		if side == "buy":
			# buy at others are buying 
			#depth_data = jdata['asks']
			depth_data = jdata['bids']
			return depth_data[0][0]
		else:
			# sell at others are selling
			#depth_data = jdata['bids']
			depth_data = jdata['asks']
			return depth_data[0][0]
	
		# TODO: Do we need this ? 
		for e in depth_data:
			print(e)
			if  vol <= float(e[1]):
				price = float(e[0])
				break
				
			vol -= float(e[1])
					
		return price

	def get_bnc_xferable_tokens(self):
		ts = str(int(time.time() * 1000))
	
		session = requests.session()
		sign_str = "GET|access-key="+self.access_key+"&tonce="+ts+ "|/api/v2/thirdparty/asset_transfer/currencies|thirdparty=binance"

		signature = hmac.new(str.encode(self.secret_key), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = self.headers.copy()
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		p = session.get(WRX_XFERABLE_TOKEN_URL, headers=hdrs, timeout=self.req_timeout)
		jdata = json.loads(p.text)
	
		allowed_bnc_withrawals = []
		for t in jdata['allowedCurrencies']:
			allowed_bnc_withrawals.append(t['code'])
		
		#print("Before removingf c['type'] in allowed_bnc_withrawals:if c['type'] in allowed_bnc_withrawals: withrawl:", allowed_bnc_withrawals)
		# Remove disabled one from main list
		#g_conf_data = self.get_global_config()

		#for c in g_conf_data['currencies']:
		#	if c['category'] != 'crypto':
		#		continue

		#	if c['type'] not in allowed_bnc_withrawals:
		#		continue

		#	if "disableWithdrawal" in c and c['disableWithdrawal']:
		#		allowed_bnc_withrawals.remove(c['type'])
		#		continue

		#	print("VALID: ", c)

		##print("After removing withrawl:", allowed_bnc_withrawals)
		return allowed_bnc_withrawals


	def transfer_fund_to_binance(self, base, qty, totp_key):
		ts = str(int(time.time() * 1000))

		sign_str = "POST|access-key="+self.access_key+"&tonce="+ts+ "|/api/v2/thirdparty/asset_transfer/init|"
		signature = hmac.new(str.encode(self.secret_key), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = self.headers.copy()
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		payload = {
			'amount': qty,
			'currency': base.lower()
		}
	
		session = requests.session()
	
		p = session.post(WRX_FUND_TRANSFER_INIT_URL, headers=hdrs, json=payload, timeout=self.req_timeout)
		print(p.text)

		jdata = json.loads(p.text)
		print(jdata)

		if "2fa" not in jdata:
			return False
		code = jdata['2fa']['code']

		# Genereate TOPT
		totp = pyotp.TOTP(totp_key)
		totp = totp.now()
		print("OTP:", totp)

		ts = str(int(time.time() * 1000))
		sign_str = "POST|access-key="+self.access_key+"&tonce="+ts+ "|/api/v2/thirdparty/asset_transfer/verify_2fa|"
		signature = hmac.new(str.encode(self.secret_key), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = self.headers.copy()
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		payload = {
			'token': totp,
			'type': "Token::Authenticator",
			'platform[label]': "web",
			'code': code
		}
	
		session = requests.session()
	
		p = session.post(WRX_VERIFY_2FA_URL, headers=hdrs, json=payload, timeout=self.req_timeout)
		print(p.text)
		jdata = json.loads(p.text)
		if "code" in jdata:
			if jdata['code'] == 94026:
				# OPT already used
				return "RETRY"
			else:
				# NOT TRANSFERABLE
				return False

		if jdata['status'] != "SUCCESS":
			return False

		return True

	def get_fund_info(self):
		ts = str(int(time.time() * 1000))
	
		session = requests.session()
		sign_str = "GET|access-key="+self.access_key+"&tonce="+ts+ "|/api/v2/funds|"

		signature = hmac.new(str.encode(self.secret_key), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = self.headers.copy()
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		p = session.get(WRX_FUND_BALANCE, headers=hdrs, timeout=self.req_timeout)
		jdata = json.loads(p.text)
	
		return jdata
	
	def get_global_config(self):
		ts = str(int(time.time() * 1000))
	
		session = requests.session()
		sign_str = "GET|access-key="+self.access_key+"&tonce="+ts+ "|/api/v2/global_configs|"

		signature = hmac.new(str.encode(self.secret_key), str.encode(sign_str), hashlib.sha256).hexdigest()
	
		hdrs = self.headers.copy()
		hdrs['tonce'] = ts
		hdrs['signature'] = signature
	
		p = session.get(WRX_GLOBAL_CONFIG_URL, headers=hdrs, timeout=self.req_timeout)
		jdata = json.loads(p.text)
	
		return jdata
	

	def get_asset_balance(self, base):

		jdata = self.get_fund_info()
		bal = 0
		for c in jdata:
			if base.lower() == c['currency']:
				bal = float(c["balance"])
				break
		return bal


	def get_portfolio_value(self):
		prices = self.get_ticker_data()
		asset_bal = self.get_fund_info()

		total_val = 0
		total_holding = 0
		for c in asset_bal:
			curr = c['currency']
			bal = float(c['balance']) + float(c['locked'])

			if bal > 0:
				total_holding += 1

			if curr == "inr":
				total_val += bal

			if curr+"inr" in prices:
				total_val += bal * float(prices[curr+'inr']['last'])
			elif curr+"usdt" in prices:
				total_val += bal * float(prices['usdtinr']['last']) * float(prices[curr+'usdt']['last'])
		return total_val, (total_holding - 3)  # -3 for inr, usdt, wrx

