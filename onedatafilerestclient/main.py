# coding: utf-8
"""Onedata REST file API client."""
# mypy: disable-error-code="method-assign"

from __future__ import annotations

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = (
    "This software is released under the MIT license cited in LICENSE.txt")

import json
import typing
from functools import wraps
from typing import Any, Callable, Dict, Iterator, List, Optional

import requests

from . import OnedataRESTError
from .httpclient import HttpClient
from .onezone_rest_client import AccessTokenScope, OnezoneRESTClient
from .provider_selector import ProviderSelector


def _retry_on_provider_connection_error(
        func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(self: OnedataFileRESTClient, space_name: str, *args: Any,
                **kwargs: Any) -> Any:
        for provider in self._provider_selector.iter_available_space_providers(
                space_name, oz_rest_client=self._oz_client):
            try:
                return func(self, space_name, *args, **kwargs)
            # TODO catch only connection exceptions
            except ValueError:
                self._provider_selector.blacklist(provider.id)

        raise OnedataRESTError(400, 'posix',
                               f'No available providers for space {space_name}',
                               'enoent')  # TODO errno

    return wrapper


class OnedataFileRESTClient:
    """Custom REST client for Onedata REST basic file operations API."""

    # TODO property?
    onezone_host: str
    token: str
    preferred_oneproviders: list[str]

    client: HttpClient

    def __init__(self,
                 onezone_host: str,
                 token: str,
                 preferred_oneproviders: list[str] = [],
                 *,
                 verify_ssl: bool = True):
        """Construct OnedataFileClient instance."""
        self._oz_client = OnezoneRESTClient(host=onezone_host,
                                            token=token,
                                            verify_ssl=verify_ssl)
        self._provider_selector = ProviderSelector(
            preferred_provider_domains=preferred_oneproviders)

        self.client = HttpClient(verify_ssl=verify_ssl)
        self.client.get_session().headers.update({'X-Auth-Token': self.token})

    def __eq__(self, other: object) -> bool:
        """Compare 2 instances of OnedataFileClient."""
        if not isinstance(other, OnedataFileRESTClient):
            return NotImplemented

        return self._oz_client == other._oz_client

    def __hash__(self) -> int:
        """Calculate a hash of a given instance of OnedataFileClient."""
        return hash(self._oz_client)

    def oz_url(self, path: str) -> str:
        """Generate Onezone URL for specific path."""
        return self._oz_client.build_url(path)

    def get_token_scope(self) -> AccessTokenScope:
        """Get current token access scope."""
        return self._oz_client.infer_token_scope()

    def list_spaces(self) -> List[str]:
        """List all spaces available for the current token."""
        return self._oz_client.list_spaces()

    def get_space_id(self, space_name: str) -> str:
        """Get space id by name."""
        return self._oz_client.get_space_id(space_name)

    def get_provider_for_space(self, space_name: str) -> str:
        """Get Oneprovider domain for a specific space."""
        provider = next(
            self._provider_selector.iter_available_space_providers(
                space_name, oz_rest_client=self._oz_client))
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

        provider_domain = self.get_provider_for_space(src_space_name)
        url = f'https://{provider_domain}/cdmi/{dst_space_name}/{dst_file_path}'

        data = {'move': f'{src_space_name}/{src_file_path}'}

        self.client.put(url, data=json.dumps(data), headers=headers)
