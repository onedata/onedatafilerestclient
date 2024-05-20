# coding: utf-8
"""Onedata REST file API client errors module."""

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"


from typing import Optional

import requests


class OnedataError(Exception):
    """Base exception class for Onedata errors."""


class TokenReadonlyError(OnedataError):
    """Exception raised when write operation is called with readonly token."""


class SpaceNotFoundError(OnedataError):
    """Exception raised when space is not found in Onedata system."""


class NoAvailableProviderForSpaceError(OnedataError):
    """Exception raised when no available provider is found for a space."""


class OnedataRESTError(OnedataError):
    """Custom Onedata REST exception class."""

    def __init__(
        self,
        http_code: int,
        category: Optional[str] = None,
        description: Optional[str] = None,
        details: Optional[str] = None,
    ):
        """Construct from individual properties."""
        self.http_code = http_code
        self.category = category
        self.description = description
        self.details = details

        super().__init__(http_code, category, description, details)

    @classmethod
    def from_response(cls, response: requests.Response) -> "OnedataRESTError":
        """Construct from a requests response object."""
        http_code = response.status_code
        error_category = None
        error_description = None
        error_details = None

        try:
            error_json = response.json().get("error", {})
            error_category = error_json.get("id")
            error_description = error_json.get("description")
            error_details = error_json.get("details")
        except ValueError:
            # If response.json() raises a ValueError, it means the response is not JSON
            pass

        return cls(http_code, error_category, error_description, error_details)

    def __str__(self) -> str:
        """Describe error reason."""
        return f"HTTP {self.http_code} [{self.category}] {self.description}\n\n{self.details}"
