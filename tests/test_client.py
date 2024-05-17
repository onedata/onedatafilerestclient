# coding: utf-8
"""Test OnedataFileRESTClient methods."""

import os
import random
import time
from contextlib import contextmanager
from typing import get_args

import requests
from packaging.version import Version  # type: ignore

import pytest
from onedatafilerestclient import OnedataFileRESTClient, OnedataRESTError
from onedatafilerestclient.errors import (
    NoAvailableProviderForSpaceError,
    SpaceNotFoundError,
)
from onedatafilerestclient.file_attributes import (
    _DEPRECATED_BASIC_FILE_ATTR_KEYS,
    BasicFileAttrKey,
)

from . import (
    PROVIDER_KRK_DOMAIN,
    PROVIDER_PAR_DOMAIN,
    SPACE_KRK_PAR_NAME,
    SPACE_PAR_NAME,
)
from .utils import random_bytes, random_int, random_path, random_str


@pytest.fixture(name="client_verifying_ssl")
def fixture_client_verifying_ssl(onezone_ip, onezone_admin_token):
    """Create OnedataFileRESTClient instance."""
    return OnedataFileRESTClient(onezone_ip, onezone_admin_token, verify_ssl=True)


@pytest.fixture(name="client")
def fixture_client(onezone_ip, onezone_admin_token):
    """Create OnedataFileRESTClient instance."""
    return OnedataFileRESTClient(onezone_ip, onezone_admin_token, verify_ssl=False)


@pytest.fixture(name="client_ro")
def fixture_client_ro(onezone_ip, onezone_readonly_token):
    """Create readonly OnedataFileRESTClient instance."""
    return OnedataFileRESTClient(onezone_ip, onezone_readonly_token, verify_ssl=False)


@pytest.fixture(name="client_krakow")
def fixture_client_krakow(onezone_ip, onezone_admin_token):
    """Create OnedataFileRESTClient instance bound to 'krakow' provider."""
    return OnedataFileRESTClient(
        onezone_ip, onezone_admin_token, [PROVIDER_KRK_DOMAIN], verify_ssl=False
    )


@pytest.fixture(name="client_ro_krakow")
def fixture_client_ro_krakow(onezone_ip, onezone_readonly_token):
    """Create readonly OnedataFileRESTClient instance bound to 'krakow'."""
    return OnedataFileRESTClient(
        onezone_ip, onezone_readonly_token, [PROVIDER_KRK_DOMAIN], verify_ssl=False
    )


@pytest.fixture(name="client_paris")
def fixture_client_paris(onezone_ip, onezone_admin_token):
    """Create OnedataFileRESTClient instance bound to 'krakow' provider."""
    return OnedataFileRESTClient(
        onezone_ip, onezone_admin_token, [PROVIDER_PAR_DOMAIN], verify_ssl=False
    )


def test_ssl_verification(client_verifying_ssl: OnedataFileRESTClient):
    """Test 'OnedataFileRESTClient' respects 'verify_ssl' flag."""
    with pytest.raises(requests.exceptions.SSLError):
        assert client_verifying_ssl.list_spaces()


def test_list_spaces(client: OnedataFileRESTClient):
    """Test 'list_spaces' method."""
    exp_spaces = sorted(
        [
            _get_space_fqn(SPACE_KRK_PAR_NAME, client),
            _get_space_fqn(SPACE_PAR_NAME, client),
        ]
    )

    assert exp_spaces == sorted(client.list_spaces())


def test_get_space_id(onezone_ip, onezone_admin_token):
    """Test 'get_space_id' method."""
    client = OnedataFileRESTClient(
        onezone_ip, onezone_admin_token, [PROVIDER_KRK_DOMAIN], verify_ssl=False
    )
    client._oz_client._space_id_cache_size_limit = 2  # pylint: disable=W0212

    space_krk_id = client.get_space_id(SPACE_KRK_PAR_NAME)

    # space_fqn resolution should not be cached
    space_krk_fqn = f"{SPACE_KRK_PAR_NAME}@{space_krk_id}"
    assert client.get_space_id(space_krk_fqn) == space_krk_id


def test_provider_selector(onezone_ip, onezone_admin_token):
    """Test provider fallback on connection error."""
    providers = [PROVIDER_KRK_DOMAIN, PROVIDER_PAR_DOMAIN]
    random.shuffle(providers)
    first_choice_provider, second_choice_provider = providers

    client = OnedataFileRESTClient(
        onezone_ip,
        onezone_admin_token,
        [_random_provider_specifier(first_choice_provider)],
        verify_ssl=False,
    )

    # pylint: disable=W0212
    client._provider_selector._blacklist_time_limit_ns = 1 * 10**9

    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    def get_selected_provider_domain():
        # pylint: disable=W0212
        provider = client._select_provider_for_space(space_specifier)
        return provider.domain

    # provider 'first_choice_provider' is chosen with accordance to
    # preferred providers
    client.get_attributes(space_specifier)
    assert get_selected_provider_domain() == first_choice_provider

    # with connection error raised 'first_choice_provider' should be
    # blacklisted for a while and next in line provider
    # - second_choice_provider - should be selected
    with _mock_http_client_get([first_choice_provider]):
        client.get_attributes(space_specifier)
        assert get_selected_provider_domain() == second_choice_provider

    client.get_attributes(space_specifier)
    assert get_selected_provider_domain() == second_choice_provider

    # with connection error raised by 'second_choice_provider' there should
    # be no available providers left
    with _mock_http_client_get([second_choice_provider]):
        with pytest.raises(NoAvailableProviderForSpaceError) as exc_info:
            client.get_attributes(space_specifier)

        assert exc_info.value.args == (space_specifier,)

    # even without mock providers should still be blacklisted
    with pytest.raises(NoAvailableProviderForSpaceError) as exc_info:
        client.get_attributes(space_specifier)

    assert exc_info.value.args == (space_specifier,)

    # but after blacklist time ends 'first_choice_provider' should be
    # again selected
    time.sleep(2)
    client.get_attributes(space_specifier)
    assert get_selected_provider_domain() == first_choice_provider


def test_get_file_id(client: OnedataFileRESTClient):
    """Test 'get_file_id' method."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    file_path = random_path()
    file_id = client.create_file(space_specifier, file_path, create_parents=True)

    assert file_id == client.get_file_id(space_specifier, file_path)


def test_get_attributes_for_space_dir(client: OnedataFileRESTClient):
    """Test 'get_attributes' method for space directory."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)
    space_attrs = client.get_attributes(space_specifier)

    assert SPACE_KRK_PAR_NAME == space_attrs["name"]


def test_get_attributes_for_file(client: OnedataFileRESTClient):
    """Test 'get_attributes' method for regular file."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    file_path = random_path()
    file_name = file_path.rsplit("/", maxsplit=1)[-1]
    file_id = client.create_file(space_specifier, file_path, create_parents=True)
    file_selector = _random_file_selector(file_id, file_path)

    file_attrs = client.get_attributes(space_specifier, **file_selector)

    assert file_name == file_attrs["name"]
    assert file_id == file_attrs["fileId"]


def test_get_selected_attributes(client: OnedataFileRESTClient):
    """Test 'get_attributes' method with random attributes."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    # Set min version to lower that testing providers to allow all new attrs
    with _mock_min_provider_version_supporting_new_file_attrs(Version("20.1.1")):

        requested_attr_keys = random.sample(get_args(BasicFileAttrKey), 5)
        space_attrs = client.get_attributes(
            space_specifier, attributes=requested_attr_keys
        )
        assert sorted(requested_attr_keys) == sorted(space_attrs.keys())

    # Set min version to higher that testing providers to disallow new attrs
    with _mock_min_provider_version_supporting_new_file_attrs(Version("30.1.1")):

        requested_attr_keys = random.sample(_DEPRECATED_BASIC_FILE_ATTR_KEYS.keys(), 5)
        requested_attr_keys.append("acl")

        with pytest.raises(OnedataRESTError) as exc_info:
            client.get_attributes(space_specifier, attributes=requested_attr_keys)

            error = exc_info.value
            assert error.http_code == 400
            assert error.error_category == "posix"
            assert error.error_details == (
                "The provider chosen for this space ({domain}) is in version "
                "({24.02.1}) that does not support the 'BaseFileAttr.ACL' "
                "attribute (requires Oneprovider version >= 30.1.1)"
            )
            assert error.description == "einval"

        space_attrs = client.get_attributes(
            space_specifier, attributes=requested_attr_keys[:-1]
        )
        exp_attrs = sorted(requested_attr_keys[:-1])
        assert exp_attrs == sorted(space_attrs.keys())


def test_set_attributes(client: OnedataFileRESTClient):
    """Test 'set_attributes' method."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    file_path = random_path()
    file_id = client.create_file(
        space_specifier, file_path, mode=0o775, create_parents=True
    )
    file_selector = _random_file_selector(file_id, file_path)

    file_attrs = client.get_attributes(space_specifier, **file_selector)
    assert file_attrs["posixPermissions"] == "775"

    client.set_attributes(space_specifier, {"mode": "553"}, **file_selector)
    file_attrs = client.get_attributes(space_specifier, **file_selector)

    assert file_attrs["posixPermissions"] == "553"


def test_list_children(client: OnedataFileRESTClient):
    """Test 'list_children' method."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    file_count = random_int(20, 50)
    dir_path = random_path()

    exp_children = []
    for _ in range(file_count):
        file_name = random_str(random_int(lower_bound=10))
        file_path = os.path.join(dir_path, file_name)
        client.create_file(space_specifier, file_path, create_parents=True)

        exp_children.append(
            {
                "name": file_name,
                "type": "REG",
            }
        )

    token = None
    limit = random_int(4, 10)
    dir_id = client.get_file_id(space_specifier, dir_path)
    dir_selector = _random_file_selector(dir_id, dir_path)

    children = []
    while True:
        result = client.list_children(
            space_specifier, limit=limit, continuation_token=token, **dir_selector
        )
        children.extend(result["children"])
        if result["isLast"]:
            break

        token = result["nextPageToken"]

    def sort_files(files):
        return sorted(files, key=lambda d: d["name"])

    assert sort_files(children) == sort_files(exp_children)


def test_get_file_content(client_krakow: OnedataFileRESTClient):
    """Test 'get_file_content' method."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client_krakow)

    file_path = random_path()
    file_id = client_krakow.create_file(space_specifier, file_path, create_parents=True)
    file_selector = _random_file_selector(file_id, file_path)

    file_size = 1024
    exp_file_content = random_bytes(file_size)
    client_krakow.put_file_content(space_specifier, exp_file_content, **file_selector)

    assert exp_file_content == client_krakow.get_file_content(
        space_specifier, **file_selector
    )

    assert exp_file_content[100:300] == client_krakow.get_file_content(
        space_specifier, offset=100, size=200, **file_selector
    )


def test_get_file_content_with_readonly_token_on_the_same_provider(
    client_krakow: OnedataFileRESTClient, client_ro_krakow: OnedataFileRESTClient
):
    """Test 'get_file_content' method using readonly token."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client_krakow)

    file_path = random_path()
    file_id = client_krakow.create_file(space_specifier, file_path, create_parents=True)
    file_selector = _random_file_selector(file_id, file_path)

    file_content = random_bytes(1024)
    client_krakow.put_file_content(space_specifier, file_content, **file_selector)

    assert (
        client_ro_krakow.get_file_content(space_specifier, **file_selector)
        == file_content
    )


def test_enoent_space(client: OnedataFileRESTClient):
    """Test 'get_file_content' on non-existing space."""
    with pytest.raises(SpaceNotFoundError) as exc_info:
        client.get_file_content("NO_SUCH_SPACE", file_path=random_path())

    assert exc_info.value.args == ("NO_SUCH_SPACE",)


def test_enoent_file(client: OnedataFileRESTClient):
    """Test 'get_file_content' on non-existing file."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)
    file_path = random_path()

    with pytest.raises(OnedataRESTError) as exc_info:
        client.get_file_content(space_specifier, file_path=file_path)

    e = exc_info.value
    assert e.http_code == 400
    assert e.category == "posix"
    assert e.description == "Operation failed with POSIX error: enoent."
    assert e.details == {"errno": "enoent"}


def test_iter_file_content(client_krakow: OnedataFileRESTClient):
    """Test 'iter_file_content' method."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client_krakow)

    file_path = random_path()
    file_id = client_krakow.create_file(space_specifier, file_path, create_parents=True)
    file_selector = _random_file_selector(file_id, file_path)

    file_content = random_bytes(1024)
    client_krakow.put_file_content(space_specifier, file_content, **file_selector)

    chunk_size = random_int(4, 100)
    stream = client_krakow.iter_file_content(
        space_specifier, chunk_size, **file_selector
    )

    buff = b""
    for chunk in stream:
        assert len(chunk) <= chunk_size
        buff += chunk

    assert buff == file_content


def test_put_file_content(client: OnedataFileRESTClient):
    """Test 'put_file_content' method."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    file_path = random_path()
    file_id = client.create_file(space_specifier, file_path, create_parents=True)
    file_selector = _random_file_selector(file_id, file_path)

    file_size = 100
    rand_bytes = random_bytes(file_size)
    client.put_file_content(space_specifier, rand_bytes, offset=100, **file_selector)
    exp_file_content = 100 * b"\0" + rand_bytes

    assert exp_file_content == client.get_file_content(space_specifier, **file_selector)


def test_create_file(client: OnedataFileRESTClient):
    """Test 'create_file' method."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    file_path = random_path()
    file_id = client.create_file(
        space_specifier, file_path, file_type="REG", create_parents=True
    )
    file_selector = _random_file_selector(file_id, file_path)

    file_content = random_bytes(1024)
    client.put_file_content(space_specifier, file_content, **file_selector)

    content = client.get_file_content(space_specifier, **file_selector)

    assert content == file_content


def test_remove(client: OnedataFileRESTClient):
    """Test 'remove' method."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    dir_path = random_path()
    file_path = os.path.join(dir_path, random_str())
    file_id = client.create_file(space_specifier, file_path, create_parents=True)
    file_selector = _random_file_selector(file_id, file_path)

    res = client.list_children(space_specifier, file_path=dir_path)
    assert len(res["children"]) == 1

    client.remove(space_specifier, **file_selector)

    res = client.list_children(space_specifier, file_path=dir_path)
    assert len(res["children"]) == 0


def test_remove_with_readonly_token(
    client_krakow: OnedataFileRESTClient, client_ro_krakow: OnedataFileRESTClient
):
    """Test 'remove' method using readonly token."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client_krakow)

    dir_path = random_path()
    file_path = os.path.join(dir_path, random_str())
    file_id = client_krakow.create_file(space_specifier, file_path, create_parents=True)
    file_selector = _random_file_selector(file_id, file_path)

    file_content = random_bytes(1024)
    client_krakow.put_file_content(space_specifier, file_content, **file_selector)

    with pytest.raises(OnedataRESTError) as exc_info:
        client_ro_krakow.remove(space_specifier, **file_selector)

    e = exc_info.value
    assert e.http_code == 400
    assert e.category == "posix"
    assert e.description == "Operation failed with POSIX error: eacces."
    assert e.details == {"errno": "eacces"}


def test_move(client: OnedataFileRESTClient):
    """Test 'move' method."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    dir_path = random_path()
    file_path = os.path.join(dir_path, random_str())
    client.create_file(space_specifier, file_path, create_parents=True)

    target_test_dir = random_path()
    client.create_file(
        space_specifier, target_test_dir, file_type="DIR", create_parents=True
    )

    target_file_path = os.path.join(target_test_dir, random_str())

    res = client.list_children(space_specifier, file_path=dir_path)
    assert len(res["children"]) == 1

    client.move(space_specifier, file_path, space_specifier, target_file_path)

    res = client.list_children(space_specifier, file_path=dir_path)
    assert len(res["children"]) == 0

    res = client.list_children(space_specifier, file_path=target_test_dir)
    assert len(res["children"]) == 1


def _random_space_specifier(space_name, client):
    space_fqn = _get_space_fqn(space_name, client)
    return random.choice([space_name, space_fqn])


def _get_space_fqn(space_name, client):
    space_id = client.get_space_id(space_name)
    return f"{space_name}@{space_id}"


def _random_file_selector(file_id, file_path):
    if random.choice([True, False]):
        return {"file_id": file_id}

    return {"file_path": file_path}


def _random_provider_specifier(domain):
    # return domain if random.choice([True, False]) else _get_provider_id(domain)
    return _get_provider_id(domain)


def _get_provider_id(host: str) -> str:
    result = requests.get(
        f"https://{host}/api/v3/oneprovider/configuration",
        verify=False,
    )
    return result.json()["providerId"]


@contextmanager
def _mock_http_client_get(raise_connection_error_for_provider_domains):
    # pylint: disable=C0415
    from onedatafilerestclient.httpclient import HttpClient

    original_get_method = HttpClient.get

    def mock_get(self, url, *args, **kwargs):
        for domain in raise_connection_error_for_provider_domains:
            if domain in url:
                raise requests.exceptions.ConnectionError()

        return original_get_method(self, url, *args, **kwargs)

    try:
        HttpClient.get = mock_get
        yield
    finally:
        HttpClient.get = original_get_method


@contextmanager
def _mock_min_provider_version_supporting_new_file_attrs(mock_version):
    # pylint: disable=C0415
    import onedatafilerestclient.file_attributes as fa

    # pylint: disable=W0212
    original_version = fa._PROVIDER_SUPPORTING_CURRENT_API_KEY_MIN_VERSION
    try:
        # pylint: disable=W0212
        fa._PROVIDER_SUPPORTING_CURRENT_API_KEY_MIN_VERSION = mock_version
        yield
    finally:
        # pylint: disable=W0212
        fa._PROVIDER_SUPPORTING_CURRENT_API_KEY_MIN_VERSION = original_version
