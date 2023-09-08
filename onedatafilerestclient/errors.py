# coding: utf-8
"""Onedata REST file API client errors module."""

from __future__ import annotations

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = (
    "This software is released under the MIT license cited in LICENSE.txt")

from typing import Optional

import requests


class OnedataRESTError(Exception):
    """Custom Onedata REST exception class."""
    def __init__(self,
                 http_code: int,
                 error_category: Optional[str] = None,
                 error_details: Optional[str] = None,
                 description: Optional[str] = None):
        """Construct from individual properties."""
        self.http_code = http_code
        self.error_category = error_category
        self.error_details = error_details
        self.description = description

    @classmethod
    def from_response(cls, response: requests.Response) -> OnedataRESTError:
        """Construct from a requests response object."""
        http_code = response.status_code
        error_category = None
        error_details = None
        description = None

        try:
            error_category = response.json()['error']['id']
        except:  # noqa
            pass

        try:
            error_details = response.json()['error']['details']
        except:  # noqa
            pass

        try:
            description = response.json()['error']['description']
        except:  # noqa
            pass

        return cls(http_code, error_category, error_details, description)

    def __repr__(self) -> str:
        """Return unique representation of the OnedataRESTFS instance."""
        return self.__str__()

    def __str__(self) -> str:
        """Return unique representation of the OnedataRESTFS instance."""
        return "<onedataresterror '{} {}:{} {}'>".format(
            self.http_code, self.error_category, self.error_details,
            self.description)
