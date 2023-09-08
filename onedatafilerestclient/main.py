# coding: utf-8
"""Onedata REST file API client."""

from __future__ import annotations

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = (
    "This software is released under the MIT license cited in LICENSE.txt")

import json
import random
import typing
from functools import lru_cache
from typing import Any, Dict, Optional

import requests

from . import OnedataRESTError
from .httpclient import HttpClient


class OnedataFileRESTClient:
    """Custom REST client for Onedata REST basic file operations API."""
    timeout: int = 5
    onezone_host: str
    token: str
    preferred_oneproviders: list[str]

    client: HttpClient
    token_client: HttpClient

    def __init__(self,
                 onezone_host: str,
                 token: str,
                 preferred_oneproviders: list[str] = []):
        """Construct OnedataFileClient instance."""
        super().__setattr__('onezone_host', onezone_host)
        super().__setattr__('token', token)
        self.client = HttpClient()
        self.token_client = HttpClient()
        self.preferred_oneproviders = preferred_oneproviders

        self.client.get_session().headers.update({'X-Auth-Token': self.token})

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

    def op_url(self, space_name: str, path: str) -> str:
        """Generate Oneprovider URL for specific path."""
        provider = self.get_provider_for_space(space_name)
        return f'https://{provider}/api/v3/oneprovider{path}'

    def get_token_scope(self) -> Any:
        """Get current token access scope."""
        url = self.oz_url('/user/infer_token_scope')
        caps = self.token_client.post(url, {'token': self.token})
        return caps.json()

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

    @lru_cache
    def get_space_id(self, space_name: str) -> Optional[str]:
        """Get space id by name."""
        caps = self.get_token_scope()

        spaces = caps['dataAccessScope']['spaces']

        for space_id in spaces:
            if spaces[space_id]['name'] == space_name:
                return typing.cast(str, space_id)

        raise OnedataRESTError(400, 'posix',
                               f'Space {space_name} doesn\'t exist', 'enoent')

    @lru_cache
    def get_provider_for_space(self, space_name: str) -> str:
        """Get Oneprovider domain for a specific space."""
        space_id = self.get_space_id(space_name)
        caps = self.get_token_scope()
        spaces = caps['dataAccessScope']['spaces']
        providers = caps['dataAccessScope']['providers']
        provider_ids = spaces[space_id]['supports']

        # Select one of the preferred provider domains if matches
        for provider in self.preferred_oneproviders:
            for pid in provider_ids:
                if providers[pid]['domain'] == provider:
                    return provider

        # Otherwise, select a provider randomly
        provider_id = random.choice(list(provider_ids.keys()))
        return typing.cast(str, providers[provider_id]['domain'])

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

    def set_attributes(self, space_name: str, file_path: str,
                       attributes: Dict[str, str]) -> None:
        """Set file or directory attributes."""
        file_id = self.get_file_id(space_name, file_path)
        url = self.op_url(space_name, f'/data/{file_id}')
        self.client.put(url, data=attributes)

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

        path = f'/data/{dir_id}/children?attribute=size&' \
               f'attribute=name&attribute=type'

        url = self.op_url(space_name, path)
        return self.client.get(url).json()

    def list_spaces(self) -> list[str]:
        """List all spaces available for the current token."""
        caps = self.get_token_scope()

        def is_space_supported(s: Dict[str, Any]) -> bool:
            return 'supports' in s and s['supports']

        supported_spaces = []
        spaces = caps['dataAccessScope']['spaces']
        for space_id in spaces:
            space = spaces[space_id]
            if is_space_supported(space):
                supported_spaces.append(space['name'])

        return supported_spaces

    def get_file_content(self,
                         space_name: str,
                         offset: int,
                         size: int,
                         file_path: Optional[str] = None,
                         file_id: Optional[str] = None) -> bytes:
        """Read from a file."""
        if file_id is None:
            if file_path is None:
                raise ValueError(
                    'Both file_path and file_id arguments cannot be None')
            file_id = self.get_file_id(space_name, file_path)
        headers = {'Range': f'bytes={offset}-{offset + size - 1}'}
        path = f'/data/{file_id}/content'
        url = self.op_url(space_name, path)
        result = self.client.get(url, headers=headers).content
        return result

    def put_file_content(self, space_name: str, file_id: str,
                         offset: Optional[int], data: bytes) -> None:
        """Write to a file."""
        headers = {'Content-type': 'application/octet-stream'}
        path_url = f'/data/{file_id}/content'
        if offset is not None:
            path_url += f'?offset={offset}'
        url = self.op_url(space_name, path_url)
        self.client.put(url, data=data, headers=headers)

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

    def remove(self, space_name: str, file_path: str) -> None:
        """Remove a file or directory."""
        file_id = self.get_file_id(space_name, file_path)
        path = f'/data/{file_id}'
        self.client.delete(self.op_url(space_name, path))

    def move(self, src_space_name: str, src_file_path: str, dst_space_name: str,
             dst_file_path: str) -> None:
        """Rename a file or directory."""
        # First create the target directory (this assumes that the src_file_path
        # already exists)
        headers = {
            "X-CDMI-Specification-Version": "1.1.1",
            "Content-type": "application/cdmi-object"
        }

        provider = self.get_provider_for_space(dst_space_name)
        url = f'https://{provider}/cdmi/{dst_space_name}/{dst_file_path}'

        data = {'move': f'{src_space_name}/{src_file_path}'}

        self.client.put(url, data=json.dumps(data), headers=headers)
