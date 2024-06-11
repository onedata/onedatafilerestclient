# coding: utf-8
"""Pytest test setup."""

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import logging
import os
import time
from typing import Final

import requests
from urllib3.util import connection

import pytest

from . import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    PROVIDER_KRK_DOMAIN,
    PROVIDER_PAR_DOMAIN,
    SPACE_MEMBER_PASSWORD,
    SPACE_MEMBER_USERNAME,
    ZONE_DOMAIN,
)


def trace_requests_messages() -> None:
    """Enable logging HTTP requests."""
    # pylint: disable=C0415
    import http.client as http_client

    http_client.HTTPConnection.debuglevel = 1

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True


# Uncomment to enable HTTP request trace log
# trace_requests_messages()


_original_create_connection = connection.create_connection


def patched_create_connection(address, *args, **kwargs):
    """Resolve Kubernetes domain names to IP's from environment variables."""
    host, port = address
    hostname = host

    if host == ZONE_DOMAIN:
        hostname = os.getenv("DEV_ONEZONE_0")
    elif host == PROVIDER_KRK_DOMAIN:
        hostname = os.getenv("DEV_ONEPROVIDER_KRAKOW_0")
    elif host == PROVIDER_PAR_DOMAIN:
        hostname = os.getenv("DEV_ONEPROVIDER_PARIS_0")

    return _original_create_connection((hostname, port), *args, **kwargs)


connection.create_connection = patched_create_connection


FIXTURE_SCOPE: Final[str] = "session"


@pytest.fixture(scope="module", autouse=True)
def fixture_wait_for_support_sync():
    """Wait until providers are fully synchronized after setup."""
    time.sleep(10)


@pytest.fixture(scope=FIXTURE_SCOPE, name="onezone_ip")
def fixture_onezone_ip():
    """Get Onezone IP from environment variable."""
    return os.getenv("DEV_ONEZONE_0")


@pytest.fixture(scope=FIXTURE_SCOPE, name="provider_krk_ip")
def fixture_provider_krk_ip():
    """Get Oneprovider 'krakow' IP from environment variable."""
    return os.getenv("DEV_ONEPROVIDER_KRAKOW_0")


@pytest.fixture(scope=FIXTURE_SCOPE, name="provider_par_ip")
def fixture_provider_par_ip():
    """Get Oneprovider 'paris' IP from environment variable."""
    return os.getenv("DEV_ONEPROVIDER_PARIS_0")


@pytest.fixture(scope=FIXTURE_SCOPE, name="onezone_admin_token")
def fixture_onezone_admin_token(onezone_ip):
    """Generate a new admin token."""
    return _create_temp_token(onezone_ip, ADMIN_USERNAME, ADMIN_PASSWORD)


@pytest.fixture(scope=FIXTURE_SCOPE, name="onezone_readonly_token")
def fixture_onezone_readonly_token(onezone_ip):
    """Generate new readonly only admin token."""
    return _create_temp_token(onezone_ip, ADMIN_USERNAME, ADMIN_PASSWORD, readonly=True)


@pytest.fixture(scope=FIXTURE_SCOPE, name="onezone_space_member_token")
def fixture_space_member_token(onezone_ip):
    """Generate a new space member token."""
    return _create_temp_token(onezone_ip, SPACE_MEMBER_USERNAME, SPACE_MEMBER_PASSWORD)


def _create_temp_token(
    onezone_ip: str, username: str, password: str, *, readonly: bool = False
) -> str:
    url = f"https://{onezone_ip}/api/v3/onezone/user/tokens/temporary"
    headers = {"content-type": "application/json"}
    auth = requests.auth.HTTPBasicAuth(username, password)

    caveats = [{"type": "time", "validUntil": int(time.time()) + 2590000}]
    if readonly:
        caveats.append({"type": "data.readonly"})

    result = requests.post(
        url,
        json={
            "type": {"accessToken": {}},
            "caveats": caveats,
        },
        headers=headers,
        auth=auth,
        verify=False,
    )
    return result.json()["token"]
