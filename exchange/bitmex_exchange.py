# -*- coding: utf-8 -*-

"""BitMEX API Connector."""
from __future__ import absolute_import
import sys
import requests
import time
from time import sleep
from datetime import datetime
import json
import decimal
import base64
import uuid
import traceback
from exchange.APIKeyAuthWithExpires import APIKeyAuthWithExpires
from exchange.bitmex_websocket import BitMEXWebsocket
from config.settings import settings
from exchange.chart import CHART
from future.utils import iteritems
from utils import errors


class BitMEXExchange(object):
    """
    BitMEX API Connector.
    """

    def __init__(self, logger, base_url=None, wss_url=None, symbol=None,
                 api_key=None, api_secret=None, order_id_prefix='mm_bitmex_', should_ws_auth=True):
        """
        Init connector.
        """

        self.logger = logger
        self.base_url = base_url
        self.wss_url = wss_url
        self.symbol = symbol
        self.shouldWSAuth = should_ws_auth
        self.chartUnit = settings.CHART_UNITS

        self.apiKey = api_key
        self.apiSecret = api_secret
        if len(order_id_prefix) > 13:
            raise ValueError("settings.ORDERID_PREFIX must be at most 13 characters long!")
        self.orderIDPrefix = order_id_prefix

        # Prepare HTTPS session
        self.session = requests.Session()
        # These headers are always sent
        self.session.headers.update({'user-agent': 'vpinbot-' + settings.VERSION})
        self.session.headers.update({'content-type': 'application/json'})
        self.session.headers.update({'accept': 'application/json'})

        # Create chart
        self.chart = CHART(self.symbol, self.chartUnit)

        # Create websocket for streaming data
        self.ws = BitMEXWebsocket(self.logger, self.symbol, self.message_callback)

        # Websocket data
        self.data = {}
        self.keys = {}

    def connect_websocket(self):
        """
        Connect BitMEX websocket
        """

        # Connect websocket
        self.ws.connect(self.wss_url, should_auth=self.shouldWSAuth)

        # Connected. Wait for partials
        self.wait_for_symbol()
        if self.shouldWSAuth:
            self.wait_for_account()
        self.logger.info('Got all market data. Starting.')

    def disconnect_websocket(self):
        self.ws.exit()

    def wait_for_symbol(self):
        """
        On subscribe, this data will come down. Wait for it.
        """

        # Wait for the keys to show up from the ws
        while not {'instrument', 'trade', 'quote', 'orderBook10'} <= set(self.data):
            sleep(0.1)

    def wait_for_account(self):
        """
        On subscribe, this data will come down. Wait for it.
        """

        # Wait for the keys to show up from the ws
        while not {'margin', 'position', 'order'} <= set(self.data):
            sleep(0.1)

    def message_callback(self, json_data):
        """
        Handler for parsing WS messages.
        """

        message = json.loads(json_data)
        # self.logger.info(json.dumps(message))

        table = message['table'] if 'table' in message else None
        action = message['action'] if 'action' in message else None
        try:
            if 'subscribe' in message:
                if message['success']:
                    self.logger.debug("Subscribed to %s." % message['subscribe'])
                else:
                    self.ws.error("Unable to subscribe to %s. Error: \"%s\" Please check and restart." %
                               (message['request']['args'][0], message['error']))
            elif 'status' in message:
                if message['status'] == 400:
                    self.ws.error(message['error'])
                if message['status'] == 401:
                    self.ws.error("API Key incorrect, please check and restart.")
            elif action:
                if table not in self.data:
                    self.data[table] = []

                if table not in self.keys:
                    self.keys[table] = []

                # There are four possible actions from the WS:
                # 'partial' - full table image
                # 'insert'  - new row
                # 'update'  - update row
                # 'delete'  - delete row
                if action == 'partial':
                    self.logger.debug("%s: partial" % table)
                    self.data[table] += message['data']
                    # Keys are communicated on partials to let you know how to uniquely identify
                    # an item. We use it for updates.
                    self.keys[table] = message['keys']

                elif action == 'insert':
                    self.logger.debug('%s: inserting %s' % (table, message['data']))
                    self.data[table] += message['data']

                    if table == 'trade':
                        for tick in message['data']:
                            symbol = tick['symbol']
                            if symbol == self.symbol:
                                tick_seconds = int(time.time())
                                # tick_seconds = (time.mktime(datetime.strptime(tick['timestamp'],
                                # '%Y-%m-%dT%H:%M:%S.000Z').timetuple()) + 3600 * 9 - 5 * 60) * 1000
                                tick_price = float(tick['price'])
                                tick_volume = float(tick['size'])
                                tick_dir = 1 if tick['side'] == 'Buy' else -1
                                self.chart.make_bar(tick_seconds, tick_price, tick_dir, tick_volume)

                    # Limit the max length of the table to avoid excessive memory usage.
                    # Don't trim orders because we'll lose valuable state if we do.
                    if table not in ['order', 'orderBookL2'] and len(self.data[table]) > BitMEXWebsocket.MAX_TABLE_LEN:
                        self.data[table] = self.data[table][(BitMEXWebsocket.MAX_TABLE_LEN // 2):]

                elif action == 'update':
                    self.logger.debug('%s: updating %s' % (table, message['data']))
                    # Locate the item in the collection and update it.
                    for updateData in message['data']:
                        item = self.findItemByKeys(self.keys[table], self.data[table], updateData)
                        if not item:
                            continue  # No item found to update. Could happen before push

                        # Log executions
                        if table == 'order':
                            is_canceled = 'ordStatus' in updateData and updateData['ordStatus'] == 'Canceled'
                            if 'cumQty' in updateData and not is_canceled:
                                contExecuted = updateData['cumQty'] - item['cumQty']
                                if contExecuted > 0:
                                    instrument = self.get_ws_instrument(item['symbol'])
                                    self.logger.info("Execution: %s %d Contracts of %s at %.*f" %
                                                     (item['side'], contExecuted, item['symbol'],
                                                      instrument['tickLog'], item['price']))

                        # Update this item.
                        item.update(updateData)

                        # Remove canceled / filled orders
                        if table == 'order' and item['leavesQty'] <= 0:
                            self.data[table].remove(item)

                elif action == 'delete':
                    self.logger.debug('%s: deleting %s' % (table, message['data']))
                    # Locate the item in the collection and remove it.
                    for deleteData in message['data']:
                        item = self.findItemByKeys(self.keys[table], self.data[table], deleteData)
                        self.data[table].remove(item)
                else:
                    raise Exception("Unknown action: %s" % action)
        except:
            self.logger.error(traceback.format_exc())

    def findItemByKeys(self, keys, table, match_data):
        for item in table:
            matched = True
            for key in keys:
                if item[key] != match_data[key]:
                    matched = False
            if matched:
                return item

    def get_ws_instrument(self, symbol):
        """
        Get an instrument's details.
        """

        instruments = self.data['instrument']
        matchingInstruments = [i for i in instruments if i['symbol'] == symbol]
        if len(matchingInstruments) == 0:
            raise Exception("Unable to find instrument or index with symbol: " + symbol)
        instrument = matchingInstruments[0]
        instrument['tickLog'] = decimal.Decimal(str(instrument['tickSize'])).as_tuple().exponent * -1

        return instrument

    def get_ws_ticker(self, symbol):
        """
        Return a ticker object. Generated from instrument.
        """

        instrument = self.get_ws_instrument(symbol)

        # If this is an index, we have to get the data from the last trade.
        if instrument['symbol'][0] == '.':
            ticker = {}
            ticker['mid'] = ticker['buy'] = ticker['sell'] = ticker['last'] = instrument['markPrice']
        # Normal instrument
        else:
            bid = instrument['bidPrice'] or instrument['lastPrice']
            ask = instrument['askPrice'] or instrument['lastPrice']
            ticker = {
                "last": instrument['lastPrice'],
                "buy": bid,
                "sell": ask,
                "mid": (bid + ask) / 2
            }

        # The instrument has a tickSize. Use it to round values.
        return {k: round(float(v or 0), instrument['tickLog']) for k, v in iteritems(ticker)}

    def get_ws_funds(self):
        """
        Get your current balance.
        """

        return self.data['margin'][0]

    def get_ws_market_depth(self, symbol):
        """
        Get market depth / orderbook.
        """

        for order_book in self.data['orderBook10']:
            if order_book['symbol'] == symbol:
                return order_book
        return None

    def get_ws_open_orders(self):
        """
        Get open orders via Websocket.
        """

        orders = self.data['order']
        # Filter to only open orders (leavesQty > 0) and those that we actually placed
        return [o for o in orders if str(o['clOrdID']).startswith(self.orderIDPrefix) and o['leavesQty'] > 0]

    def get_ws_position(self, symbol):
        """
        Get your open position.
        """

        positions = self.data['position']
        pos = [p for p in positions if p['symbol'] == symbol]
        if len(pos) == 0:
            # No position found; stub it
            return {'markPrice': 0, 'avgEntryPrice': 0, 'marginCallPrice': 0, 'currentQty': 0, 'symbol': symbol}
        return pos[0]

    def get_ws_recent_trades(self):
        """
        Get recent trades.

        Returns
        -------
        A list of dicts:
              {u'amount': 60,
               u'date': 1306775375,
               u'price': 8.7401099999999996,
               u'tid': u'93842'},
        """

        return self.data['trade']

    def instruments(self, filter=None):
        """
        Get all instrument
        """

        query = {}
        if filter is not None:
            query['filter'] = json.dumps(filter)
        return self._curl_bitmex(api='/instrument', query=query, verb='GET')

    def authentication_required(function):
        """
        Annotation for methods that require auth.
        """

        def wrapped(self, *args, **kwargs):
            if not self.apiKey:
                msg = "You must be authenticated to use this method"
                raise errors.AuthenticationError(msg)
            else:
                return function(self, *args, **kwargs)
        return wrapped

    @authentication_required
    def isolate_margin(self, leverage, rethrow_errors=False):
        """
        Set the leverage on an isolated margin position
        """

        postdict = {
            'symbol': self.symbol,
            'leverage': leverage
        }
        return self._curl_bitmex(api="/position/leverage", postdict=postdict, verb="POST", rethrow_errors=rethrow_errors)

    @authentication_required
    def buy_order(self, quantity, price):
        """
        Place a buy order.
        Returns order object. ID: orderID
        """

        return self.place_order(quantity, price)

    @authentication_required
    def sell_order(self, quantity, price):
        """
        Place a sell order.
        Returns order object. ID: orderID
        """

        return self.place_order(-quantity, price)

    @authentication_required
    def place_order(self, quantity, price):
        """
        Place an order.
        """

        if price < 0:
            raise Exception("Price must be positive.")

        # Generate a unique clOrdID with our prefix so we can identify it.
        clOrdID = self.orderIDPrefix + base64.b64encode(uuid.uuid4().bytes).decode('utf-8').rstrip('=\n')
        postdict = {
            'symbol': self.symbol,
            'orderQty': quantity,
            'price': price,
            'clOrdID': clOrdID,
            'execInst': 'ParticipateDoNotInitiate'
        }
        return self._curl_bitmex(api="/order", postdict=postdict, verb="POST")

    @authentication_required
    def amend_bulk_orders(self, orders):
        """
        Amend multiple orders.
        """

        return self._curl_bitmex(api='/order/bulk', postdict={'orders': orders}, verb='PUT', rethrow_errors=True)

    @authentication_required
    def create_bulk_orders(self, orders):
        """
        Create multiple orders.
        """

        for order in orders:
            order['clOrdID'] = self.orderIDPrefix + base64.b64encode(uuid.uuid4().bytes).decode('utf-8').rstrip('=\n')
            order['symbol'] = self.symbol
            order['execInst'] = 'ParticipateDoNotInitiate'
        return self._curl_bitmex(api='/order/bulk', postdict={'orders': orders}, verb='POST')

    @authentication_required
    def cancel_bulk_orders(self, orders):
        """
        Cancel multiple orders.
        """

        return self.cancel_order([order['orderID'] for order in orders])

    @authentication_required
    def http_open_orders(self):
        """
        Get open orders via HTTP. Used on close to ensure we catch them all.
        """

        orders = self._curl_bitmex(
            api="/order",
            query={'filter': json.dumps({'ordStatus.isTerminated': False, 'symbol': self.symbol})},
            verb="GET"
        )
        # Only return orders that start with our clOrdID prefix.
        return [o for o in orders if str(o['clOrdID']).startswith(self.orderIDPrefix)]

    @authentication_required
    def cancel_order(self, order_id):
        """
        Cancel an existing order.
        """

        postdict = {
            'orderID': order_id,
        }
        self.logger.info("BitMex cancel order %s" % order_id)
        return self._curl_bitmex(api="/order", postdict=postdict, verb="DELETE")

    @authentication_required
    def withdraw(self, amount, fee, address):
        """
        withdraw
        """

        postdict = {
            'amount': amount,
            'fee': fee,
            'currency': 'XBt',
            'address': address
        }
        return self._curl_bitmex(api="/user/requestWithdrawal", postdict=postdict, verb="POST")

    def _curl_bitmex(self, api, query=None, postdict=None, timeout=3, verb=None, rethrow_errors=False):
        """
        Send a request to BitMEX Servers.
        """

        # Handle URL
        url = self.base_url + api

        # Default to POST if data is attached, GET otherwise
        if not verb:
            verb = 'POST' if postdict else 'GET'

        auth = APIKeyAuthWithExpires(self.apiKey, self.apiSecret)

        def maybe_exit(e):
            if rethrow_errors:
                raise e
            else:
                exit(1)

        # Make the request
        response = None
        try:
            req = requests.Request(verb, url, json=postdict, auth=auth, params=query)
            prepped = self.session.prepare_request(req)
            response = self.session.send(prepped, timeout=timeout)
            # Make non-200s throw
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            # 401 - Auth error. This is fatal with API keys.
            if response.status_code == 401:
                self.logger.error("Login information or API Key incorrect, please check and restart.")
                self.logger.error("Error: " + response.text)
                if postdict:
                    self.logger.error(postdict)
                # Always exit, even if rethrow_errors, because this is fatal
                exit(1)
                return self._curl_bitmex(api, query, postdict, timeout, verb)

            # 404, can be thrown if order canceled does not exist.
            elif response.status_code == 404:
                if verb == 'DELETE':
                    self.logger.error("Order not found: %s" % postdict['orderID'])
                    return
                self.logger.error("Unable to contact the BitMEX API (404). " +
                                  "Request: %s \n %s" % (url, json.dumps(postdict)))
                maybe_exit(e)

            # 429, ratelimit
            elif response.status_code == 429:
                self.logger.error("Ratelimited on current request. Sleeping, then trying again. Try fewer " +
                                  "order pairs or contact support@bitmex.com to raise your limits. " +
                                  "Request: %s \n %s" % (url, json.dumps(postdict)))
                sleep(1)
                return self._curl_bitmex(api, query, postdict, timeout, verb)

            # 503 - BitMEX temporary downtime, likely due to a deploy. Try again
            elif response.status_code == 503:
                self.logger.warning("Unable to contact the BitMEX API (503), retrying. " +
                                    "Request: %s \n %s" % (url, json.dumps(postdict)))
                sleep(1)
                return self._curl_bitmex(api, query, postdict, timeout, verb)

            # Duplicate clOrdID: that's fine, probably a deploy, go get the order and return it
            elif (response.status_code == 400 and
                  response.json()['error'] and
                  response.json()['error']['message'] == 'Duplicate clOrdID'):

                order = self._curl_bitmex('/order',
                                          query={'filter': json.dumps({'clOrdID': postdict['clOrdID']})},
                                          verb='GET')[0]
                if (
                        order['orderQty'] != postdict['quantity'] or
                        order['price'] != postdict['price'] or
                        order['symbol'] != postdict['symbol']):
                    raise Exception('Attempted to recover from duplicate clOrdID, but order returned from API ' +
                                    'did not match POST.\nPOST data: %s\nReturned order: %s' % (
                                        json.dumps(postdict), json.dumps(order)))
                # All good
                return order

            # Unknown Error
            else:
                self.logger.error("Unhandled Error: %s: %s" % (e, response.text))
                self.logger.error("Endpoint was: %s %s: %s" % (verb, api, json.dumps(postdict)))
                maybe_exit(e)

        except requests.exceptions.Timeout as e:
            # Timeout, re-run this request
            self.logger.warning("Timed out, retrying...")
            return self._curl_bitmex(api, query, postdict, timeout, verb)

        except requests.exceptions.ConnectionError as e:
            self.logger.warning("Unable to contact the BitMEX API (ConnectionError). Please check the URL. Retrying. " +
                                "Request: %s \n %s" % (url, json.dumps(postdict)))
            sleep(1)
            return self._curl_bitmex(api, query, postdict, timeout, verb)

        return response.json()
