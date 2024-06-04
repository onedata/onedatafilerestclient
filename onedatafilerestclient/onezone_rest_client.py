# coding: utf-8
"""Onezone REST API client."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2024 Onedata"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import copy
import itertools
import sys
import time
import typing
from functools import lru_cache
from typing import Dict, Final, List, Optional, Tuple, Union, cast

from .errors import SpaceNotFoundError
from .http_client import HttpClient

if sys.version_info < (3, 11):
    from typing_extensions import TypeAlias, TypedDict
else:
    from typing import TypeAlias, TypedDict


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


_SPACE_ID_CACHE_SIZE_LIMIT: Final[int] = 512


class OnezoneRESTClient:
    """Custom REST client for Onezone REST basic operations API."""

    _host: str
    _token: str
    _http_client: HttpClient

    _token_scope_cache: Optional[AccessTokenScope] = None
    _token_scope_cache_valid_until_ns: int = 0
    _token_scope_cache_time_limit_ns: int = 2 * 10**9  # 2 seconds

    def __init__(self, host: str, token: str, *, verify_ssl: bool = True):
        """Construct OnezoneRESTClient instance."""
        self._host = host
        self._token = token
        self._http_client = HttpClient(verify_ssl=verify_ssl)

        # lru_cache cannot be used as decorator, as we want to have a separate
        # cache for each OnezoneRESTClient instance
        self._get_space_id_by_name_cache = lru_cache(
            maxsize=_SPACE_ID_CACHE_SIZE_LIMIT
        )(self._resolve_space_id_by_name)

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
        self._ensure_cached_token_scope_is_up_to_date()
        return cast(AccessTokenScope, copy.deepcopy(self._token_scope_cache))

    def list_spaces(self) -> List[SpaceSpecifier]:
        """List all spaces available for the current token."""
        token_scope = self.infer_token_scope()
        space_registry = token_scope["dataAccessScope"]["spaces"]

        all_space_refs = [
            (space_details["name"], space_id)
            for space_id, space_details in space_registry.items()
        ]
        all_space_refs.sort()

        result: List[SpaceSpecifier] = []
        for space_name, refs_iter in itertools.groupby(
            all_space_refs, key=lambda x: x[0]
        ):
            refs_list = list(refs_iter)
            if len(refs_list) > 1:
                # Multiple spaces with the same name, use fully qualified name
                result.extend(pack_space_fqn(*space_ref) for space_ref in refs_list)
            else:
                # Only one space with this name, use the name alone
                result.append(space_name)

        return result

    def ensure_space_fqn(self, space_specifier: SpaceSpecifier) -> SpaceFQN:
        if is_fully_qualified_space_name(space_specifier):
            return space_specifier

        space_id = self._get_space_id_by_name(space_specifier)
        return pack_space_fqn(space_specifier, space_id)

    def get_space_id(self, space_specifier: SpaceSpecifier) -> SpaceId:
        """Get space id by specifier."""
        if is_fully_qualified_space_name(space_specifier):
            _, space_id = unpack_space_fqn(space_specifier)
            return space_id

        return self._get_space_id_by_name(space_specifier)

    def _get_space_id_by_name(self, space_name: SpaceName) -> SpaceId:
        # ensure space id cache is invalidated in case of token scope change
        self._ensure_cached_token_scope_is_up_to_date()
        return self._get_space_id_by_name_cache(space_name)

    def _resolve_space_id_by_name(self, space_name: SpaceName) -> SpaceId:
        access_token_scope = self.infer_token_scope()
        all_spaces = access_token_scope["dataAccessScope"]["spaces"]

        for space_id, space_details in all_spaces.items():
            if space_details["name"] == space_name:
                return space_id

        raise SpaceNotFoundError(space_name)

    def _ensure_cached_token_scope_is_up_to_date(self) -> None:
        if (
            self._token_scope_cache is None
            or time.time_ns() > self._token_scope_cache_valid_until_ns
        ):
            url = self.build_url("/tokens/infer_access_token_scope")
            result = self._http_client.post(url, {"token": self._token})
            access_token_scope = typing.cast(AccessTokenScope, result.json())

            if self._token_scope_cache != access_token_scope:
                # clear cache as it is possible that e.g. space name has changed
                self._get_space_id_by_name_cache.cache_clear()

            valid_until = time.time_ns() + self._token_scope_cache_time_limit_ns
            self._token_scope_cache = access_token_scope
            self._token_scope_cache_valid_until_ns = valid_until


def is_fully_qualified_space_name(space_specifier: SpaceSpecifier) -> bool:
    """Check if given space specifier if fully qualified."""
    return "@" in space_specifier


def pack_space_fqn(space_name: SpaceName, space_id: SpaceId) -> SpaceFQN:
    """Create space fully qualified name using space name and id."""
    return f"{space_name}@{space_id}"


def unpack_space_fqn(space_fqn: SpaceFQN) -> Tuple[SpaceName, SpaceId]:
    """Infer space name and id from fully qualified space name."""
    space_name, space_id = space_fqn.split("@")
    return space_name, space_id
