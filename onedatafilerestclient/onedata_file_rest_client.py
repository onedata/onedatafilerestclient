# coding: utf-8
"""Onedata REST file API client."""

from __future__ import annotations

import json
import sys
import typing
from functools import partial, wraps
from typing import Any, Callable, Dict, Iterator, List, Optional

import requests.exceptions

from .errors import NoAvailableProviderForSpaceError, ReadonlyTokenError
from .file_attributes import (
    FileAttrKey,
    FileAttrsJson,
    FileType,
    build_http_get_file_attr_params,
    build_http_list_children_attrs_params,
    normalize_file_attrs_json,
)
from .http_client import HttpClient
from .onezone_rest_client import (
    AccessTokenScope,
    OnezoneRESTClient,
    SpaceFQN,
    SpaceId,
    SpaceSpecifier,
)
from .provider_selector import (
    ProviderSelector,
    ProviderSpecifier,
    SpaceSupportingProvider,
)

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"


if sys.version_info < (3, 11):
    from typing_extensions import TypeAlias, TypedDict
else:
    from typing import TypeAlias, TypedDict


FileId: TypeAlias = str
FilePath: TypeAlias = str
"""
File path relative to space, that is without space specifier prefix.
"""


class ListChildrenResult(TypedDict):
    """Directory listing result.

    Refer to the API specification for more information:
    https://onedata.org/#/home/api/stable/oneprovider?anchor=operation/list_children
    """

    children: List[FileAttrsJson]
    isLast: bool
    nextPageToken: Optional[str]


def _find_available_provider(
    func: Optional[Callable[..., Any]] = None, *, except_readonly: bool = False
) -> Callable[..., Any]:
    if func is None:
        return partial(_find_available_provider, except_readonly=except_readonly)

    @wraps(func)
    def wrapper(
        self: OnedataFileRESTClient,
        space_specifier: SpaceSpecifier,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if except_readonly:
            access_token_scope = self.get_token_scope()
            if access_token_scope["dataAccessScope"]["readonly"]:
                raise ReadonlyTokenError

        # pylint: disable=W0212
        oz_client = self._oz_client
        provider_selector = self._provider_selector

        space_fqn = oz_client.ensure_space_fqn(space_specifier)

        provider = kwargs.get("provider")
        if provider is not None:
            return func(self, space_fqn, *args, **kwargs)

        for provider in provider_selector.iter_available_space_providers(
            space_fqn,
            oz_rest_client=oz_client,
            except_readonly=except_readonly,
        ):
            try:
                kwargs["provider"] = provider
                return func(self, space_fqn, *args, **kwargs)
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout,
            ):
                provider_selector.blacklist(provider)

        raise NoAvailableProviderForSpaceError(space_specifier)

    return wrapper


class OnedataFileRESTClient:
    """Custom REST client for Onedata REST basic file operations API."""

    _oz_client: OnezoneRESTClient
    _provider_selector: ProviderSelector
    _op_client: HttpClient

    def __init__(
        self,
        onezone_host: str,
        token: str,
        preferred_providers: Optional[List[ProviderSpecifier]] = None,
        *,
        verify_ssl: bool = True,
    ):
        """Construct OnedataFileRESTClient instance."""
        self._oz_client = OnezoneRESTClient(
            host=onezone_host, token=token, verify_ssl=verify_ssl
        )
        self._provider_selector = ProviderSelector(
            preferred_providers=preferred_providers
        )

        self._op_client = HttpClient(verify_ssl=verify_ssl)
        self._op_client.get_session().headers.update({"X-Auth-Token": token})

    def __eq__(self, other: object) -> bool:
        """Compare 2 instances of OnedataFileRESTClient."""
        if not isinstance(other, OnedataFileRESTClient):
            return NotImplemented

        return self._oz_client == other._oz_client

    def __hash__(self) -> int:
        """Calculate a hash of a given instance of OnedataFileRESTClient."""
        return hash(self._oz_client)

    def get_token_scope(self) -> AccessTokenScope:
        """Get current token access scope."""
        return self._oz_client.infer_token_scope()

    def list_spaces(self) -> List[SpaceFQN]:
        """List all spaces available for the current token."""
        return self._oz_client.list_spaces()

    def get_space_id(self, space_specifier: SpaceSpecifier) -> SpaceId:
        """Get space id by specifier."""
        return self._oz_client.get_space_id(space_specifier)

    @_find_available_provider
    def get_file_id(
        self,
        space_specifier: SpaceSpecifier,
        *,
        file_path: Optional[FilePath] = None,
        retries: int = 3,
        provider: Optional[SpaceSupportingProvider] = None,
    ) -> FileId:
        """Get Onedata file id based on space specifier and file path."""
        provider = self._ensure_provider(provider)

        rest_path = f"/lookup-file-id/{space_specifier}"
        if file_path is not None:
            rest_path += f"/{file_path.lstrip('/')}"
        url = self._build_op_url(provider, rest_path)

        while True:
            try:
                file_id = self._op_client.post(url).json()["fileId"]
                return typing.cast(FileId, file_id)
            except requests.exceptions.ReadTimeout as e:
                if retries <= 0:
                    raise e

                retries -= 1

    @_find_available_provider
    def get_attributes(
        self,
        space_specifier: SpaceSpecifier,
        *,
        attributes: Optional[List[FileAttrKey]] = None,
        file_path: Optional[FilePath] = None,
        file_id: Optional[FileId] = None,
        provider: Optional[SpaceSupportingProvider] = None,
    ) -> FileAttrsJson:
        """Get file or directory attributes."""
        provider = self._ensure_provider(provider)
        file_id = self._resolve_file_id(
            space_specifier, file_path=file_path, file_id=file_id, provider=provider
        )
        url = self._build_op_url(provider, f"/data/{file_id}")
        qs, body = build_http_get_file_attr_params(provider, attributes)
        if qs:
            url += f"?{qs}"

        result = self._op_client.get(url, data=body).json()
        attrs = normalize_file_attrs_json(provider, attributes, result)

        return typing.cast(FileAttrsJson, attrs)

    @_find_available_provider(except_readonly=True)
    def set_attributes(
        self,
        space_specifier: SpaceSpecifier,
        attributes: Dict[str, str],
        *,
        file_path: Optional[FilePath] = None,
        file_id: Optional[FileId] = None,
        provider: Optional[SpaceSupportingProvider] = None,
    ) -> None:
        """Set file or directory attributes."""
        provider = self._ensure_provider(provider)
        file_id = self._resolve_file_id(
            space_specifier, file_path=file_path, file_id=file_id, provider=provider
        )
        url = self._build_op_url(provider, f"/data/{file_id}")
        self._op_client.put(url, data=attributes)

    @_find_available_provider
    def list_children(
        self,
        space_specifier: SpaceSpecifier,
        *,
        attributes: Optional[List[FileAttrKey]] = None,
        limit: int = 1000,
        continuation_token: Optional[str] = None,
        file_path: Optional[FilePath] = None,
        file_id: Optional[FileId] = None,
        provider: Optional[SpaceSupportingProvider] = None,
    ) -> ListChildrenResult:
        """List contents of a directory."""
        provider = self._ensure_provider(provider)
        dir_file_id = self._resolve_file_id(
            space_specifier, file_path=file_path, file_id=file_id, provider=provider
        )
        qs = f"?limit={limit}"
        if continuation_token is not None:
            qs += f"&token={continuation_token}"

        if not attributes:
            attributes = ["name", "type"]

        qs_attrs, body = build_http_list_children_attrs_params(provider, attributes)
        if qs_attrs:
            qs += f"&{qs_attrs}"

        url = self._build_op_url(provider, f"/data/{dir_file_id}/children{qs}")
        result = self._op_client.get(url, data=body).json()
        result["children"] = [
            normalize_file_attrs_json(provider, attributes, file_attrs_json)
            for file_attrs_json in result["children"]
        ]

        return typing.cast(ListChildrenResult, result)

    @_find_available_provider
    def get_file_content(
        self,
        space_specifier: SpaceSpecifier,
        *,
        offset: int = 0,
        size: Optional[int] = None,
        file_path: Optional[FilePath] = None,
        file_id: Optional[FileId] = None,
        provider: Optional[SpaceSupportingProvider] = None,
    ) -> bytes:
        """Read from a file."""
        provider = self._ensure_provider(provider)
        file_id = self._resolve_file_id(
            space_specifier, file_path=file_path, file_id=file_id, provider=provider
        )
        if size is not None:
            headers = {"Range": f"bytes={offset}-{offset + size - 1}"}
        else:
            headers = {}

        url = self._build_op_url(provider, f"/data/{file_id}/content")
        return self._op_client.get(url, headers=headers).content

    @_find_available_provider
    def iter_file_content(
        self,
        space_specifier: SpaceSpecifier,
        *,
        chunk_size: int = 1048576,  # 1 MB
        file_path: Optional[FilePath] = None,
        file_id: Optional[FileId] = None,
        provider: Optional[SpaceSupportingProvider] = None,
    ) -> Iterator[bytes]:
        """Iterate file content."""
        provider = self._ensure_provider(provider)
        file_id = self._resolve_file_id(
            space_specifier, file_path=file_path, file_id=file_id, provider=provider
        )
        url = self._build_op_url(provider, f"/data/{file_id}/content")
        return self._op_client.get(url, stream=True).iter_content(chunk_size)

    @_find_available_provider(except_readonly=True)
    def put_file_content(
        self,
        space_specifier: SpaceSpecifier,
        data: bytes,
        *,
        offset: Optional[int] = None,
        file_path: Optional[FilePath] = None,
        file_id: Optional[FileId] = None,
        provider: Optional[SpaceSupportingProvider] = None,
    ) -> None:
        """Write to a file."""
        provider = self._ensure_provider(provider)
        file_id = self._resolve_file_id(
            space_specifier, file_path=file_path, file_id=file_id, provider=provider
        )
        headers = {"Content-type": "application/octet-stream"}
        qs = f"?offset={offset}" if offset is not None else ""
        url = self._build_op_url(provider, f"/data/{file_id}/content{qs}")
        self._op_client.put(url, data=data, headers=headers)

    @_find_available_provider(except_readonly=True)
    def create_file(
        self,
        space_specifier: SpaceSpecifier,
        file_path: FilePath,
        *,
        file_type: FileType = "REG",
        create_parents: bool = False,
        mode: Optional[int] = None,
        provider: Optional[SpaceSupportingProvider] = None,
    ) -> FileId:
        """Create a file at path."""
        provider = self._ensure_provider(provider)
        space_id = self.get_space_id(space_specifier)
        parents = str(create_parents).lower()

        path = f"/data/{space_id}/path/{file_path}"
        path += f"?type={file_type}&create_parents={parents}"

        if mode:
            path += f"&mode={oct(mode).lstrip('0o')}"

        url = self._build_op_url(provider, path)
        result = self._op_client.put(url, b"").json()["fileId"]
        return typing.cast(FileId, result)

    @_find_available_provider(except_readonly=True)
    def remove(
        self,
        space_specifier: SpaceSpecifier,
        *,
        file_path: Optional[FilePath] = None,
        file_id: Optional[FileId] = None,
        provider: Optional[SpaceSupportingProvider] = None,
    ) -> None:
        """Remove a file or directory."""
        provider = self._ensure_provider(provider)
        file_id = self._resolve_file_id(
            space_specifier, file_path=file_path, file_id=file_id, provider=provider
        )
        url = self._build_op_url(provider, f"/data/{file_id}")
        self._op_client.delete(url)

    @_find_available_provider(except_readonly=True)
    def move(
        self,
        src_space_specifier: SpaceSpecifier,
        src_file_path: FilePath,
        dst_space_specifier: SpaceSpecifier,
        dst_file_path: FilePath,
        *,
        provider: Optional[SpaceSupportingProvider] = None,
    ) -> None:
        """Rename a file or directory."""
        provider = self._ensure_provider(provider)
        headers = {
            "X-CDMI-Specification-Version": "1.1.1",
            "Content-type": "application/cdmi-object",
        }
        url = f"https://{provider.domain}/cdmi/{dst_space_specifier}/{dst_file_path}"

        data = {"move": f"{src_space_specifier}/{src_file_path}"}

        self._op_client.put(url, data=json.dumps(data), headers=headers)

    @staticmethod
    def _ensure_provider(
        provider: Optional[SpaceSupportingProvider],
    ) -> SpaceSupportingProvider:
        if provider is None:
            raise ValueError("Missing required 'provider' argument.")

        return provider

    def _resolve_file_id(
        self,
        space_specifier: SpaceSpecifier,
        *,
        file_path: Optional[FilePath] = None,
        file_id: Optional[FileId] = None,
        provider: SpaceSupportingProvider,
    ) -> FileId:
        if file_id is not None:
            return file_id

        if file_path is not None:
            file_id = self.get_file_id(
                space_specifier, file_path=file_path, provider=provider
            )
            return typing.cast(FileId, file_id)

        return self.get_space_id(space_specifier)

    @staticmethod
    def _build_op_url(provider: SpaceSupportingProvider, rest_path: str) -> str:
        if not rest_path.startswith("/"):
            rest_path = "/" + rest_path

        return f"https://{provider.domain}/api/v3/oneprovider{rest_path}"
