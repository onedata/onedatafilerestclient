# coding: utf-8
"""REST-style HTTP client wrapper over requests."""

from __future__ import annotations

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = (
    "This software is released under the MIT license cited in LICENSE.txt")

import logging
from typing import Any

from onedatafilerestclient import OnedataRESTError

import requests


def trace_requests_messages() -> None:
    """Enable logging HTTP requests."""
    import http.client as http_client
    http_client.HTTPConnection.debuglevel = 1

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True


# Uncomment to enable HTTP request trace log
# trace_requests_messages()


class HttpClient:
    """REST-style wrapper over requests library."""
    timeout: int = 5
    session: requests.Session

    def _send_request(self,
                      method: str,
                      url: str,
                      data: Any = None,
                      headers: dict[str, str] = {}) -> requests.Response:
        """Perform an HTTP request."""
        logging.debug(f">> {method} {url} {headers}")

        if 'Content-type' not in headers:
            headers['Content-type'] = 'application/json'

        req = requests.Request(method, url, data=data, headers=headers)
        prepared = self.session.prepare_request(req)
        response = self.session.send(prepared,
                                      timeout=self.timeout,
                                      verify=False)

        if not response.ok:
            logging.debug(f"ERROR: {method} {url} '{response.text}'")
            raise OnedataRESTError(response)

        logging.debug(f'<< {response.content}')

        return response

    def _get(self,
             url: str,
             data: Any = None,
             headers: dict[str, str] = {}) -> requests.Response:
        return self._send_request('GET', url, data, headers)

    def _put(self,
             url: str,
             data: Any = None,
             headers: dict[str, str] = {}) -> requests.Response:
        return self._send_request('PUT', url, data, headers)

    def _post(self,
              url: str,
              data: Any = None,
              headers: dict[str, str] = {}) -> requests.Response:
        return self._send_request('POST', url, data, headers)

    def _delete(self,
                url: str,
                data: Any = None,
                headers: dict[str, str] = {}) -> requests.Response:
        return self._send_request('DELETE', url, data, headers)

    def _head(self,
              url: str,
              data: Any = None,
              headers: dict[str, str] = {}) -> requests.Response:
        return self._send_request('HEAD', url, data, headers)
