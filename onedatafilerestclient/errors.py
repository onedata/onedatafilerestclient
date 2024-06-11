# coding: utf-8
"""Onedata REST file API client errors module."""

from __future__ import annotations

from typing import Dict, Optional, Union

import requests

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"


class OnedataError(Exception):
    """Base exception class for Onedata errors."""

    msg = "Unexpected error"

    def __str__(self) -> str:
        """Return the error message."""
        return self.msg.format(**self.__dict__)


class ReadonlyTokenError(OnedataError):
    """Exception raised when write operation is called with readonly token."""

    msg = (
        "Forbidden operation - the provided access token is limited "
        "to read-only data access."
    )


class SpaceNotFoundError(OnedataError):
    """Exception raised when space is not found in Onedata system."""

    msg = (
        "Could not find the requested Onedata space '{space_specifier}'; "
        "either it does not exist, or the provided access token is limited "
        "to a different subset of spaces."
    )

    def __init__(self, space_specifier: str):
        """Construct 'SpaceNotFoundError' instance."""
        self.space_specifier = space_specifier

        super().__init__(space_specifier)


class NoAvailableProviderForSpaceError(OnedataError):
    """Exception raised when no available provider is found for a space."""

    msg = (
        "Could not find any available Onedata provider for the space '{space_specifier}'; "
        "either the space is not supported at all, or all supporting providers "
        "are offline, malfunctioning or outdated (version >= 21.02.1 is required)."
    )

    def __init__(self, space_specifier: str):
        """Construct 'NoAvailableProviderForSpaceError' instance."""
        self.space_specifier = space_specifier

        super().__init__(space_specifier)


class OnedataRESTError(OnedataError):
    """Custom Onedata REST exception class."""

    def __init__(
        self,
        http_code: int,
        category: Optional[str] = None,
        description: Optional[str] = None,
        details: Optional[Union[str, Dict[str, str]]] = None,
    ):
        """Construct from individual properties."""
        self.http_code = http_code
        self.category = category
        self.description = description
        self.details = details

        super().__init__(http_code, category, description, details)

    @classmethod
    def from_response(cls, response: requests.Response) -> OnedataRESTError:
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
        msg = f"HTTP {self.http_code}"

        if self.category:
            msg += f" [{self.category}]"

        if self.description:
            msg += f" {self.description}"

        if self.details:
            msg += f" ({self.details})"

        return msg
