# coding: utf-8
"""Onezone REST API client."""
# mypy: disable-error-code="method-assign"

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2024 Onedata"
__license__ = (
    "This software is released under the MIT license cited in LICENSE.txt")

import sys
import typing
from functools import lru_cache
from typing import Dict, List, Optional, Tuple, Union

if sys.version_info < (3, 11):
    from typing_extensions import TypeAlias, TypedDict
else:
    from typing import TypeAlias, TypedDict

from .errors import OnedataRESTError  # noqa
from .httpclient import HttpClient

ProviderId: TypeAlias = str

SpaceId: TypeAlias = str
SpaceName: TypeAlias = str
SpaceFQN: TypeAlias = str
"""
Fully qualified space name in the form: <SpaceName>@<SpaceId>
"""


class SpaceSupportAttributes(TypedDict):
    """Relevant space support attributes.

    Refer to the API specification for more information:
    https://onedata.org/#/home/api/stable/onezone?anchor=operation/infer_access_token_scope
    """

    readonly: bool


class SpaceDetails(TypedDict):
    """Space details.

    Refer to the API specification for more information:
    https://onedata.org/#/home/api/stable/onezone?anchor=operation/infer_access_token_scope
    """

    name: str
    supports: Dict[ProviderId, SpaceSupportAttributes]


class ProviderDetails(TypedDict):
    """Provider details.

    Refer to the API specification for more information:
    https://onedata.org/#/home/api/stable/onezone?anchor=operation/infer_access_token_scope
    """

    name: str
    domain: str
    version: str
    online: bool


class DataAccessScope(TypedDict):
    """Data access scope info.

    Refer to the API specification for more information:
    https://onedata.org/#/home/api/stable/onezone?anchor=operation/infer_access_token_scope
    """

    readonly: bool
    spaces: Dict[SpaceId, SpaceDetails]
    providers: Dict[ProviderId, ProviderDetails]


class AccessTokenScope(TypedDict):
    """JSON object describing inferred data access scope and validity.

    Refer to the API specification for more information:
    https://onedata.org/#/home/api/stable/onezone?anchor=operation/infer_access_token_scope
    """

    validUntil: int
    dataAccessScope: DataAccessScope


class OnezoneRESTClient:
    """Custom REST client for Onezone REST basic operations API."""
    _host: str
    _token: str
    _client: HttpClient

    def __init__(self, host: str, token: str, *, verify_ssl: bool = True):
        """Construct OnezoneRESTClient instance."""
        self._host = host
        self._token = token
        self._client = HttpClient(verify_ssl=verify_ssl)

        # TODO
        # lru_cache cannot be used as decorator, as we want to have a separate
        # cache for each OnezoneRESTClient instance
        self.get_space_id = lru_cache(maxsize=512)(self.get_space_id)

    def __eq__(self, other: object) -> bool:
        """Compare 2 instances of OnezoneRESTClient."""
        if not isinstance(other, OnezoneRESTClient):
            return NotImplemented

        return (self._host == other._host) and (self._token == other._token)

    def __hash__(self) -> int:
        """Calculate a hash of a given instance of OnezoneRESTClient."""
        return hash(self._host) ^ hash(self._token)

    def build_url(self, path: str) -> str:
        """Build Onezone URL for specific path."""
        if not path.startswith("/"):
            path = "/" + path

        return f"https://{self._host}/api/v3/onezone{path}"

    def infer_token_scope(self) -> AccessTokenScope:
        """Get current token access scope."""
        url = self.build_url("/tokens/infer_access_token_scope")
        result = self._client.post(url, {"token": self._token})
        return typing.cast(AccessTokenScope, result.json())

    def list_spaces(self) -> List[str]:
        """List all spaces available for the current token."""
        access_token_scope = self.infer_token_scope()

        def is_space_supported(s: SpaceDetails) -> bool:
            return "supports" in s and bool(s["supports"])

        all_spaces = access_token_scope["dataAccessScope"]["spaces"]

        # TODO space_name@space_id ?
        supported_spaces = [
            space_details["name"] for space_details in all_spaces.values()
            if is_space_supported(space_details)
        ]

        return supported_spaces

    def get_space_id(
            self,
            space_name: Union[SpaceName, SpaceFQN],
            *,
            access_token_scope: Optional[AccessTokenScope] = None) -> SpaceId:
        """Get space id by name."""
        if is_fully_qualified_space_name(space_name):
            _, space_id = unpack_fully_qualified_space_name(space_name)
            return space_id

        if not access_token_scope:
            access_token_scope = self.infer_token_scope()

        all_spaces = access_token_scope["dataAccessScope"]["spaces"]

        for space_id, space_details in all_spaces.items():
            if space_details["name"] == space_name:
                return space_id

        raise OnedataRESTError(
            http_code=400,
            error_category="posix",
            error_details=f"Space {space_name} does not exist",
            description="enoent")


def is_fully_qualified_space_name(space_name: str) -> bool:
    """Check if given space name if fully qualified."""
    return "@" in space_name


def unpack_fully_qualified_space_name(
        space_fqn: SpaceFQN) -> Tuple[SpaceName, SpaceId]:
    """Infer space name and id from fully qualified space name."""
    space_name, space_id = space_fqn.split("@")
    return space_name, space_id
