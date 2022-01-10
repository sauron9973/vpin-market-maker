# -*- coding: utf-8 -*-

from os.path import join
import logging

# Program Version
VERSION = '1.0'

# Setting Log
LOG_DIR = './logs'
LOG_NAME = 'vpin'
LOG_LEVEL = logging.INFO

# If any of these files (and this file) changes, reload the bot.
WATCHED_FILES = [join(".", f) for f in ["config/constants.py", __file__]]

# BITHUMB EXCHANGE_INFO
BITHUMB_BASE_URL = "https://api.bithumb.com"
BITHUMB_API_KEY = "api-key"
BITHUMB_API_SECRET = "secret-key"
BITHUMB_BTC_SYMBOL = "BTC"

# BITMEX EXCHANGE_INFO
BITMEX_BASE_URL = "https://www.bitmex.com/api/v1"
BITMEX_WSS_URL = "wss://www.bitmex.com"
BITMEX_API_KEY = "IhS6b8cLf64arhVL09M3T4cz"
BITMEX_API_SECRET = "o42TjXY2g_RwCSnbORglkF_wb-B6lArulw1aBabOuvraK2xN"
BITMEX_BTC_SYMBOL = "XBTUSD"
BITMEX_ORDERID_PREFIX = "mm_bitmex_"

XBt_TO_XBT = 100000000
CONTRACTS = ['XBTUSD']
MIN_CONTRACTS = 5000

RANDOM_ORDER_SIZE = False
MIN_ORDER_SIZE = 1
MAX_ORDER_SIZE = 10

ORDER_PAIRS = 1
ORDER_START_SIZE = 300
ORDER_STEP_SIZE = 300

INTERVAL = 0.005
MIN_SPREAD = 0.01
MAINTAIN_SPREADS = True
RELIST_INTERVAL = 0.01

CHECK_POSITION_LIMITS = True
MIN_POSITION = -5000
MAX_POSITION = 5000

# INTERVAL
LOOP_INTERVAL = 5
API_REST_INTERVAL = 1
API_ERROR_INTERVAL = 10

# CHART
CHART_UNITS = 1000000
LONG_WINDOW_SIZE = 30
MID_WINDOW_SIZE = 10
SHORT_WINDOW_SIZE = 5
