"""Authors: Bartek Kryza
Copyright (C) 2021 onedata.org
This software is released under the MIT license cited in 'LICENSE.txt'
"""
import logging
import os
import time
import uuid

import pytest
import requests
from urllib3.util import connection


def trace_requests_messages() -> None:
    """Enable logging HTTP requests."""
    import http.client as http_client
    http_client.HTTPConnection.debuglevel = 1

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True


# Uncomment to enable HTTP request trace log
# trace_requests_messages()

FIXTURE_SCOPE = "session"

_original_create_connection = connection.create_connection


def patched_create_connection(address, *args, **kwargs):
    """Resolve Kubernetes domain names to IP's from environment variables"""
    host, port = address
    hostname = host

    if host == 'dev-onezone-0.default.svc.cluster.local':
        hostname = os.getenv('DEV_ONEZONE_0')
    elif host == 'dev-oneprovider-krakow.default.svc.cluster.local':
        hostname = os.getenv('DEV_ONEPROVIDER_KRAKOW_0')
    elif host == 'dev-oneprovider-paris.default.svc.cluster.local':
        hostname = os.getenv('DEV_ONEPROVIDER_PARIS_0')

    return _original_create_connection((hostname, port), *args, **kwargs)


connection.create_connection = patched_create_connection


@pytest.fixture(scope="module", autouse=True)
def wait_for_support_sync():
    """Wait until providers are fully synchronized after setup"""
    time.sleep(10)


@pytest.fixture(scope=FIXTURE_SCOPE)
def git_version():
    gv = os.getenv('GIT_VERSION')
    yield gv


@pytest.fixture
def uuid_str():
    return str(uuid.uuid4())


@pytest.fixture(scope=FIXTURE_SCOPE)
def onezone_ip():
    ozip = os.getenv('DEV_ONEZONE_0')
    yield ozip


@pytest.fixture(scope=FIXTURE_SCOPE)
def oneprovider_krakow_ip():
    opip = os.getenv('DEV_ONEPROVIDER_KRAKOW_0')
    yield opip


@pytest.fixture(scope=FIXTURE_SCOPE)
def oneprovider_paris_ip():
    opip = os.getenv('DEV_ONEPROVIDER_PARIS_0')
    yield opip


@pytest.fixture(scope=FIXTURE_SCOPE)
def onezone_admin_token(onezone_ip):
    tokens_endpoint = f'https://{onezone_ip}/api/v3/onezone/user/client_tokens'
    res = requests.post(tokens_endpoint, {},
                        auth=requests.auth.HTTPBasicAuth('admin', 'password'),
                        verify=False)
    return res.json()["token"]


@pytest.fixture(scope=FIXTURE_SCOPE)
def onezone_readonly_token(onezone_ip):
    tokens_endpoint = f'https://{onezone_ip}/api/v3/onezone/user/tokens/temporary'
    headers = {'content-type': 'application/json'}
    res = requests.post(tokens_endpoint,
                        json={
                            "type": {
                                "accessToken": {}
                            },
                            "caveats": [{
                                "type": "data.readonly"
                            }, {
                                "type": "time",
                                "validUntil": int(time.time()) + 2592000
                            }]
                        },
                        headers=headers,
                        auth=requests.auth.HTTPBasicAuth('admin', 'password'),
                        verify=False)
    return res.json()["token"]
