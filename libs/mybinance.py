import requests
import json
from datetime import datetime
import hmac
import hashlib
import time
import traceback
import imaplib, email
import re



BNC_SEND_EMAIL_VERIFY_CODE_URL = "https://www.binance.com/bapi/accounts/v1/protect/account/email/sendEmailVerifyCode"
BNC_ASSET_XFER_URL = "https://www.binance.com/bapi/asset/v1/private/asset-service/partner/transfer"
REQ_TIMEOUT = (10, 10)

def bnc_send_verification_mail(base, qty, cookie):
	
	payload = {
		"bizScene":"FIAT_ASSET_WITHDRAW_CONFIRM",
		"msgType":"TEXT",
		"resend":False,
		"params": {
			"amount":str(qty),
			"asset":base.upper(),
			"clientName":"wazirx"
		}
	}

	print("payload", payload)
	hdrs = {                                                                
		"cookie": cookie,                                               
		'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36', 
		"clienttype": "web",                                            
	}                                                                       
	                                                                        
	session = requests.session()                                            
	p = session.post(BNC_SEND_EMAIL_VERIFY_CODE_URL, headers=hdrs, json=payload, timeout=REQ_TIMEOUT) 
	print(p.text)                                                           
	jdata = json.loads(p.text)                                              
	return jdata["success"] 

def bnc_xfer_funds(base, qty, cookie, email_otp, totp):

	payload = {
		"asset": base.upper(),
		"amount": str(qty),
		"clientId": "aEd4v9Cd90",
		"emailVerifyCode": str(email_otp),
		"googleVerifyCode": str(totp),
	}
	hdrs = {                                                                
		"cookie": cookie,                                               
		'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36', 
		"clienttype": "web",                                            
	}                                                                       
	                                                                        
	print("payload", payload)
	session = requests.session()                                            
	p = session.post(BNC_ASSET_XFER_URL, headers=hdrs, json=payload, timeout=REQ_TIMEOUT) 
	print(p.text)                                                           
	jdata = json.loads(p.text)                                              
	return jdata["success"] 


def bnc_get_otp_from_gmail(email, app_password):
	imap_url = 'imap.gmail.com'
	con = imaplib.IMAP4_SSL(imap_url)
	con.login(email, app_password)
	con.select('Inbox')

	result, data = con.search(None, '(FROM "do-not-reply@directmail2.binance.com" SUBJECT "[Binance] Confirm Withdrawal/Transfer")')                                                                               

	msgs = [] # all the email data are pushed inside an array
	for num in data[0].split():
		typ, data = con.fetch(num, '(RFC822)')
		msgs.append(data)

	msg = msgs[-1]
	for sent in msg:
		if type(sent) is tuple:
			m = email.message_from_string(sent[1].decode("utf-8"))
			body = m.get_payload(decode=True).decode("utf-8")
			m = re.search('>(\d\d\d\d\d\d)<', body)
			if not m:
				return False
			otp = m.group(1)
			return otp
