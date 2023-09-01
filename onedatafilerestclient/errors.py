# coding: utf-8
"""Onedata REST file API client errors module."""

from __future__ import annotations

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = (
    "This software is released under the MIT license cited in LICENSE.txt")

import requests


class OnedataRESTError(Exception):
    """Custom Onedata REST exception class."""
    def __init__(self, response: requests.Response):
        """Construct from a requests response object."""
        self.http_code = response.status_code
        self.error_category = None
        self.error_details = None
        self.description = None

        try:
            self.error_category = response.json()['error']['id']
        except:  # noqa
            pass

        try:
            self.error_details = response.json()['error']['details']
        except:  # noqa
            pass

        try:
            self.description = response.json()['error']['description']
        except:  # noqa
            pass

    def __repr__(self) -> str:
        """Return unique representation of the OnedataRESTFS instance."""
        return self.__str__()

    def __str__(self) -> str:
        """Return unique representation of the OnedataRESTFS instance."""
        return "<onedataresterror '{} {}:{} {}'>".format(
            self.http_code, self.error_category, self.error_details,
            self.description)
