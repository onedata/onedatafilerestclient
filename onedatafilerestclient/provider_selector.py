# coding: utf-8
"""Provider selector utilities."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2024 ACK CYFRONET AGH"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import logging
import sys
import time
from datetime import datetime
from typing import Dict, Final, Iterator, List, NamedTuple, Optional, Union

from packaging.version import Version, parse

from .onezone_rest_client import (
    OnezoneRESTClient,
    ProviderDetails,
    ProviderId,
    SpaceSpecifier,
    SpaceSupportAttributes,
)

if sys.version_info < (3, 11):
    from typing_extensions import TypeAlias
else:
    from typing import TypeAlias


_logger = logging.getLogger(__name__)
_logger.addHandler(logging.NullHandler())

_MIN_SUPPORTED_PROVIDER_VERSION: Final[Version] = Version("21.2.1")

ProviderDomain: TypeAlias = str
ProviderSpecifier: TypeAlias = Union[ProviderId, ProviderDomain]


class SpaceSupportingProvider(NamedTuple):
    """Provider relevant attributes."""

    id: str
    version: Version
    domain: str
    online: bool
    readonly_support: bool


class ProviderSelector:
    """Selector responsible for choosing available provider(s) for space."""

    preferred_providers: List[str]

    _cache_size_limit: int = 512
    _provider_for_space_cache: Dict[SpaceSpecifier, SpaceSupportingProvider]
    _provider_blacklist_cache: Dict[ProviderId, int]
    _blacklist_time_limit_ns: int = 30 * 10**9  # 30 seconds

    def __init__(
        self, *, preferred_providers: Optional[List[ProviderSpecifier]] = None
    ) -> None:
        """Construct ProviderSelector instance."""
        self.preferred_providers = preferred_providers or []
        self._provider_blacklist_cache = {}
        self._provider_for_space_cache = {}

    def is_blacklisted(self, provider_id: ProviderId) -> bool:
        """Blacklist specified provider for a short while."""
        if provider_id not in self._provider_blacklist_cache:
            return False

        blacklist_time_end = self._provider_blacklist_cache[provider_id]
        if blacklist_time_end > time.time_ns():
            return True

        del self._provider_blacklist_cache[provider_id]
        return False

    def blacklist(self, provider: SpaceSupportingProvider) -> None:
        """Check if specified provider is blacklisted."""
        blacklist_time_end_ns = time.time_ns() + self._blacklist_time_limit_ns

        _logger.debug(
            "Blacklisting provider '%s' (id: %s) until %s",
            provider.domain,
            provider.id,
            datetime.fromtimestamp(blacklist_time_end_ns // 1e9),
        )

        if len(self._provider_blacklist_cache) > self._cache_size_limit:
            self._provider_blacklist_cache = {provider.id: blacklist_time_end_ns}
        else:
            self._provider_blacklist_cache[provider.id] = blacklist_time_end_ns

    def iter_available_space_providers(
        self,
        space_specifier: SpaceSpecifier,
        *,
        oz_rest_client: OnezoneRESTClient,
        except_readonly: bool = False,
    ) -> Iterator[SpaceSupportingProvider]:
        """Iterate over online and not blacklisted space providers."""
        space_fqn = oz_rest_client.ensure_space_fqn(space_specifier)

        cache_key = space_fqn
        yield from self._fetch_provider_from_cache(cache_key, except_readonly)

        if except_readonly:
            cache_key = f"{space_fqn}#not_readonly"
            yield from self._fetch_provider_from_cache(cache_key, except_readonly)

        if len(self._provider_for_space_cache) >= self._cache_size_limit:
            # clear cache
            self._provider_for_space_cache = {}

        for provider in self.list_available_space_providers(
            space_fqn,
            oz_rest_client=oz_rest_client,
            except_readonly=except_readonly,
        ):
            _logger.debug(
                "Designating provider '%s' (id: %s) to handle requests for space '%s'",
                provider.domain,
                provider.id,
                space_fqn,
            )
            self._provider_for_space_cache[cache_key] = provider
            yield provider

    def list_available_space_providers(
        self,
        space_specifier: SpaceSpecifier,
        *,
        oz_rest_client: OnezoneRESTClient,
        except_readonly: bool = False,
    ) -> List[SpaceSupportingProvider]:
        """List online and not not blacklisted space providers."""
        space_id = oz_rest_client.get_space_id(space_specifier)

        access_token_scope = oz_rest_client.infer_token_scope()
        all_providers = access_token_scope["dataAccessScope"]["providers"]
        space_details = access_token_scope["dataAccessScope"]["spaces"][space_id]

        preferred_supporting_providers = []
        remaining_supporting_providers = []

        for provider_id, support_attributes in space_details["supports"].items():
            provider = self._build_space_supporting_provider(
                provider_id, support_attributes, all_providers[provider_id]
            )
            if not self._is_provider_available(provider, except_readonly):
                continue

            try:
                index = next(
                    i
                    for i, provider_specifier in enumerate(self.preferred_providers)
                    if provider_specifier in (provider.id, provider.domain)
                )
            except StopIteration:
                remaining_supporting_providers.append(provider)
            else:
                preferred_supporting_providers.append((index, provider))

        preferred_supporting_providers.sort()
        supporting_providers = [
            provider for _, provider in preferred_supporting_providers
        ]

        remaining_supporting_providers.sort(key=lambda x: x.version, reverse=True)
        supporting_providers.extend(remaining_supporting_providers)

        return supporting_providers

    @staticmethod
    def _build_space_supporting_provider(
        provider_id: ProviderId,
        support_attributes: SpaceSupportAttributes,
        provider_details: ProviderDetails,
    ) -> SpaceSupportingProvider:
        provider = SpaceSupportingProvider(
            id=provider_id,
            version=parse(provider_details["version"]),
            domain=provider_details["domain"],
            online=provider_details["online"],
            readonly_support=support_attributes["readonly"],
        )
        return provider

    def _is_provider_available(
        self, provider: SpaceSupportingProvider, except_readonly: bool
    ) -> bool:
        if self.is_blacklisted(provider.id):
            return False

        if except_readonly and provider.readonly_support:
            return False

        if not provider.online:
            return False

        if provider.version < _MIN_SUPPORTED_PROVIDER_VERSION:
            return False

        return True

    def _fetch_provider_from_cache(
        self, cache_key: str, except_readonly: bool
    ) -> Iterator[SpaceSupportingProvider]:
        provider = self._provider_for_space_cache.get(cache_key)
        if provider is not None:
            if (not except_readonly) or (
                except_readonly and not provider.readonly_support
            ):
                if not self.is_blacklisted(provider.id):
                    yield provider

                del self._provider_for_space_cache[cache_key]
