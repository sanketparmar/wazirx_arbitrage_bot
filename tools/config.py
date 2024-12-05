DEFAULT_CONFIG = {
	'TG_ALD_API_KEY': "",
	'TG_ALD_GRP_ID': "",
	
	# WazirX API 
	'WRX_ACCESS_KEY': "",
	'WRX_SECRET_KEY': "",
	'WRX_API_KEY': "",
	
	'WRX_MIN_INR_LIMIT': 50,
	'WRX_MIN_USDT_LIMIT': 2,
	'WRX_MIN_WRX_LIMIT': 50,
	
	# INR LIMIT PER TRADE
	'INR_TRADE_LIMIT': 10000,
	
	# Expected profit per trade in INR
	'MIN_EXPECTED_PROFIT_INR': 80,
	
	# Expected profit per trade in USDT
	'MIN_EXPECTED_PROFIT_USDT': 1,
	
	# THRESHOLD differnce PERC
	'THRESHOLD_DIFF_PERC': 0.8,
	
	# Banned tocken lists

	'SKIP_QUOTE_TOKENS': ["btc", 'wrx'],
	'SKIP_BASE_TOKENS': [],

	# Request delay in sec
	'SLEEP_TIME': 0.5, 
	
	# REQUEST TIMEOUT (connect, read) 
	'REQ_TIMEOUT': (5, 10),
	
	# MAX active threads 
	'MAX_ACTIVE_THREADS': 5,

}
