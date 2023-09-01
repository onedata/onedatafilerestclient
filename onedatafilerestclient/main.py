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

from .httpclient import HttpClient


class OnedataFileRESTClient(HttpClient):
    """Custom REST client for Onedata REST basic file operations API."""
    timeout: int = 5
    onezone_host: str
    token: str

    def __init__(self, onezone_host: str, token: str):
        """Construct OnedataFileClient instance."""
        super().__setattr__('onezone_host', 'aaa')
        super().__setattr__('token', token)
        self.session = requests.Session()
        self.session.headers.update({'X-Auth-Token': self.token})

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
        caps = """
        {
            "spaces": {
                "84af6570d3e133c7164e52594b368f22ch7d58": {
                    "name": "test01",
                    "supports": {
                        "d8190b4632eccaeaf1f2128f267c4176che3cf": {
                            "readonly": true
                        }
                    }
                },
                "03b1fdcdef49c3d013342c3a3ef9cbb8chfadd": {
                    "name": "test02",
                    "supports": {
                        "d8190b4632eccaeaf1f2128f267c4176che3cf": {
                            "readonly": true
                        }
                    }
                }
            },
            "providers": {
                "d8190b4632eccaeaf1f2128f267c4176che3cf": {
                  "domain": "dev-oneprovider-krakow.default.svc.cluster.local",
                  "version": "23.02.1",
                  "online": true
                }
            }
        }
        """
        return json.loads(caps)

    @lru_cache
    def get_space_id(self, space_name: str) -> Optional[str]:
        """Get space id by name."""
        caps = self.get_token_scope()

        spaces = caps['spaces']

        for space_id in spaces:
            if spaces[space_id]['name'] == space_name:
                return typing.cast(str, space_id)

        return None

    def get_file_id(self,
                    space_name: str,
                    file_path: str,
                    retries: int = 3) -> str:
        """Get Onedata file id based on space name and path."""
        try:
            path = f'/lookup-file-id/{space_name}/{file_path}'
            return typing.cast(
                str,
                self._post(self.op_url(space_name, path)).json()["fileId"])
        except requests.exceptions.ReadTimeout as e:
            if retries > 0:
                return self.get_file_id(space_name, file_path, retries - 1)
            raise e

    @lru_cache
    def get_provider_for_space(self, space_name: str) -> str:
        """Get Oneprovider domain for a specific space."""
        space_id = self.get_space_id(space_name)
        caps = self.get_token_scope()
        provider_ids = caps['spaces'][space_id]['supports']
        provider_id = random.choice(list(provider_ids.keys()))
        return typing.cast(str, caps['providers'][provider_id]['domain'])

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
        result = self._get(url).json()
        return typing.cast(Dict[str, str], result)

    def set_attributes(self, space_name: str, file_path: str,
                       attributes: Dict[str, str]) -> None:
        """Set file or directory attributes."""
        file_id = self.get_file_id(space_name, file_path)
        url = self.op_url(space_name, f'/data/{file_id}')
        self._put(url, data=attributes)

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
        return self._get(url).json()

    def list_spaces(self) -> list[str]:
        """List all spaces available for the current token."""
        caps = self.get_token_scope()

        def is_space_supported(s: Dict[str, Any]) -> bool:
            return 'supports' in s and s['supports']

        supported_spaces = []
        for space_id in caps['spaces']:
            space = caps['spaces'][space_id]
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
        result = self._get(url, headers=headers).content
        return result

    def put_file_content(self, space_name: str, file_id: str,
                         offset: Optional[int], data: bytes) -> None:
        """Write to a file."""
        headers = {'Content-type': 'application/octet-stream'}
        path_url = f'/data/{file_id}/content'
        if offset is not None:
            path_url += f'?offset={offset}'
        url = self.op_url(space_name, path_url)
        self._put(url, data=data, headers=headers)

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
        result = self._put(url, b'').json()['fileId']
        return typing.cast(str, result)

    def remove(self, space_name: str, file_path: str) -> None:
        """Remove a file or directory."""
        space_id = self.get_space_id(space_name)
        path = f'/data/{space_id}/path/{file_path}'
        self._delete(self.op_url(space_name, path))

    def move(self, src_space_name: str, src_file_path: str,
             dst_space_name: str, dst_file_path: str) -> None:
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

        self._put(url, data=json.dumps(data), headers=headers)
