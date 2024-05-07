"""Access token scope data types.

Refer to the API specification for more information:
https://onedata.org/#/home/api/stable/onezone?anchor=operation/infer_access_token_scope
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2024 ACK CYFRONET AGH"
__license__ = (
    "This software is released under the MIT license cited in LICENSE.txt")

import sys

if sys.version_info < (3, 11):
    from typing_extensions import Dict, TypeAlias, TypedDict
else:
    from typing import Dict, TypeAlias, TypedDict

SpaceId: TypeAlias = str
ProviderId: TypeAlias = str


class SpaceSupportAttributes(TypedDict):
    """Relevant space support attributes."""

    readonly: bool


class SpaceDetails(TypedDict):
    """Space details."""

    name: str
    supports: Dict[ProviderId, SpaceSupportAttributes]


class ProviderDetails(TypedDict):
    """Provider details."""

    name: str
    domain: str
    version: str
    online: bool


class DataAccessScope(TypedDict):
    """Data access scope info."""

    readonly: bool
    spaces: Dict[SpaceId, SpaceDetails]
    providers: Dict[ProviderId, ProviderDetails]


class AccessTokenScope(TypedDict):
    """JSON object describing inferred data access scope and validity."""

    validUntil: int
    dataAccessScope: DataAccessScope
