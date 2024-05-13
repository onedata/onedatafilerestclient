# coding: utf-8
"""Provider selector utilities."""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2024 ACK CYFRONET AGH"
__license__ = (
    "This software is released under the MIT license cited in LICENSE.txt")

import time
from typing import Dict, Iterator, List, NamedTuple, Optional

from packaging.version import Version, parse  # type: ignore

from .onezone_rest_client import OnezoneRESTClient, ProviderId, SpaceSpecifier


class Provider(NamedTuple):
    """Provider relevant attributes."""
    id: str
    version: Version
    domain: str


class ProviderSelector:
    """Selector responsible for choosing available provider(s) for space."""

    preferred_provider_domains: List[str]
    _provider_blacklist: Dict[ProviderId, int]
    _provider_for_space: Dict[SpaceSpecifier, Provider]

    _cache_size_limit: int = 512
    _blacklist_time_limit_ns: int = 5 * 10**9

    def __init__(
            self,
            *,
            preferred_provider_domains: Optional[List[str]] = None) -> None:
        """Construct ProviderSelector instance."""
        self.preferred_provider_domains = preferred_provider_domains or []
        self._provider_blacklist = {}
        self._provider_for_space = {}

    def is_blacklisted(self, provider_id: ProviderId) -> bool:
        """Blacklist specified provider for a short while."""
        if provider_id not in self._provider_blacklist:
            return False

        blacklist_time_end = self._provider_blacklist[provider_id]
        if blacklist_time_end > time.time_ns():
            return True
        else:
            del self._provider_blacklist[provider_id]
            return False

    def blacklist(self, provider_id: ProviderId) -> None:
        """Check if specified provider is blacklisted."""
        blacklist_time_end = time.time_ns() + self._blacklist_time_limit_ns

        if len(self._provider_blacklist) > self._cache_size_limit:
            self._provider_blacklist = {provider_id: blacklist_time_end}
        else:
            self._provider_blacklist[provider_id] = blacklist_time_end

    def iter_available_space_providers(
            self, space_specifier: SpaceSpecifier, *,
            oz_rest_client: OnezoneRESTClient) -> Iterator[Provider]:
        """Iterate over online and not not blacklisted space providers."""
        if space_specifier in self._provider_for_space:
            provider = self._provider_for_space[space_specifier]
            if not self.is_blacklisted(provider.id):
                yield self._provider_for_space[space_specifier]

            del self._provider_for_space[space_specifier]

        if len(self._provider_for_space) >= self._cache_size_limit:
            # clear cache
            self._provider_for_space = {}

        for provider in self.list_available_space_providers(
                space_specifier, oz_rest_client=oz_rest_client):
            self._provider_for_space[space_specifier] = provider
            yield provider

    def list_available_space_providers(
            self, space_specifier: SpaceSpecifier, *,
            oz_rest_client: OnezoneRESTClient) -> List[Provider]:
        """List online and not not blacklisted space providers."""
        access_token_scope = oz_rest_client.infer_token_scope()

        all_providers = access_token_scope["dataAccessScope"]["providers"]

        space_id = oz_rest_client.get_space_id(
            space_specifier, access_token_scope=access_token_scope)
        space_details = access_token_scope["dataAccessScope"]["spaces"][
            space_id]

        preferred_supporting_providers = []
        remaining_supporting_providers = []

        for provider_id in space_details["supports"]:
            if self.is_blacklisted(provider_id):
                continue

            provider_details = all_providers[provider_id]
            if not provider_details["online"]:
                continue

            provider = Provider(id=provider_id,
                                version=parse(provider_details["version"]),
                                domain=provider_details["domain"])

            try:
                index = self.preferred_provider_domains.index(provider.domain)
                preferred_supporting_providers.append((index, provider))
            except ValueError:
                remaining_supporting_providers.append(provider)

        preferred_supporting_providers.sort()
        supporting_providers = [
            provider for _, provider in preferred_supporting_providers
        ]

        remaining_supporting_providers.sort(key=lambda x: x.version,
                                            reverse=True)
        supporting_providers.extend(remaining_supporting_providers)

        return supporting_providers
