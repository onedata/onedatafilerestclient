# coding: utf-8
"""Definitions and utilities for handling file attributes.

Refer to the API specification for more information:
https://onedata.org/#/home/api/latest/oneprovider?anchor=operation/get_attrs
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2024 Onedata"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import sys
from typing import Any, Dict, Final, List, Literal, Optional, Tuple, Union, cast

from packaging.version import Version

from .errors import OnedataRESTError
from .provider_selector import SpaceSupportingProvider

if sys.version_info < (3, 11):
    from typing_extensions import TypeAlias, TypedDict
else:
    from typing import TypeAlias, TypedDict


_MIN_SUPPORTED_PROVIDER_API_VERSION: Final[Version] = Version("21.2.1")
_PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION: Final[Version] = Version("21.2.5")

_NOT_SUPPORTED_ATTR_ERROR_DETAILS_FMT: Final[str] = (
    "The provider chosen for this space ({domain}) is in version ({version}) "
    "that does not support the '{attr}' attribute (requires Oneprovider "
    "version >= {min_required_version})"
)

BasicFileAttrKey: TypeAlias = Literal[
    "fileId",
    "index",
    "type",
    "activePermissionsType",
    "posixPermissions",
    "acl",
    "name",
    "conflictingName",
    "path",
    "parentFileId",
    "displayGid",
    "displayUid",
    "creationTime",
    "atime",
    "mtime",
    "ctime",
    "size",
    "isFullyReplicatedLocally",
    "localReplicationRate",
    "originProviderId",
    "directShareIds",
    "ownerUserId",
    "hardlinkCount",
    "symlinkValue",
    "hasCustomMetadata",
    "effProtectionFlags",
    "effDatasetProtectionFlags",
    "effDatasetInheritancePath",
    "effQosInheritancePath",
    "aggregateQosStatus",
    "archiveRecallRootFileId",
]

_MIN_PROVIDER_VERSION_SUPPORTING_BASIC_ATTR_KEY: Final[
    Dict[BasicFileAttrKey, Version]
] = {
    "fileId": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "index": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "type": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "activePermissionsType": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "posixPermissions": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "acl": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "name": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "conflictingName": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "path": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "parentFileId": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "displayGid": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "displayUid": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "creationTime": Version("21.2.6"),
    "atime": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "mtime": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "ctime": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "size": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "isFullyReplicatedLocally": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "localReplicationRate": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "originProviderId": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "directShareIds": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "ownerUserId": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "hardlinkCount": _MIN_SUPPORTED_PROVIDER_API_VERSION,
    "symlinkValue": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "hasCustomMetadata": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "effProtectionFlags": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "effDatasetProtectionFlags": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "effDatasetInheritancePath": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "effQosInheritancePath": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "aggregateQosStatus": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
    "archiveRecallRootFileId": _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION,
}

XattrKey: TypeAlias = str
"""
File extended attribute in the form xattr.<NAME>
"""

FileAttrKey = Union[BasicFileAttrKey, XattrKey]

_SNAKE_CASE_BASIC_FILE_ATTR_KEYS: Final[Dict[BasicFileAttrKey, str]] = {
    "fileId": "file_id",
    "index": "index",
    "type": "type",
    "posixPermissions": "mode",
    "name": "name",
    "parentFileId": "parent_id",
    "displayGid": "storage_group_id",
    "displayUid": "storage_user_id",
    "atime": "atime",
    "mtime": "mtime",
    "ctime": "ctime",
    "size": "size",
    "originProviderId": "provider_id",
    "directShareIds": "shares",
    "ownerUserId": "owner_id",
    "hardlinkCount": "hardlinks_count",
}

_DEFAULT_API_FILE_ATTR_KEYS: Final[List[FileAttrKey]] = [
    "fileId",
    "parentFileId",
    "name",
    "posixPermissions",
    "atime",
    "mtime",
    "ctime",
    "type",
    "size",
    "directShareIds",
    "index",
    "displayGid",
    "displayUid",
    "ownerUserId",
    "originProviderId",
    "hardlinkCount",
]

FileType: TypeAlias = Literal["REG", "DIR", "SYMLNK"]
ProtectionFlag: TypeAlias = Literal["data_protection", "metadata_protection"]
InheritancePath: TypeAlias = Literal[
    "none", "direct", "ancestor", "direct_and_ancestor"
]


class FileAttrsJson(TypedDict, total=False):
    """
    File attributes.

    Refer to the API specification for more information:
    https://onedata.org/#/home/api/latest/oneprovider?anchor=operation/get_attrs

    NOTE: dynamic fields like `xattr.*` are not typed due to limitations
    of typing machinery.
    """

    fileId: str
    index: str
    type: FileType
    activePermissionsType: Literal["posix", "acl"]
    posixPermissions: str
    acl: List[Any]
    name: str
    conflictingName: Optional[str]
    path: str
    parentFileId: Optional[str]
    displayGid: int
    displayUid: int
    creationTime: int
    atime: int
    mtime: int
    ctime: int
    size: Optional[int]
    isFullyReplicatedLocally: Optional[bool]
    localReplicationRate: float
    originProviderId: str
    directShareIds: List[str]
    ownerUserId: str
    hardlinkCount: int
    symlinkValue: Optional[str]
    hasCustomMetadata: bool
    effProtectionFlags: List[ProtectionFlag]
    effDatasetProtectionFlags: List[ProtectionFlag]
    effDatasetInheritancePath: InheritancePath
    effQosInheritancePath: InheritancePath
    aggregateQosStatus: Literal["fulfilled", "pending", "impossible"]
    archiveRecallRootFileId: Optional[str]


def build_http_get_file_attr_params(
    provider: SpaceSupportingProvider, requested_attr_keys: Optional[List[FileAttrKey]]
) -> Tuple[Optional[str], Optional[Dict[str, List[str]]]]:
    """Build query string and body for HTTP request to retrieve file attributes.

    NOTE: In case not all requested attributes are supported by selected
    provider exception will be raised.
    """
    qs = None
    body = None

    if requested_attr_keys is not None:
        _assert_attr_keys_supported(provider, requested_attr_keys)

        if provider.version < _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION:
            # Due to a bug it is not possible to fetch more than one specific
            # attribute for file using old API. Trying to do so results in empty
            # json returned. As a workaround all attributes are fetched (no qs)
            if len(requested_attr_keys) <= 1:
                qs = "&".join(
                    f"attribute={_get_snake_case_attr_key(attr_key)}"
                    for attr_key in requested_attr_keys
                )
        else:
            body = {"attributes": requested_attr_keys}

    return qs, body


def build_http_list_children_attrs_params(
    provider: SpaceSupportingProvider, requested_attr_keys: Optional[List[FileAttrKey]]
) -> Tuple[Optional[str], Optional[Dict[str, List[str]]]]:
    """Build query string and body for HTTP request to retrieve file attributes.

    NOTE: In case not all requested attributes are supported by selected
    provider exception will be raised.
    """
    qs = None
    body = None

    if requested_attr_keys is not None:
        _assert_attr_keys_supported(provider, requested_attr_keys)

        if provider.version < _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION:
            qs = "&".join(
                f"attribute={_get_snake_case_attr_key(attr_key)}"
                for attr_key in requested_attr_keys
            )
        else:
            body = {"attributes": requested_attr_keys}

    return qs, body


def _assert_attr_keys_supported(
    provider: SpaceSupportingProvider, attr_keys: List[FileAttrKey]
) -> None:
    for attr_key in attr_keys:
        _assert_attr_key_supported(provider, attr_key)


def _assert_attr_key_supported(
    provider: SpaceSupportingProvider, attr_key: FileAttrKey
) -> None:
    if attr_key.startswith("xattr."):
        min_required_version = _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION
    else:
        min_required_version = _MIN_PROVIDER_VERSION_SUPPORTING_BASIC_ATTR_KEY[
            cast(BasicFileAttrKey, attr_key)
        ]

    if provider.version < min_required_version:
        raise OnedataRESTError(
            http_code=400,
            category="posix",
            description="einval",
            details=_NOT_SUPPORTED_ATTR_ERROR_DETAILS_FMT.format(
                attr=attr_key,
                domain=provider.domain,
                version=provider.version,
                min_required_version=min_required_version,
            ),
        )


def normalize_file_attrs_json(
    provider: SpaceSupportingProvider,
    requested_attr_keys: Optional[List[FileAttrKey]],
    file_attrs_json: Dict[str, Any],
) -> FileAttrsJson:
    """Translate attributes api keys to current ones for older providers."""
    if not requested_attr_keys:
        # default api attrs
        requested_attr_keys = _DEFAULT_API_FILE_ATTR_KEYS

    if provider.version < _PROVIDER_SUPPORTING_CAMEL_CASE_API_KEYS_MIN_VERSION:
        sanitized_file_attrs_json = {
            attr_key: file_attrs_json[_get_snake_case_attr_key(attr_key)]
            for attr_key in requested_attr_keys
        }
    else:
        sanitized_file_attrs_json = {
            attr_key: file_attrs_json[attr_key] for attr_key in requested_attr_keys
        }

    return cast(FileAttrsJson, sanitized_file_attrs_json)


def _get_snake_case_attr_key(attr_key: FileAttrKey) -> str:
    return _SNAKE_CASE_BASIC_FILE_ATTR_KEYS[cast(BasicFileAttrKey, attr_key)]
