# -*- coding: utf-8 -*-

import os
import sys
import atexit
import signal
import requests
import random
from time import sleep
from utils import errors, math
from os.path import getmtime
from config.settings import settings
from exchange.exchange_interface import ExchangeInterface


class TradeManager(object):
    ###
    # Init
    ###

    def __init__(self, logger):
        self.logger = logger

        self.symbol = settings.BITMEX_BTC_SYMBOL
        self.interface = ExchangeInterface(self.logger)
        self.watched_files_mtimes = [(f, getmtime(f)) for f in settings.WATCHED_FILES]
        self.starting_qty = 0
        self.running_qty = 0
        self.start_XBt = 0
        self.instrument = None
        self.cur_market_rate = 0.0
        self.prev_market_rate = 0.0
        self.start_position_buy = 0
        self.start_position_sell = 0
        self.start_position_mid = 0

        # register exit handler that will always cancel orders on any error.
        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

        self.logger.info("Using symbol bitmex(%s)." % self.symbol)

    ###
    # Running
    ###

    def init(self):
        """
        init vpin market making trading system
        """

        self.logger.info("Trade Manager initializing")

        self.instrument = self.interface.get_instrument(self.symbol)
        self.starting_qty = self.interface.get_delta(self.symbol)
        self.running_qty = self.starting_qty
        self.interface.cancel_all_orders(self.symbol)

    def exit(self):
        """
        exit vpin market making trading system
        """

        self.logger.info("Shutting down. All open orders will be cancelled.")

        try:
            self.interface.cancel_all_orders(self.symbol)
            self.interface.exit()
        except errors.AuthenticationError as e:
            self.logger.info("Was not authenticated; could not cancel orders.")
        except Exception as e:
            self.logger.info("Unable to cancel orders: %s" % e)

    def restart(self):
        """
        Restart vpin market making trading system.
        """

        self.logger.info("Restarting the vpin market making Trading System...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def print_status(self):
        margin = self.interface.get_margin()
        position = self.interface.get_position(self.symbol)
        self.running_qty = self.interface.get_delta(self.symbol)
        self.start_XBt = margin["marginBalance"]

        self.logger.info("Current XBT Balance: %.6f" % self.XBt_to_XBT(self.start_XBt))
        self.logger.info("Current Contract Position: %d" % self.running_qty)
        self.logger.info("Position limits: %d / %d" % (settings.MIN_POSITION, settings.MAX_POSITION))
        if self.short_position_limit_exceeded():
            self.logger.warn(">>> Short delta limit exceeded")
            self.logger.warn("    Current Position: %.f, Minimum Position: %.f" %
                             (self.interface.get_delta(self.symbol), settings.MIN_POSITION))
        if self.long_position_limit_exceeded():
            self.logger.warn(">>> Long delta limit exceeded")
            self.logger.warn("    Current Position: %.f, Maximum Position: %.f" %
                             (self.interface.get_delta(self.symbol), settings.MAX_POSITION))

        if position['currentQty'] != 0:
            self.logger.info("Avg Market Price: %.2f" % float(position['markPrice']))
            self.logger.info("Avg Entry Price: %.2f" % float(position['avgEntryPrice']))
            self.logger.info("Margin Call Price: %.2f" % float(position['marginCallPrice']))
        self.logger.info("Contracts Traded This Run: %d" % (self.running_qty - self.starting_qty))
        self.logger.info("Total Contract Delta: %.4f XBT" % self.interface.calc_delta()['spot'])

    def run_loop(self):
        """
        market making trading Main Loop
        """

        while True:
            # Restart if any files we're watching have changed
            self.check_file_change()

            sleep(settings.LOOP_INTERVAL)

            # Check that websocket are still open.
            if not self.interface.is_ws_open():
                self.logger.error("Realtime data connection unexpectedly closed, restarting.")
                self.restart()

            # Print skew, delta, etc
            self.print_status()

            # Ensure market is still open.
            if self.interface.check_market_not_open(self.symbol):
                continue

            # Check if order book is empty - if so, can't quote.
            if self.interface.check_if_orderbook_empty(self.symbol):
                continue

            # Ensure enough liquidity on each side of the order book
            if not self.enough_liquidity():
                continue

            # Get signal from Reinforcement Learning Agent
            sell_action, buy_action = self.get_rl_action()
            if sell_action == 9:
                return

            # Creates desired orders and converges to existing orders
            # self.place_orders()

    def check_file_change(self):
        """
        Restart if any files we're watching have changed.
        """

        for f, mtime in self.watched_files_mtimes:
            if getmtime(f) > mtime:
                self.logger.info(f + " was changed..., restarting")
                self.restart()

    def enough_liquidity(self):
        """
        Returns true if there is enough liquidity on each side of the order book
        """

        order_book = self.interface.get_market_depth(self.symbol)
        ask_liquid = sum([x[1] for x in order_book['asks']])
        bid_liquid = sum([x[1] for x in order_book['bids']])
        # self.logger.info("Ask Liquidity: " + str(ask_liquid) + " Contracts")
        # self.logger.info("Bid Liquidity: " + str(bid_liquid) + " Contracts")

        enough_ask_liquidity = ask_liquid >= settings.MIN_CONTRACTS
        enough_bid_liquidity = bid_liquid >= settings.MIN_CONTRACTS
        enough_liquidity = (enough_ask_liquidity and enough_bid_liquidity)
        if not enough_liquidity:
            if (not enough_bid_liquidity) and (not enough_ask_liquidity):
                self.logger.info("Neither side has enough liquidity")
            elif not enough_bid_liquidity:
                self.logger.info("Bid side is not liquid enough")
            else:
                self.logger.info("Ask side is not liquid enough")
        return enough_liquidity

    def short_position_limit_exceeded(self):
        """
        Returns True if the short position limit is exceeded
        """

        position = self.interface.get_delta(self.symbol)
        return position <= settings.MIN_POSITION

    def long_position_limit_exceeded(self):
        """
        Returns True if the long position limit is exceeded
        """

        position = self.interface.get_delta(self.symbol)
        return position >= settings.MAX_POSITION

    def get_rl_action(self):
        vpin, bounce = self.interface.get_latest_vpin()
        print('vpin = %.2f bounce = %.2f' % (vpin, bounce))

        sell_action = 0
        buy_action = 0

        return sell_action, buy_action

    #
    # Helpers
    #

    def XBt_to_XBT(self, XBt):
        return float(XBt) / settings.XBt_TO_XBT

    def cost(self, instrument, quantity, price):
        multiplier = instrument["multiplier"]
        p = multiplier * price if multiplier >= 0 else multiplier / price
        return abs(quantity * p)

    def margin(self, instrument, quantity, price):
        return self.cost(instrument, quantity, price) * instrument["initMargin"]
