# coding: utf-8
"""Definitions of environment constants used in tests."""

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"


from typing import Final

ZONE_DOMAIN: Final[str] = "dev-onezone-0.default.svc.cluster.local"

PROVIDER_KRK_NAME: Final[str] = "dev-oneprovider-krakow"
PROVIDER_KRK_DOMAIN: Final[str] = "dev-oneprovider-krakow.default.svc.cluster.local"
PROVIDER_PAR_NAME: Final[str] = "dev-oneprovider-paris"
PROVIDER_PAR_DOMAIN: Final[str] = "dev-oneprovider-paris.default.svc.cluster.local"

SPACE_KRK_PAR_NAME: Final[str] = "space_krk_par"
SPACE_PAR_NAME: Final[str] = "space_par"
SPACE_NO_SUPPORT_NAME: Final[str] = "space_nosupport"

ADMIN_USERNAME: Final[str] = "admin"
ADMIN_PASSWORD: Final[str] = "password"
SPACE_MEMBER_USERNAME: Final[str] = "space_member"
SPACE_MEMBER_PASSWORD: Final[str] = "password"
