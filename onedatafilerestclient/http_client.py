# coding: utf-8
"""REST-style HTTP client wrapper over requests."""

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import json
import logging
from typing import Any, Dict, Optional

import requests
from requests.structures import CaseInsensitiveDict

from .errors import OnedataRESTError

_logger = logging.getLogger(__name__)
_logger.addHandler(logging.NullHandler())

_HEADERS_TO_LOG = {"range"}


class HttpClient:
    """REST-style wrapper over requests library."""

    timeout: int = 8
    session: requests.Session

    def __init__(self, *, verify_ssl: bool = True) -> None:
        """Construct OnedataFileClient instance."""
        self.session = requests.Session()
        self.session.verify = verify_ssl

    def get_session(self) -> requests.Session:
        """Return requests session instance."""
        return self.session

    def get(
        self,
        url: str,
        data: Any = None,
        headers: Optional[Dict[str, str]] = None,
        *,
        stream: bool = False,
    ) -> requests.Response:
        """Perform a GET request."""
        return self._send_request("GET", url, data, headers, stream=stream)

    def put(
        self, url: str, data: Any = None, headers: Optional[Dict[str, str]] = None
    ) -> requests.Response:
        """Perform a PUT request."""
        return self._send_request("PUT", url, data, headers)

    def post(
        self, url: str, data: Any = None, headers: Optional[Dict[str, str]] = None
    ) -> requests.Response:
        """Perform a POST request."""
        return self._send_request("POST", url, data, headers)

    def delete(
        self, url: str, data: Any = None, headers: Optional[Dict[str, str]] = None
    ) -> requests.Response:
        """Perform a DELETE request."""
        return self._send_request("DELETE", url, data, headers)

    def head(
        self, url: str, data: Any = None, headers: Optional[Dict[str, str]] = None
    ) -> requests.Response:
        """Perform a HEAD request."""
        return self._send_request("HEAD", url, data, headers)

    def _send_request(
        self,
        method: str,
        url: str,
        data: Any = None,
        headers: Optional[Dict[str, str]] = None,
        *,
        stream: bool = False,
    ) -> requests.Response:
        """Perform an HTTP request."""
        if isinstance(data, dict):
            body = json.dumps(data)
        else:
            body = data

        case_insensitive_headers = CaseInsensitiveDict(headers)
        if "content-type" not in case_insensitive_headers:
            case_insensitive_headers["content-type"] = "application/json"

        req = requests.Request(method, url, data=body, headers=case_insensitive_headers)
        prepared = self.session.prepare_request(req)
        response = self.session.send(prepared, stream=stream, timeout=self.timeout)

        if not response.ok:
            ex = OnedataRESTError.from_response(response)
            if response.status_code == 403:
                _logger.debug(
                    "AUTHORIZATION FAILED %s %s\nheaders: %s\nbody: %s\ndetails: %s",
                    method,
                    url,
                    {
                        k: v
                        for k, v in case_insensitive_headers.items()
                        if k.lower() in _HEADERS_TO_LOG
                    },
                    data if isinstance(data, dict) else len(data),
                    ex,
                )
            else:
                _logger.debug("REQUEST FAILED %s %s\ndetails: %s", method, url, ex)

            raise ex

        _logger.debug("REQUEST OK %d %s %s", response.status_code, method, url)
        return response
