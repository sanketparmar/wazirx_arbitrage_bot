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

	'WRX_ALLOWED_QUOTE_TOKENS': ["usdt", 'inr', 'wrx'],
	#'WRX_ALLOWED_QUOTE_TOKENS': ["usdt"],
	'WRX_SKIP_BASE_TOKENS': [],

	'BNC_ALLOWED_QUOTE_TOKENS': ['busd', 'eth', 'usdt', 'bnb', 'usdc'],
	#'BNC_ALLOWED_QUOTE_TOKENS': ['usdt'],
	'BNC_SKIP_BASE_TOKENS': [],

	# Request delay in sec
	'SLEEP_TIME': 0.5, 
	
	# REQUEST TIMEOUT (connect, read) 
	'REQ_TIMEOUT': (5, 10),
	
	# MAX active threads 
	'MAX_ACTIVE_THREADS': 5,

	# CONVERT ALLL PRICE TO 
	'CONV_UNIT': "usdt",


}


wrx_xferable_tokens = []
bnc_xferable_tokens = []

blocked_wrx_tokens = ["ltc", "uma", "mkr", "ray", "keep", "xmr", "mina", "mask", "trb", "gala", "dego", "tfuel", "ilv", "pundix", "alpha", "stmx", "lrc", "beta", "auction", "rsr", "agld", "super", "rose", "pnt", "mft", "vite", "rep", "tlm", "win", "dydx", "skl", "burger", "mir", "xec", "dnt", "icx", "qnt", "rad", "coti", "ar", "reef", "ogn", "dusk", "ardr", "ctsi", "lsk", "ont", "front", "sand", "wtc", "nbs", "luna", "ava", "klay", "inj", "matic", "bake", "qtum", "mbox", "icp", "crv", "audio", "nkn", "pha", "adx", "enj", "mtl", "ftm", "iotx", "sys", "ocean", "stpt", "perp", "dodo", "nu", "poly", "dent", "theta", "hnt", "mdx", "cfx", "gno", "flow", "chr", "usdc", "clv", "stx", "ata", "xyz", "dcr", "hot", "algo", "xlm", "waxp", "alpaca", "alice", "band", "rad", "agld", "gxs", "rare", "key", "xtz", "sc", "slp", "cocos", "chess", 'mln', 'near', 'grt', 'vgx']

BNC_XFERABLE_TOKEN_URL = "https://www.binance.com/bapi/asset/v1/public/asset-service/partner/supported-assets?clientId=aEd4v9Cd90"
BNC_TICKER_URL = "https://api.binance.com/api/v3/ticker/bookTicker"
