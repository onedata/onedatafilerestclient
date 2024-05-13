# coding: utf-8
"""Definitions and utilities for handling file attributes.

Refer to the API specification for more information:
https://onedata.org/#/home/api/latest/oneprovider?anchor=operation/get_attrs
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2024 Onedata"
__license__ = (
    "This software is released under the MIT license cited in LICENSE.txt")

import sys
from enum import Enum
from typing import (Any, Dict, Final, List, Literal, NamedTuple, Optional,
                    Tuple, Union, cast)

from packaging.version import Version  # type: ignore

if sys.version_info < (3, 11):
    from typing_extensions import TypeAlias, TypedDict
else:
    from typing import TypeAlias, TypedDict

from .errors import OnedataRESTError
from .provider_selector import Provider

_PROVIDER_SUPPORTING_CURRENT_API_KEY_MIN_VERSION: Final[Version] = Version(
    "21.02.5")

_NOT_SUPPORTED_ATTR_ERROR_DETAILS_FMT: Final[str] = (
    "The provider chosen for this space ({domain}) is in version ({version}) "
    "that does not support the '{attr}' attribute (requires Oneprovider "
    f"version >= {_PROVIDER_SUPPORTING_CURRENT_API_KEY_MIN_VERSION})")


class _FileBasicAttrApiKey(NamedTuple):
    current_key: str
    deprecated_key: Optional[str] = None


class BasicFileAttr(Enum):
    """Enumeration of files basic attributes stored in a Onedata filesystem."""
    FILE_ID = _FileBasicAttrApiKey(current_key="fileId",
                                   deprecated_key="file_id")
    INDEX = _FileBasicAttrApiKey(current_key="index", deprecated_key="index")
    TYPE = _FileBasicAttrApiKey(current_key="type", deprecated_key="type")
    ACTIVE_PERMISSIONS_TYPE = _FileBasicAttrApiKey(
        current_key="activePermissionsType")
    POSIX_PERMISSIONS = _FileBasicAttrApiKey(current_key="posixPermissions",
                                             deprecated_key="mode")
    ACL = _FileBasicAttrApiKey(current_key="acl")
    NAME = _FileBasicAttrApiKey(current_key="name", deprecated_key="name")
    CONFLICTING_NAME = _FileBasicAttrApiKey(current_key="conflictingName")
    PATH = _FileBasicAttrApiKey(current_key="path")
    PARENT_FILE_ID = _FileBasicAttrApiKey(current_key="parentFileId",
                                          deprecated_key="parent_id")
    DISPLAY_GID = _FileBasicAttrApiKey(current_key="displayGid",
                                       deprecated_key="storage_group_id")
    DISPLAY_UID = _FileBasicAttrApiKey(current_key="displayUid",
                                       deprecated_key="storage_user_id")
    ATIME = _FileBasicAttrApiKey(current_key="atime", deprecated_key="atime")
    MTIME = _FileBasicAttrApiKey(current_key="mtime", deprecated_key="mtime")
    CTIME = _FileBasicAttrApiKey(current_key="ctime", deprecated_key="ctime")
    SIZE = _FileBasicAttrApiKey(current_key="size", deprecated_key="size")
    IS_FULLY_REPLICATED_LOCALLY = _FileBasicAttrApiKey(
        current_key="isFullyReplicatedLocally")
    LOCAL_REPLICATION_RATE = _FileBasicAttrApiKey(
        current_key="localReplicationRate")
    ORIGIN_PROVIDER_ID = _FileBasicAttrApiKey(current_key="originProviderId",
                                              deprecated_key="provider_id")
    DIRECT_SHARE_IDS = _FileBasicAttrApiKey(current_key="directShareIds",
                                            deprecated_key="shares")
    OWNER_USER_ID = _FileBasicAttrApiKey(current_key="ownerUserId",
                                         deprecated_key="owner_id")
    HARDLINK_COUNT = _FileBasicAttrApiKey(current_key="hardlinkCount",
                                          deprecated_key="hardlinks_count")
    SYMLINK_VALUE = _FileBasicAttrApiKey(current_key="symlinkValue")
    HAS_CUSTOM_METADATA = _FileBasicAttrApiKey(current_key="hasCustomMetadata")
    EFF_PROTECTION_FLAGS = _FileBasicAttrApiKey(
        current_key="effProtectionFlags")
    EFF_DATASET_PROTECTION_FLAGS = _FileBasicAttrApiKey(
        current_key="effDatasetProtectionFlags")
    EFF_DATASET_INHERITANCE_PATH = _FileBasicAttrApiKey(
        current_key="effDatasetInheritancePath")
    EFF_QOS_INHERITANCE_PATH = _FileBasicAttrApiKey(
        current_key="effQosInheritancePath")
    AGGREGATE_QOS_STATUS = _FileBasicAttrApiKey(
        current_key="aggregateQosStatus")
    ARCHIVE_RECALL_ROOT_FILE_ID = _FileBasicAttrApiKey(
        current_key="archiveRecallRootFileId")

    @property
    def api_key(self) -> str:
        """Current api key."""
        return self.value.current_key


class XattrKey:
    """Extended attribute key."""
    def __init__(self, name: str):
        """Construct XattrKey instance."""
        self.name = name

    @property
    def api_key(self) -> str:
        """Current api key."""
        return f"xattr.{self.name}"


FileAttr = Union[BasicFileAttr, XattrKey]

_DEFAULT_API_FILE_ATTRS: Final[List[FileAttr]] = [
    BasicFileAttr.FILE_ID, BasicFileAttr.PARENT_FILE_ID, BasicFileAttr.NAME,
    BasicFileAttr.POSIX_PERMISSIONS, BasicFileAttr.ATIME, BasicFileAttr.MTIME,
    BasicFileAttr.CTIME, BasicFileAttr.TYPE, BasicFileAttr.SIZE,
    BasicFileAttr.DIRECT_SHARE_IDS, BasicFileAttr.INDEX,
    BasicFileAttr.DISPLAY_UID, BasicFileAttr.DISPLAY_GID,
    BasicFileAttr.OWNER_USER_ID, BasicFileAttr.ORIGIN_PROVIDER_ID,
    BasicFileAttr.HARDLINK_COUNT
]

FileType: TypeAlias = Literal["REG", "DIR", "SYMLNK"]
ProtectionFlag: TypeAlias = Literal["data_protection", "metadata_protection"]
InheritancePath: TypeAlias = Literal["none", "direct", "ancestor",
                                     "direct_and_ancestor"]


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
    provider: Provider, requested_attrs: Optional[List[FileAttr]]
) -> Tuple[Optional[str], Optional[Dict[str, List[str]]]]:
    """Build query string and body for HTTP request to retrieve file attributes.

    NOTE: In case not all requested attributes are supported by selected
    provider exception will be raised.
    """
    qs = None
    body = None

    if requested_attrs is not None:
        if provider.version < _PROVIDER_SUPPORTING_CURRENT_API_KEY_MIN_VERSION:
            qs = "&".join(
                f"attribute={_get_deprecated_api_attr_key(provider, attr)}"
                for attr in requested_attrs)
        else:
            body = {"attributes": [attr.api_key for attr in requested_attrs]}

    return qs, body


def sanitize_file_attrs_json(provider: Provider,
                             requested_attrs: Optional[List[FileAttr]],
                             file_attrs_json: Dict[str, Any]) -> FileAttrsJson:
    """Translate attributes api keys to current ones for older providers."""
    if not requested_attrs:
        # default api attrs
        requested_attrs = _DEFAULT_API_FILE_ATTRS

    if provider.version < _PROVIDER_SUPPORTING_CURRENT_API_KEY_MIN_VERSION:
        if requested_attrs is None:
            requested_attrs = [
                attr for attr in BasicFileAttr
                if attr.value.deprecated_key is not None
            ]

        sanitized_file_attrs_json = {
            attr.api_key:
            file_attrs_json[attr.value.deprecated_key]  # type: ignore
            for attr in requested_attrs
        }
    else:
        if requested_attrs is None:
            requested_attrs = list(BasicFileAttr)

        sanitized_file_attrs_json = {
            attr.api_key: file_attrs_json[attr.api_key]
            for attr in requested_attrs
        }

    return cast(FileAttrsJson, sanitized_file_attrs_json)


def _get_deprecated_api_attr_key(provider: Provider, attr: FileAttr) -> str:
    if isinstance(attr,
                  BasicFileAttr) and attr.value.deprecated_key is not None:
        return attr.value.deprecated_key
    else:
        raise OnedataRESTError(
            http_code=400,
            error_category="posix",
            error_details=_NOT_SUPPORTED_ATTR_ERROR_DETAILS_FMT.format(
                domain=provider.domain, version=provider.version, attr=attr),
            description="einval")
