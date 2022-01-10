#
# bithumb API-call related functions
#

import time
import math
import base64
import hmac
import hashlib
import urllib.parse
import pycurl
import json
import certifi
import os


class BithumbExchange(object):
    contents = ""

    def __init__(self, logger, base_url=None, symbol=None, api_key=None, api_secret=None):
        self.logger = logger
        self.base_url = base_url
        self.symbol = symbol
        self.api_key = api_key
        self.api_secret = api_secret
        self.contents = ""

    def body_callback(self, buf):
        self.contents = self.contents + buf.decode('utf-8')

    def micro_time(self, get_as_float=False):
        if get_as_float:
            return time.time()
        else:
            return '%f %d' % math.modf(time.time())

    def usec_time(self):
        mt = self.micro_time(False)
        mt_array = mt.split(" ")[:2]
        return mt_array[1] + mt_array[0][2:5]

    def api_call(self, endpoint, params):
        self.contents = ''

        endpoint_item_array = {
            "endpoint": endpoint
        }

        uri_array = dict(endpoint_item_array, **params)  # Concatenate the two arrays.
        str_data = urllib.parse.urlencode(uri_array)

        nonce = self.usec_time()

        data = endpoint + chr(0) + str_data + chr(0) + nonce
        utf8_data = data.encode('utf-8')

        key = self.api_secret
        utf8_key = key.encode('utf-8')

        h = hmac.new(bytes(utf8_key), utf8_data, hashlib.sha512)
        hex_output = h.hexdigest()
        utf8_hex_output = hex_output.encode('utf-8')

        api_sign = base64.b64encode(utf8_hex_output)
        utf8_api_sign = api_sign.decode('utf-8')

        curl_handle = pycurl.Curl()
        try:
            curl_handle.setopt(pycurl.POST, 1)
            curl_handle.setopt(pycurl.POSTFIELDS, str_data)

            url = self.base_url + endpoint
            curl_handle.setopt(curl_handle.CAINFO, certifi.where())
            curl_handle.setopt(curl_handle.URL, url)
            curl_handle.setopt(curl_handle.HTTPHEADER, ['Api-Key: ' + self.api_key,
                                                        'Api-Sign: ' + utf8_api_sign,
                                                        'Api-Nonce: ' + nonce])
            curl_handle.setopt(curl_handle.WRITEFUNCTION, self.body_callback)

            curl_handle.perform()
        except pycurl.error as e:
            print(e)
            self.contents = '{"status": "1000", "message": "curl error"}'
        finally:
            curl_handle.close()

        try:
            json_data = json.loads(self.contents)
        except ValueError:
            print("json error")
            json_data = json.loads('{"status": "1000", "message": "json error"}')

        return json_data
