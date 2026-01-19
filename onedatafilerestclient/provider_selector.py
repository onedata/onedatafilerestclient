# coding: utf-8
"""Provider selector utilities.

Key behaviour:
- Available provider: provider that is online, meets min version and not readonly
  in case of modifying operations (see `_is_provider_available`).
- Graylisted provider: a provider that is still “available” but recently failed
  (e.g. timeout/connection error). It gets lower priority (for a short graylisting
  period), when choosing provider for operation, than other available providers.
- Selection order: active providers are sorted (preferred first, then by version
  descending); graylisted providers are sorted the same way and appended as
  fallback when no active providers are suitable.
- Cache: the last selected provider per space is cached; the entry is dropped if
  the provider becomes graylisted or expires.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2024 ACK CYFRONET AGH"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import logging
import sys
import time
from datetime import datetime
from typing import Dict, Final, Iterator, List, NamedTuple, Optional, Tuple, Union

from packaging.version import Version, parse

from .onezone_rest_client import (
    OnezoneRESTClient,
    ProviderDetails,
    ProviderId,
    SpaceId,
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
    _provider_graylist_cache: Dict[Tuple[ProviderId, SpaceId], int]
    _graylist_time_limit_ns: int = 30 * 10**9  # 30 seconds

    def __init__(
        self, *, preferred_providers: Optional[List[ProviderSpecifier]] = None
    ) -> None:
        """Construct ProviderSelector instance."""
        self.preferred_providers = preferred_providers or []
        self._provider_graylist_cache = {}
        self._provider_for_space_cache = {}

    def is_graylisted(self, provider_id: ProviderId, space_id: SpaceId) -> bool:
        """Check if specified provider is graylisted for given space."""
        key = (provider_id, space_id)
        if key not in self._provider_graylist_cache:
            return False

        graylist_time_end = self._provider_graylist_cache[key]
        if graylist_time_end > time.time_ns():
            return True

        del self._provider_graylist_cache[key]
        return False

    def graylist(self, provider: SpaceSupportingProvider, space_id: SpaceId) -> None:
        """Graylist specified provider for a short while for given space."""
        graylist_time_end_ns = time.time_ns() + self._graylist_time_limit_ns
        key = (provider.id, space_id)

        _logger.debug(
            "Graylisting provider '%s' (id: %s) for space '%s' until %s",
            provider.domain,
            provider.id,
            space_id,
            datetime.fromtimestamp(graylist_time_end_ns // 1e9),
        )

        if len(self._provider_graylist_cache) > self._cache_size_limit:
            self._provider_graylist_cache = {key: graylist_time_end_ns}
        else:
            self._provider_graylist_cache[key] = graylist_time_end_ns

    def iter_available_space_providers(
        self,
        space_specifier: SpaceSpecifier,
        *,
        oz_rest_client: OnezoneRESTClient,
        except_readonly: bool = False,
    ) -> Iterator[SpaceSupportingProvider]:
        """Iterate over available space providers (with graylist fallback)."""
        space_canonical_fqn = oz_rest_client.ensure_space_canonical_fqn(space_specifier)
        space_id = oz_rest_client.get_space_id(space_specifier)

        cache_key = space_canonical_fqn
        yield from self._fetch_provider_from_cache(
            cache_key, space_id, except_readonly=except_readonly
        )

        if except_readonly:
            cache_key = f"{space_canonical_fqn}#not_readonly"
            yield from self._fetch_provider_from_cache(
                cache_key, space_id, except_readonly=except_readonly
            )

        if len(self._provider_for_space_cache) >= self._cache_size_limit:
            # clear cache
            self._provider_for_space_cache = {}

        for provider in self.list_available_space_providers(
            space_canonical_fqn,
            oz_rest_client=oz_rest_client,
            except_readonly=except_readonly,
        ):
            if self.is_graylisted(provider.id, space_id):
                msg = (
                    "Using graylisted provider '%s' (id: %s) for space '%s' as fallback"
                )
            else:
                msg = "Designating active provider '%s' (id: %s) to handle requests for space '%s'"

            _logger.debug(
                msg,
                provider.id,
                space_canonical_fqn,
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
        """List providers, appending graylisted ones as a fallback."""
        space_id = oz_rest_client.get_space_id(space_specifier)

        access_token_scope = oz_rest_client.infer_token_scope()
        all_providers = access_token_scope["dataAccessScope"]["providers"]
        space_details = access_token_scope["dataAccessScope"]["spaces"][space_id]

        active_providers = []
        graylisted_providers = []

        for provider_id, support_attributes in space_details["supports"].items():
            provider = self._build_space_supporting_provider(
                provider_id, support_attributes, all_providers[provider_id]
            )
            if not self._is_provider_available(provider, except_readonly):
                continue

            if self.is_graylisted(provider.id, space_id):
                graylisted_providers.append(provider)
            else:
                active_providers.append(provider)

        sorted_active_providers = self._sort_providers(active_providers)
        sorted_graylisted_providers = self._sort_providers(graylisted_providers)

        sorted_active_providers.extend(sorted_graylisted_providers)
        return sorted_active_providers

    def _sort_providers(
        self, providers: List[SpaceSupportingProvider]
    ) -> List[SpaceSupportingProvider]:
        preferred_providers = []
        remaining_providers = []

        for provider in providers:
            try:
                index = next(
                    i
                    for i, provider_specifier in enumerate(self.preferred_providers)
                    if provider_specifier in (provider.id, provider.domain)
                )
            except StopIteration:
                remaining_providers.append(provider)
            else:
                preferred_providers.append((index, provider))

        preferred_providers.sort()
        result = [provider for _, provider in preferred_providers]

        remaining_providers.sort(key=lambda x: x.version, reverse=True)
        result.extend(remaining_providers)

        return result

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
        if except_readonly and provider.readonly_support:
            return False

        if not provider.online:
            return False

        if provider.version < _MIN_SUPPORTED_PROVIDER_VERSION:
            return False

        return True

    def _fetch_provider_from_cache(
        self, cache_key: str, space_id: SpaceId, except_readonly: bool
    ) -> Iterator[SpaceSupportingProvider]:
        provider = self._provider_for_space_cache.get(cache_key)
        if provider is not None:
            if (not except_readonly) or (
                except_readonly and not provider.readonly_support
            ):
                if not self.is_graylisted(provider.id, space_id):
                    yield provider

                del self._provider_for_space_cache[cache_key]
