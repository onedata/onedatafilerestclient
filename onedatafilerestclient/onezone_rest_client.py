# coding: utf-8
"""Onezone REST API client."""
# mypy: disable-error-code="method-assign"

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2024 Onedata"
__license__ = (
    "This software is released under the MIT license cited in LICENSE.txt")

import sys
import typing
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

SpaceSpecifier: TypeAlias = Union[SpaceName, SpaceFQN]


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
    _cache_size_limit: int = 512

    _host: str
    _token: str
    _http_client: HttpClient
    _space_specifier_to_id: Dict[SpaceSpecifier, SpaceId]

    def __init__(self, host: str, token: str, *, verify_ssl: bool = True):
        """Construct OnezoneRESTClient instance."""
        self._host = host
        self._token = token
        self._http_client = HttpClient(verify_ssl=verify_ssl)
        self._space_specifier_to_id = {}

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
        result = self._http_client.post(url, {"token": self._token})
        return typing.cast(AccessTokenScope, result.json())

    def list_spaces(self) -> List[SpaceFQN]:
        """List all spaces available for the current token."""
        access_token_scope = self.infer_token_scope()
        all_spaces = access_token_scope["dataAccessScope"]["spaces"]

        supported_spaces = [
            f'{space_details["name"]}@{space_id}'
            for space_id, space_details in all_spaces.items()
            if is_space_supported(space_details)
        ]

        return supported_spaces

    def get_space_id(
            self,
            space_specifier: SpaceSpecifier,
            *,
            access_token_scope: Optional[AccessTokenScope] = None) -> SpaceId:
        """Get space id by specifier."""
        space_id = self._space_specifier_to_id.get(space_specifier)
        if space_id:
            return space_id
        if len(self._space_specifier_to_id) > self._cache_size_limit:
            self._space_specifier_to_id = {}

        if is_fully_qualified_space_name(space_specifier):
            _, space_id = unpack_fully_qualified_space_name(space_specifier)
            return space_id

        if not access_token_scope:
            access_token_scope = self.infer_token_scope()

        all_spaces = access_token_scope["dataAccessScope"]["spaces"]

        for space_id, space_details in all_spaces.items():
            if space_details["name"] == space_specifier:
                return space_id

        raise OnedataRESTError(
            http_code=400,
            error_category="posix",
            error_details=f"Space {space_specifier} does not exist",
            description="enoent")


def is_fully_qualified_space_name(space_specifier: SpaceSpecifier) -> bool:
    """Check if given space specifier if fully qualified."""
    return "@" in space_specifier


def unpack_fully_qualified_space_name(
        space_fqn: SpaceFQN) -> Tuple[SpaceName, SpaceId]:
    """Infer space name and id from fully qualified space name."""
    space_name, space_id = space_fqn.split("@")
    return space_name, space_id


def is_space_supported(space_details: SpaceDetails) -> bool:
    """Check if space is supported."""
    return "supports" in space_details and bool(space_details["supports"])
