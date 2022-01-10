# -*- coding: utf-8 -*-

import sys
from time import sleep
from config.settings import settings
from exchange.bithumb_exchange import BithumbExchange
from exchange.bitmex_exchange import BitMEXExchange


class ExchangeInterface:
    def __init__(self, logger):
        self.logger = logger
        self.bithumb_exchange = BithumbExchange(self.logger,
                                                settings.BITHUMB_BASE_URL,
                                                settings.BITHUMB_BTC_SYMBOL,
                                                settings.BITHUMB_API_KEY, settings.BITHUMB_API_SECRET)

        self.bitmex_exchange = BitMEXExchange(self.logger,
                                              settings.BITMEX_BASE_URL, settings.BITMEX_WSS_URL,
                                              settings.BITMEX_BTC_SYMBOL,
                                              settings.BITMEX_API_KEY, settings.BITMEX_API_SECRET,
                                              settings.BITMEX_ORDERID_PREFIX, True)
        self.bitmex_exchange.connect_websocket()

    def exit(self):
        self.bitmex_exchange.ws.exit()

    def get_btci(self):
        return self.bithumb_exchange.api_call("/public/btci", {})

    def get_latest_vpin(self):
        cur_candle = self.bitmex_exchange.chart.candles[-1]
        return cur_candle.vpinShort, cur_candle.bounceShort

    def is_ws_open(self):
        """
        Check that websocket are still open.
        """

        return not self.bitmex_exchange.ws.exited

    def check_market_not_open(self, symbol):
        """
        Check market opened
        """

        instrument = self.bitmex_exchange.get_ws_instrument(symbol)
        if instrument["state"] != "Open":
            self.logger.warn("The instrument %s is not open. State: %s" % (symbol, instrument["state"]))
            return True
        return False

    def check_if_orderbook_empty(self, symbol):
        """
        This function checks whether the order book is empty
        """

        instrument = self.bitmex_exchange.get_ws_instrument(symbol)
        if instrument['midPrice'] is None:
            self.logger.warn("Orderbook is empty, cannot quote")
            return True
        return False

    def cancel_order(self, symbol, order):
        tick_log = self.get_instrument(symbol)['tickLog']
        self.logger.info("Canceling: %s %d @ %.*f" % (order['side'], order['orderQty'], tick_log, order['price']))
        while True:
            try:
                self.bitmex_exchange.cancel_order(order['orderID'])
                sleep(settings.API_REST_INTERVAL)
            except ValueError as e:
                self.logger.info(e)
                sleep(settings.API_ERROR_INTERVAL)
            else:
                break

    def cancel_all_orders(self, symbol):
        self.logger.info("Resetting current position. Canceling all existing orders.")
        tick_log = self.get_instrument(symbol)['tickLog']

        # In certain cases, a WS update might not make it through before we call this.
        # For that reason, we grab via HTTP to ensure we grab them all.
        orders = self.bitmex_exchange.http_open_orders()

        for order in orders:
            self.logger.info("Canceling: %s %d @ %.*f" % (order['side'], order['orderQty'], tick_log, order['price']))

        if len(orders):
            self.bitmex_exchange.cancel_order([order['orderID'] for order in orders])

        sleep(settings.API_REST_INTERVAL)

    def get_portfolio(self):
        contracts = settings.CONTRACTS
        portfolio = {}
        for symbol in contracts:
            position = self.bitmex_exchange.get_ws_position(symbol=symbol)
            instrument = self.bitmex_exchange.get_ws_instrument(symbol=symbol)

            if instrument['isQuanto']:
                future_type = "Quanto"
            elif instrument['isInverse']:
                future_type = "Inverse"
            elif not instrument['isQuanto'] and not instrument['isInverse']:
                future_type = "Linear"
            else:
                raise NotImplementedError("Unknown future type; not quanto or inverse: %s" % instrument['symbol'])

            if instrument['underlyingToSettleMultiplier'] is None:
                multiplier = float(instrument['multiplier']) / float(instrument['quoteToSettleMultiplier'])
            else:
                multiplier = float(instrument['multiplier']) / float(instrument['underlyingToSettleMultiplier'])

            portfolio[symbol] = {
                "currentQty": float(position['currentQty']),
                "futureType": future_type,
                "multiplier": multiplier,
                "markPrice": float(instrument['markPrice']),
                "spot": float(instrument['indicativeSettlePrice'])
            }

        return portfolio

    def calc_delta(self):
        """Calculate currency delta for portfolio"""
        portfolio = self.get_portfolio()
        spot_delta = 0
        mark_delta = 0
        for symbol in portfolio:
            item = portfolio[symbol]
            if item['futureType'] == "Quanto":
                spot_delta += item['currentQty'] * item['multiplier'] * item['spot']
                mark_delta += item['currentQty'] * item['multiplier'] * item['markPrice']
            elif item['futureType'] == "Inverse":
                spot_delta += (item['multiplier'] / item['spot']) * item['currentQty']
                mark_delta += (item['multiplier'] / item['markPrice']) * item['currentQty']
            elif item['futureType'] == "Linear":
                spot_delta += item['multiplier'] * item['currentQty']
                mark_delta += item['multiplier'] * item['currentQty']
        basis_delta = mark_delta - spot_delta
        delta = {
            "spot": spot_delta,
            "mark_price": mark_delta,
            "basis": basis_delta
        }
        return delta

    def get_delta(self, symbol):
        return self.get_position(symbol)['currentQty']

    def get_instrument(self, symbol):
        return self.bitmex_exchange.get_ws_instrument(symbol)

    def get_market_depth(self, symbol):
        return self.bitmex_exchange.get_ws_market_depth(symbol)

    def get_margin(self):
        return self.bitmex_exchange.get_ws_funds()

    def get_orders(self):
        return self.bitmex_exchange.http_open_orders()

    def get_highest_buy(self):
        buys = [o for o in self.get_orders() if o['side'] == 'Buy']
        if not len(buys):
            return {'price': -2**32, 'orderQty': 0}
        highest_buy = max(buys or [], key=lambda o: o['price'])
        return highest_buy if highest_buy else {'price': -2**32}

    def get_lowest_sell(self):
        sells = [o for o in self.get_orders() if o['side'] == 'Sell']
        if not len(sells):
            return {'price': 2**32, 'orderQty': 0}
        lowest_sell = min(sells or [], key=lambda o: o['price'])
        return lowest_sell if lowest_sell else {'price': 2**32}  # ought to be enough for anyone

    def get_position(self, symbol):
        return self.bitmex_exchange.get_ws_position(symbol)

    def get_ticker(self, symbol):
        return self.bitmex_exchange.get_ws_ticker(symbol)

    def amend_bulk_orders(self, orders):
        return self.bitmex_exchange.amend_bulk_orders(orders)

    def create_bulk_orders(self, orders):
        return self.bitmex_exchange.create_bulk_orders(orders)

    def cancel_bulk_orders(self, orders):
        return self.bitmex_exchange.cancel_order([order['orderID'] for order in orders])
