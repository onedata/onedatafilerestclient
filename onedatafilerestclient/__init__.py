# coding: utf-8
"""onedatafilerestclient module."""

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

__all__ = ["OnedataRESTError", "OnedataFileRESTClient"]

from .errors import OnedataRESTError  # noqa
from .onedata_file_rest_client import OnedataFileRESTClient  # noqa
