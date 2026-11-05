"""Onedata REST file API type aliases module."""

from typing import Tuple, TypeAlias, Union

Json: TypeAlias = dict[str, "Json"] | list["Json"] | str | int | float | bool | None

HTTPTimeout: TypeAlias = Union[int, Tuple[int, int]]

FileId: TypeAlias = str
FilePath: TypeAlias = str
"""
File path relative to space, that is without space specifier prefix.
"""

ProviderId: TypeAlias = str

SpaceId: TypeAlias = str
SpaceName: TypeAlias = str

# pylint: disable=invalid-name

SpaceCanonicalFQN: TypeAlias = str
"""
Fully qualified space name in the form: <SpaceName>@<SpaceId>
"""

SpaceFQN: TypeAlias = str
"""
Fully qualified space name in the form: <SpaceName><Separator><SpaceId>
By default, the canonical separator "@" is accepted, but alternative
ones can be provided in the 'alt_space_fqn_separators' option.
"""

# pylint: enable=invalid-name

SpaceSpecifier: TypeAlias = Union[SpaceName, SpaceFQN]


ProviderDomain: TypeAlias = str
ProviderSpecifier: TypeAlias = Union[ProviderId, ProviderDomain]
