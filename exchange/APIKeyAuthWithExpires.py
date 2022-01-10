# - coding: utf-8 -*-

from requests.auth import AuthBase
import time
from exchange.APIKeyAuth import generate_signature


class APIKeyAuthWithExpires(AuthBase):
    """
    Attaches API Key Authentication to the given Request object. This implementation uses `expires`.
    """

    def __init__(self, api_key, api_secret):
        """
        Init with Key & Secret.
        """

        self.apiKey = api_key
        self.apiSecret = api_secret

    def __call__(self, r):
        """
        Called when forming a request - generates api key headers. This call uses `expires` instead of nonce.
        This way it will not collide with other processes using the same API Key if requests arrive out of order.
        For more details, see https://www.bitmex.com/app/apiKeys
        """

        # modify and return the request
        expires = int(round(time.time()) + 5)  # 5s grace period in case of clock skew
        r.headers['api-expires'] = str(expires)
        r.headers['api-key'] = self.apiKey
        r.headers['api-signature'] = generate_signature(self.apiSecret, r.method, r.url, expires, r.body or '')

        return r
