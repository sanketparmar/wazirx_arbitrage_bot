from threading import Thread
import time
import threading
import logging
from logging.handlers import RotatingFileHandler
from logging import handlers
from termcolor import colored
import sys
import requests
import imaplib, email
import re
import traceback
import json

def get_logger(appname, logfile, loglevel=logging.DEBUG, consolop=False): 
	logger = logging.getLogger(appname)
	logger.setLevel(logging.DEBUG)
	format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d: %(message)s")

	if logger.hasHandlers():
		return logger
	
	if consolop:
		ch = logging.StreamHandler(sys.stdout)
		ch.setFormatter(format)
		ch.setLevel(loglevel)
		logger.addHandler(ch)
	
	#fh = handlers.RotatingFileHandler(logfile, maxBytes=(1048576*5), backupCount=10)
	fh = handlers.TimedRotatingFileHandler(logfile, when='midnight', backupCount=30)
	fh.setFormatter(format)
	fh.setLevel(logging.DEBUG)
	logger.addHandler(fh)
	
	return logger
class tg_alert():
	def __init__(self, api_key, group_id):
		self.api_key = api_key
		self.group_id = group_id

	def send_alert(self, msg):
		session = requests.session()
		tg_url = 'https://api.telegram.org/bot'+self.api_key+'/sendMessage'
		data = {'chat_id': self.group_id, 'text': msg, 'parse_mode': 'html'}
		p = session.post(tg_url, data=data, timeout=(5,5))

	def get_bot_update(self):
		session = requests.session()
		tg_url = 'https://api.telegram.org/bot'+self.api_key+'/getUpdates'
		p = session.get(tg_url, timeout=(5,5))
		jdata = json.loads(p.text)

		if jdata["ok"]:
			return jdata["result"]

		else:
			return False



	
def printred(text):
	print(colored(text, 'red', attrs=['bold']))

def printgreen(text):
        print(colored(text, 'green', attrs=['bold']))

def printyellow(text):
	print(colored(text, 'yellow', attrs=['bold']))

def printgrey(text):
	print(colored(text, 'grey', attrs=['bold']))

def ctext(color, text, attrs=[]):
	return colored(text, color, attrs=attrs)


class Heartbeat(Thread):
	def __init__(self, name, title, timer = 600, send_notification = False, wrx_client = None):
		Thread.__init__(self)
		self.name = name 
		self.title = title
		self.timer = timer
		self.notifiation = send_notification
		self.wrx_client = wrx_client

	def run(self):
		msg = "***** "+ self.name + " Bot Restarted. Config:" + self.title
		while True:
			try:
				if self.notifiation:
					send_tg_alert(msg)
				else:
					printgreen(msg)

				msg = "HEART BEAT["+ self.name + "|" + self.title + " ]\nActive Thread count: " + str(threading.active_count())+"\n"
				if self.wrx_client:
					val, holdings = self.wrx_client.get_portfolio_value()
					msg += "Wazirx Portfolio: " + "{:.2f}".format(val) + " Rs. Total Holdings: " + str(holdings)+"\n"

				time.sleep(self.timer)
			except Exception as e:
				
				print("Exception in HB thread")
				track = traceback.format_exc()
				printyellow(track)
				pass


#def get_binance_otp_from_gmail(email, app_password):
#	imap_url = 'imap.gmail.com'
#	con = imaplib.IMAP4_SSL(imap_url)
#	con.login(email, app_password)
#	con.select('Inbox')
#
#	result, data = con.search(None, '(FROM "do-not-reply@directmail2.binance.com" SUBJECT "[Binance] Confirm Withdrawal/Transfer")')                                                                               
#
#	msgs = [] # all the email data are pushed inside an array
#	for num in data[0].split():
#		typ, data = con.fetch(num, '(RFC822)')
#		msgs.append(data)
#
#	msg = msgs[-1]
#	for sent in msg:
#		if type(sent) is tuple:
#			m = email.message_from_string(sent[1].decode("utf-8"))
#			body = m.get_payload(decode=True).decode("utf-8")
#			m = re.search('>(\d\d\d\d\d\d)<', body)
#			if not m:
#				return False
#			otp = m.group(1)
#			return otp
