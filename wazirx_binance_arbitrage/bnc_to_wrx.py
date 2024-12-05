from threading import Thread
import threading
import time
import requests
import json
import hmac
import hashlib
import pyotp
import traceback
from binance.client import Client as BinanceClient
from mywazirx import wazirx_client
from mybinance import bnc_send_verification_mail, bnc_get_otp_from_gmail

class bnc_trade_manager(Thread):
	def __init__(self, logger, lock, cfg, base, quote, buy_at, sell_at, qty, xferable):
		Thread.__init__(self)
		self.name = "bnc_to_wrx|" + base
		self.base = base
		self.quote = quote
		self.buy_at = buy_at
		self.sell_at = sell_at
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
		self.bnc_cookie = self.cfg["BNC_COOKIE"]

		self.bnc_email = self.cfg["BNC_EMAIL"]
		self.gmail_app_password = self.cfg["GMAIL_APP_PASSWORD"]
		self.bnc_totp_key = self.cfg["BNC_TOTP_KEY"]
	
	def run(self):
		try:
			self.lock.acquire()
			print("Running thread ", self.name)

			buy_vol = self.bnc_get_volume()
			sell_vol = self.wrx_client.get_volume("sell", self.base, self.quote, self.sell_at)

			qty = min(buy_vol, sell_vol, self.qty)

			if qty <= 0:
				print("No buyer or seller. Terminating thread:", self.name)
				self.lock.release()
				return 
				
			exp_profit = (qty * self.sell_at) - (qty * self.buy_at)
			print("Expected profit: ", exp_profit, "USDT")
			if exp_profit < self.min_expected_profit_usdt:
				print("Low profit", exp_profit, "USDT")
				self.lock.release()
				return

			self.qty = qty

			# Place buy order 
			print("Placing buy order on binance")
			symbol = self.base.upper() + self.quote.upper()
			# GET symbol price 
			symbol_info = self.bnc_client.get_symbol_info(symbol=symbol)
			price_precision, qty_precision = self.get_pricelot_format(symbol, symbol_info, self.buy_at, self.qty)

			if float(qty_precision) > self.qty:
				qty_precision = self.qty

			# Place limit order with profit
			order = self.bnc_client.order_limit_buy(
				symbol=symbol,
				quantity=qty_precision,
				price=price_precision)
		
			print("Placed buy limit order", order)
			if "orderId" not in order or not order["orderId"]:
				print("Failed to place buy order")
				self.lock.release()
				return 

			order_id = order["orderId"]
			# Wait for confirmation 
			wait = 30 # Sec
			count = wait / 5 
			confirmed_qty = 0
			pending_qty = 0
			while count:
				count -= 1
				try:
					order = self.bnc_client.get_order(symbol=symbol, orderId=order_id)

					confirmed_qty = float(order['executedQty'])
					pending_qty = float(order['origQty']) - confirmed_qty
					status = order["status"]

					if status == "FILLED":
						break
				except Exception as e:
					print("Order doen't exist", e)
				time.sleep(5)

			if not confirmed_qty or (confirmed_qty < (self.qty * 0.7)):
				# cancel order
				print("Failed to confirm buy order...canceling the order")
				self.bnc_client.cancel_order(symbol=symbol, orderId=order_id)
				if confirmed_qty:
					# TODO: Sell of ??
					pass

				self.lock.release()
				return

			if confirmed_qty < self.qty:
				self.bnc_client.cancel_order(symbol=symbol, orderId=order_id)
				print("Confirmed buy volume is low than ordered. Confirmed:" + str(confirmed_qty) + " Odered: " + str(self.qty))

			self.qty = confirmed_qty

			# Send email for xfer
			ret = bnc_send_verification_mail(self.base, self.qty, self.bnc_cookie)
			if not ret:
				print("Failed to send mail verification code")
				#TODO: Sell of ???
				self.lock.release()
				return

			# Get otp from mail 
			time.sleep(10)
			otp = bnc_get_otp_from_gmail(self.bnc_email, self.gmail_app_password)
			if not otp:
				print("Failed to send mail verification code")
				#TODO: Sell of ???
				self.lock.release()
				return

			# gen totp for xfer 

			totp = pyotp.TOTP(self.bnc_totp_key)
			totp = totp.now()
			print("OTP:", totp)

			# send fund to wazirx
			ret = bnc_xfer_funds(self.base, self.qty, cookie, otp, totp)
			print("Xfer fund output:", ret)

			# verify fund to wazirx
			wait = 15 # sec
			count = wait / 5 
			bal = 0
			while count:
				count -= 1
				bal = self.wrx_client.get_asset_balance(self.base)
				if bal >= self.qty:
					break
				time.sleep(5)
				
			if bal == 0:
				print("Failed to confirm balance at wazirx")
				#TODO: Sell of ???
				self.lock.release()
				return

			# Place sell order
			order_id, msg = self.wrx_client.place_order("sell", self.base, self.quote, self.sell_at, self.qty)
			print("Placed sell order on wazirx,", order_id, msg)

		except Exception as e:
			track = traceback.format_exc()
			print("Exception in thread", self.name)
			print(track)
			if self.lock.locked():
				self.lock.release()

	def bnc_get_volume(self):
		market = self.base.upper() + self.quote.upper()
		limit = 10
		price = self.buy_at
		trade_side = "buy"
		jdata = self.bnc_client.get_order_book(symbol=market, limit=limit)
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

	def get_pricelot_format(self, symbol, response, priceOrg, quantityOrg):
		price = float(priceOrg)
		quantity = float(quantityOrg)
		#response = self.get_symbol_info(car.pair) #self is client btw
		priceFilterFloat = format(float(response["filters"][0]["tickSize"]), '.20f')
		lotSizeFloat = format(float(response["filters"][2]["stepSize"]), '.20f')
		# PriceFilter
		numberAfterDot = str(priceFilterFloat.split(".")[1])
		indexOfOne = numberAfterDot.find("1")
		if indexOfOne == -1:
			price = int(price)
		else:
			price = round(float(price), int(indexOfOne - 1))
			price = '{:0.0{}f}'.format(price, int(indexOfOne - 1))
		# LotSize
		numberAfterDotLot = str(lotSizeFloat.split(".")[1])
		indexOfOneLot = numberAfterDotLot.find("1")
		if indexOfOneLot == -1:
			quantity = int(quantity)
		else:
			#quantity = round(float(quantity), int(indexOfOneLot))
			quantity = '{:0.0{}f}'.format(quantity, int(indexOfOneLot))
		print(f"""
		##### SELL #####
		Pair : {str(symbol)}
		Cash : {str(price)}
		Quantity : {str(quantity)}
		Price : {str(price)}
		    """)
	
		return price,  quantity
