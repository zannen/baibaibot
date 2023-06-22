# This file is adapted from krakenex: https://github.com/veox/python3-krakenex/
#
# krakenex is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# krakenex is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser
# General Public LICENSE along with krakenex. If not, see
# <http://www.gnu.org/licenses/lgpl-3.0.txt> and
# <http://www.gnu.org/licenses/gpl-3.0.txt>.

"""A class to handle generic interaction with the Kraken API."""

import base64
import hashlib
import hmac
import json
import time
import urllib.request

import requests

from . import version
from .encode import encode


class KAPI:
    """Maintains a single session between this machine and Kraken.

    Specifying a key/secret pair is optional. If not specified, private
    queries will not be possible.

    The :py:attr:`session` attribute is a :py:class:`requests.Session`
    object. Customise networking options by manipulating it.

    Query responses, as received by :py:mod:`requests`, are retained
    as attribute :py:attr:`response` of this object. It is overwritten
    on each query.

    .. note::
       No query rate limiting is performed.

    """

    def __init__(self, key="", secret=""):
        """Create an object with authentication information.

        :param key: (optional) key identifier for queries to the API
        :type key: str
        :param secret: (optional) actual private key used to sign messages
        :type secret: str
        :returns: None

        """
        self.key = key
        self.secret = secret
        self.uri = "https://api.kraken.com"
        self.apiversion = "0"
        self.session = requests.Session()
        self.user_agent = (
            "baibaibot/" + version.__version__ + " (+" + version.__url__ + ")"
        )
        self.session.headers.update({"User-Agent": self.user_agent})
        self.response = None
        self._json_options = {}
        return

    def json_options(self, **kwargs):
        """Set keyword arguments to be passed to JSON deserialization.

        :param kwargs: passed to :py:meth:`requests.Response.json`
        :returns: this instance for chaining

        """
        self._json_options = kwargs
        return self

    def close(self):
        """Close this session.

        :returns: None

        """
        self.session.close()
        return

    def load_key(self, path):
        """Load key and secret from file.

        Expected file format is key and secret on separate lines.

        :param path: path to keyfile
        :type path: str
        :returns: None

        """
        with open(path, "r", encoding="utf-8") as f:
            self.key = f.readline().strip()
            self.secret = f.readline().strip()
        return

    def _query(self, urlpath, data, headers=None, timeout=None):
        """Low-level query handling.

        .. note::
           Use :py:meth:`query_private` or :py:meth:`query_public`
           unless you have a good reason not to.

        :param urlpath: API URL path sans host
        :type urlpath: str
        :param data: API request parameters
        :type data: dict
        :param headers: (optional) HTTPS headers
        :type headers: dict
        :param timeout: (optional) if not ``None``, a `requests.HTTPError`
                        will be thrown after ``timeout`` seconds if a response
                        has not been received
        :type timeout: int or float
        :returns: :py:meth:`requests.Response.json`-deserialised Python object
        :raises: `requests.HTTPError`: if response status not successful

        """
        if data is None:
            data = {}
        if headers is None:
            headers = {}

        url = self.uri + urlpath

        self.response = self.session.post(
            url,
            data=data,
            headers=headers,
            timeout=timeout,
        )

        if self.response.status_code not in (200, 201, 202):
            self.response.raise_for_status()

        return self.response.json(**self._json_options)

    def query_public(self, method, data=None, timeout=None):
        """Performs an API query that does not require a valid key/secret pair.

        :param method: API method name
        :type method: str
        :param data: (optional) API request parameters
        :type data: dict
        :param timeout: (optional) if not ``None``, a `requests.HTTPError`
                        will be thrown after ``timeout`` seconds if a response
                        has not been received
        :type timeout: int or float
        :returns: :py:meth:`requests.Response.json`-deserialised Python object

        """
        if data is None:
            data = {}

        urlpath = "/" + self.apiversion + "/public/" + method

        return self._query(urlpath, data, timeout=timeout)

    def query_private(self, method: str, data: dict = {}, timeout=None):
        """
        Perform an API query that requires a valid key/secret pair.
        """
        if not self.key or not self.secret:
            raise Exception(
                "Either key or secret is not set! (Use `load_key()`."
            )

        data["nonce"] = str(int(1000 * time.time()))

        urlpath = "/" + self.apiversion + "/private/" + method

        # Note: cannot use urllib.parse.urlencode() here. It does not handle
        #       embedded lists/dicts very well, so not good with closing orders
        #       or batch orders.
        api_post = encode(data)
        api_sha256 = hashlib.sha256(
            data["nonce"].encode("utf8") + api_post.encode("utf8")
        )
        api_hmac = hmac.new(
            base64.b64decode(self.secret),
            urlpath.encode("utf8") + api_sha256.digest(),
            hashlib.sha512,
        )
        api_signature = base64.b64encode(api_hmac.digest())

        api_request = urllib.request.Request(
            self.uri + urlpath, api_post.encode("utf8")
        )
        api_request.add_header("API-Key", self.key)
        api_request.add_header("API-Sign", str(api_signature))
        api_request.add_header("User-Agent", self.user_agent)
        api_response = urllib.request.urlopen(api_request).read().decode()
        return json.loads(api_response)
