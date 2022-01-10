# -*- coding: utf-8 -*-

import websocket
import threading
from time import sleep
import json
from config.settings import settings
from exchange.APIKeyAuth import generate_expires, generate_signature


class BitMEXWebsocket(object):
    # Don't grow a table larger than this amount. Helps cap memory usage.
    MAX_TABLE_LEN = 200

    def __init__(self, logger, symbol, message_callback):
        self.logger = logger
        self.symbol = symbol
        self.message_callback = message_callback
        self.endpoint = ""
        self.shouldAuth = True

        self.reset()

    def __del__(self):
        self.exit()

    def connect(self, endpoint="", should_auth=True):
        """
        Connect to the websocket and initialize data stores.
        """

        self.endpoint = endpoint
        self.shouldAuth = should_auth

        # We can subscribe right in the connection querystring, so let's build that.
        # Subscribe to all pertinent endpoints
        subscriptions = [sub + ':' + self.symbol for sub in ["quote", "trade", "orderBook10"]]
        subscriptions += ["instrument"]  # We want all of them
        if self.shouldAuth:
            subscriptions += [sub + ':' + self.symbol for sub in ["order", "execution"]]
            subscriptions += ["margin", "position"]

        # Get WS URL and connect.
        ws_url = endpoint + "/realtime?subscribe=" + ",".join(subscriptions)
        self.logger.info("BitMEX, Websocket Connecting to %s" % ws_url)
        self.__connect(ws_url)

    def exit(self):
        self.exited = True
        self.ws.close()

    def reset(self):
        self.exited = False
        self._error = None

    def error(self, err):
        self._error = err
        self.logger.error(err)
        self.exit()

    def __connect(self, ws_url):
        """
        Connect to the websocket
        """

        self.logger.info("BitMEX, Websocket %s", ws_url)

        # websocket.enableTrace(True)
        self.ws = websocket.WebSocketApp(ws_url,
                                         on_message=self.__on_message,
                                         on_close=self.__on_close,
                                         on_open=self.__on_open,
                                         on_error=self.__on_error,
                                         header=self.__get_auth())

        self.wst = threading.Thread(target=lambda: self.ws.run_forever())
        self.wst.daemon = True
        self.wst.start()

        # Wait for connect before continuing
        conn_timeout = 5
        while (not self.ws.sock or not self.ws.sock.connected) and conn_timeout and not self._error:
            sleep(1)
            conn_timeout -= 1

        if not conn_timeout or self._error:
            self.logger.error("BitMEX, Websocket not connected. Exiting.")
            self.exit()

        self.logger.info("BitMEX, Websocket connect complete!")

    def __get_auth(self):
        """
        Return auth headers. Will use API Keys if present in settings.
        """
        if self.shouldAuth is False:
            return []

        nonce = generate_expires()
        return [
            "api-nonce: " + str(nonce),
            "api-signature: " + generate_signature(settings.BITMEX_API_SECRET, 'GET', '/realtime', nonce, ''),
            "api-key:" + settings.BITMEX_API_KEY
        ]

    def __send_command(self, command, args=None):
        """
        Send a raw command.
        """
        if args is None:
            args = []
        self.ws.send(json.dumps({"op": command, "args": args}))

    def __on_open(self):
        """
        Handler for WS open event
        """

        self.logger.info("BitMEX, Websocket Opened.")

        self.exited = False

    def __on_message(self, json_data):
        """
        Handler for parsing WS messages.
        """

        self.message_callback(json_data)

    def __on_close(self):
        """
        Handler for WS close event
        """

        self.logger.info('BitMEX, Websocket Closed')
        self.exit()

    def __on_error(self, error):
        """
        Handler for WS close event
        """

        if not self.exited:
            self.error(error)
