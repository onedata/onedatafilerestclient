# coding: utf-8
"""Onedata REST file API client."""
# mypy: disable-error-code="method-assign"

from __future__ import annotations

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = (
    "This software is released under the MIT license cited in LICENSE.txt")

import json
import random
import time
import typing
from functools import lru_cache, wraps
from typing import Any, Callable, Dict, Final, Iterator, NamedTuple, Optional

import requests

import semver  # type: ignore

from . import OnedataRESTError
from .access_token_scope import AccessTokenScope, SpaceDetails
from .httpclient import HttpClient

CACHE_SIZE_LIMIT: Final[int] = 512
BLACKLIST_TIME_LIMIT_NS: Final[int] = 5 * 10**9


class Provider(NamedTuple):
    """Provider relevant attributes."""
    id: str
    version: semver.Version
    domain: str


def _retry_on_provider_connection_error(
        func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(self: OnedataFileRESTClient, space_name: str, *args: Any,
                **kwargs: Any) -> Any:
        for provider in self._iter_available_space_providers(space_name):
            try:
                return func(self, space_name, *args, **kwargs)
            # TODO catch only connection exceptions
            except ValueError:
                self._blaklist_provider(provider.id)

        raise OnedataRESTError(400, 'posix',
                               f'No available providers for space {space_name}',
                               'enoent')  # TODO errno

    return wrapper


class OnedataFileRESTClient:
    """Custom REST client for Onedata REST basic file operations API."""
    onezone_host: str
    token: str
    preferred_oneproviders: list[str]

    client: HttpClient
    token_client: HttpClient

    def __init__(self,
                 onezone_host: str,
                 token: str,
                 preferred_oneproviders: list[str] = [],
                 *,
                 verify_ssl: bool = True):
        """Construct OnedataFileClient instance."""
        super().__setattr__('onezone_host', onezone_host)
        super().__setattr__('token', token)
        self.client = HttpClient(verify_ssl=verify_ssl)
        self.token_client = HttpClient(verify_ssl=verify_ssl)
        self.preferred_oneproviders = preferred_oneproviders

        # lru_cache cannot be used as decorator, as we want to have a separate
        # cache for each OnedataFileRESTClient instance
        self.get_space_id = lru_cache(maxsize=512)(self.get_space_id)

        self.client.get_session().headers.update({'X-Auth-Token': self.token})

        self._init_cache()

    def __setattr__(self, name: str, value: str) -> None:
        """Dissalow modification of selected attributes due to caching."""
        if name in ['token', 'onezone_host']:
            raise AttributeError(
                f'"{name}" attribute cannot be changed after construction.')

        super().__setattr__(name, value)

    def __eq__(self, other: object) -> bool:
        """Compare 2 instances of OnedataFileClient."""
        if not isinstance(other, OnedataFileRESTClient):
            return NotImplemented
        return (self.onezone_host == other.onezone_host) \
            and (self.token == other.token)

    def __hash__(self) -> int:
        """Calculate a hash of a given instance of OnedataFileClient."""
        return hash(self.onezone_host) ^ hash(self.token)

    def oz_url(self, path: str) -> str:
        """Generate Onezone URL for specific path."""
        return f'https://{self.onezone_host}/api/v3/onezone{path}'

    def get_token_scope(self) -> AccessTokenScope:
        """Get current token access scope."""
        url = self.oz_url('/tokens/infer_access_token_scope')
        caps = self.token_client.post(url, {'token': self.token})
        return typing.cast(AccessTokenScope, caps.json())

    def list_spaces(self) -> list[str]:
        """List all spaces available for the current token."""
        access_token_scope = self.get_token_scope()

        def is_space_supported(s: SpaceDetails) -> bool:
            return 'supports' in s and bool(s['supports'])

        all_spaces = access_token_scope['dataAccessScope']['spaces']

        # TODO space_name@space_id ?
        supported_spaces = [
            space_details['name'] for space_details in all_spaces.values()
            if is_space_supported(space_details)
        ]

        return supported_spaces

    def get_space_id(self, space_name: str) -> str:
        """Get space id by name."""
        return self._get_space_id(space_name, self.get_token_scope())

    # TODO handle space_name@space_id
    def _get_space_id(self, space_name: str,
                      access_token_scope: AccessTokenScope) -> str:
        """Get space id by name."""
        spaces = access_token_scope['dataAccessScope']['spaces']

        for space_id, space_details in spaces.items():
            if space_details['name'] == space_name:
                space_id

        raise OnedataRESTError(400, 'posix',
                               f'Space {space_name} doesn\'t exist', 'enoent')

    def get_provider_for_space(self, space_name: str) -> str:
        """Get Oneprovider domain for a specific space."""
        provider = next(self._iter_available_space_providers(space_name))
        return provider.domain

    def op_url(self, space_name: str, path: str) -> str:
        """Generate Oneprovider URL for specific path."""
        provider = self.get_provider_for_space(space_name)
        return f'https://{provider}/api/v3/oneprovider{path}'

    def get_file_id(self,
                    space_name: str,
                    file_path: str,
                    retries: int = 3) -> str:
        """Get Onedata file id based on space name and path."""
        try:
            path = f'/lookup-file-id/{space_name}/{file_path}'
            return typing.cast(
                str,
                self.client.post(self.op_url(space_name,
                                             path)).json()["fileId"])
        except requests.exceptions.ReadTimeout as e:
            if retries > 0:
                return self.get_file_id(space_name, file_path, retries - 1)
            raise e

    @_retry_on_provider_connection_error
    def get_attributes(self,
                       space_name: str,
                       file_path: Optional[str] = None,
                       file_id: Optional[str] = None) -> Dict[str, str]:
        """Get file or directory attributes."""
        if file_id is None:
            if file_path is None:
                file_id = self.get_space_id(space_name)
            else:
                file_id = self.get_file_id(space_name, file_path)

        url = self.op_url(space_name, f'/data/{file_id}')
        result = self.client.get(url).json()
        return typing.cast(Dict[str, str], result)

    @_retry_on_provider_connection_error
    def set_attributes(self, space_name: str, file_path: str,
                       attributes: Dict[str, str]) -> None:
        """Set file or directory attributes."""
        file_id = self.get_file_id(space_name, file_path)
        url = self.op_url(space_name, f'/data/{file_id}')
        self.client.put(url, data=attributes)

    @_retry_on_provider_connection_error
    def readdir(self,
                space_name: str,
                file_path: str,
                limit: int = 1000,
                continuation_token: Optional[str] = None) -> Any:
        """List contents of a directory."""
        if file_path is None:
            # We're listing space contents
            dir_id = self.get_space_id(space_name)
        else:
            dir_id = self.get_file_id(space_name, file_path)

        url = self.op_url(space_name, f'/data/{dir_id}/children')
        data = {"attributes": ["name", "size", "type"]}
        return self.client.get(url, data=data).json()

    @_retry_on_provider_connection_error
    def get_file_content(self,
                         space_name: str,
                         offset: int,
                         size: int,
                         file_path: Optional[str] = None,
                         file_id: Optional[str] = None) -> bytes:
        """Read from a file."""
        file_id = self._ensure_file_id(space_name, file_path, file_id)
        headers = {'Range': f'bytes={offset}-{offset + size - 1}'}
        url = self.op_url(space_name, f'/data/{file_id}/content')
        return self.client.get(url, headers=headers).content

    @_retry_on_provider_connection_error
    def iter_file_content(self,
                          space_name: str,
                          chunk_size: int,
                          file_path: Optional[str] = None,
                          file_id: Optional[str] = None) -> Iterator[bytes]:
        """Iterate file content."""
        file_id = self._ensure_file_id(space_name, file_path, file_id)
        url = self.op_url(space_name, f'/data/{file_id}/content')
        return self.client.get(url, stream=True).iter_content(chunk_size)

    def _ensure_file_id(self,
                        space_name: str,
                        file_path: Optional[str] = None,
                        file_id: Optional[str] = None) -> str:
        if file_id is not None:
            return file_id
        elif file_path is not None:
            return self.get_file_id(space_name, file_path)
        else:
            raise ValueError('Either file_path or file_id must be specified')

    @_retry_on_provider_connection_error
    def put_file_content(self, space_name: str, file_id: str,
                         offset: Optional[int], data: bytes) -> None:
        """Write to a file."""
        headers = {'Content-type': 'application/octet-stream'}
        path_url = f'/data/{file_id}/content'
        if offset is not None:
            path_url += f'?offset={offset}'
        url = self.op_url(space_name, path_url)
        self.client.put(url, data=data, headers=headers)

    @_retry_on_provider_connection_error
    def create_file(self,
                    space_name: str,
                    file_path: str,
                    file_type: str = 'REG',
                    create_parents: bool = False,
                    mode: Optional[int] = None) -> str:
        """Create a file at path."""
        space_id = self.get_space_id(space_name)
        parents = str(create_parents).lower()

        path = f'/data/{space_id}/path/{file_path}'
        path += f'?type={file_type}&create_parents={parents}'

        if mode:
            path += f'&mode={oct(mode)}'

        url = self.op_url(space_name, path)
        result = self.client.put(url, b'').json()['fileId']
        return typing.cast(str, result)

    @_retry_on_provider_connection_error
    def remove(self, space_name: str, file_path: str) -> None:
        """Remove a file or directory."""
        file_id = self.get_file_id(space_name, file_path)
        path = f'/data/{file_id}'
        self.client.delete(self.op_url(space_name, path))

    @_retry_on_provider_connection_error
    def move(self, src_space_name: str, src_file_path: str, dst_space_name: str,
             dst_file_path: str) -> None:
        """Rename a file or directory."""
        # First create the target directory (this assumes that the src_file_path
        # already exists)
        headers = {
            "X-CDMI-Specification-Version": "1.1.1",
            "Content-type": "application/cdmi-object"
        }

        provider = self._provider_for_space[src_space_name]
        url = f'https://{provider.domain}/cdmi/{dst_space_name}/{dst_file_path}'

        data = {'move': f'{src_space_name}/{src_file_path}'}

        self.client.put(url, data=json.dumps(data), headers=headers)

    def _init_cache(self) -> None:
        self._provider_blacklist: Dict[str, int] = {}
        self._provider_for_space: Dict[str, Provider] = {}

    def _is_provider_blacklisted(self, provider_id: str) -> bool:
        if provider_id in self._provider_blacklist:
            blacklist_time_end = self._provider_blacklist[provider_id]
            if blacklist_time_end > time.time_ns():
                True
            else:
                del self._provider_blacklist[provider_id]
                return False

        return False

    def _blaklist_provider(self, provider_id: str) -> None:
        blacklist_time_end = time.time_ns() + BLACKLIST_TIME_LIMIT_NS

        if len(self._provider_blacklist) >= CACHE_SIZE_LIMIT:
            self._provider_blacklist = {provider_id: blacklist_time_end}
        else:
            self._provider_blacklist[provider_id] = blacklist_time_end

    def _iter_available_space_providers(self,
                                        space_name: str) -> Iterator[Provider]:
        if space_name in self._provider_for_space:
            yield self._provider_for_space[space_name]
        elif len(self._provider_for_space) >= CACHE_SIZE_LIMIT:
            # clear cache
            self._provider_for_space = {}

        for provider in self._list_available_space_providers(space_name):
            self._provider_for_space[space_name] = provider
            yield provider

    def _list_available_space_providers(self,
                                        space_name: str) -> list[Provider]:
        access_token_scope = self.get_token_scope()

        all_providers = access_token_scope['dataAccessScope']['providers']

        space_id = self._get_space_id(space_name, access_token_scope)
        space_details = access_token_scope['dataAccessScope']['spaces'][
            space_id]

        preferred_supporting_providers = []
        remaining_supporting_providers = []

        for provider_id in space_details['supports']:
            if self._is_provider_blacklisted(provider_id):
                continue

            provider_details = all_providers[provider_id]
            if not provider_details['online']:
                continue

            provider = Provider(id=provider_id,
                                version=semver.Version.parse(
                                    provider_details['version']),
                                domain=provider_details['domain'])

            try:
                index = self.preferred_oneproviders.index(provider.domain)
                preferred_supporting_providers.append((index, provider))
            except ValueError:
                remaining_supporting_providers.append(provider)

        preferred_supporting_providers.sort()
        random.shuffle(remaining_supporting_providers)

        supporting_providers = [
            provider for _, provider in preferred_supporting_providers
        ]
        supporting_providers.extend(remaining_supporting_providers)

        return supporting_providers
