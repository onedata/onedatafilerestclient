# coding: utf-8
"""Test OnedataFileRESTClient methods."""

import json
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
    ReadonlyTokenError,
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
    SPACE_NO_SUPPORT_NAME,
    SPACE_PAR_NAME,
    ZONE_DOMAIN,
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
    """Test 'list_spaces' method.

    Test listing user spaces and proper handling of duplicate space names
    (the space with no support is duplicated, see the test_env_config.yaml)
    """
    token_scope = client.get_token_scope()
    space_registry = token_scope["dataAccessScope"]["spaces"]

    exp_space_list = []
    for space_id, space_details in space_registry.items():
        space_specifier = space_details["name"]
        if space_specifier == SPACE_NO_SUPPORT_NAME:
            space_specifier = _pack_space_fqn(space_specifier, space_id)

        exp_space_list.append(space_specifier)

    exp_space_list.sort()

    assert exp_space_list == sorted(client.list_spaces())


def test_get_space_id(onezone_ip, onezone_admin_token):
    """Test 'get_space_id' method."""
    client = OnedataFileRESTClient(
        onezone_ip, onezone_admin_token, [PROVIDER_KRK_DOMAIN], verify_ssl=False
    )
    client._oz_client._space_id_cache_size_limit = 2  # pylint: disable=W0212

    space_par_id = client.get_space_id(SPACE_PAR_NAME)

    # space_fqn resolution should not be cached
    space_par_fqn = _pack_space_fqn(SPACE_PAR_NAME, space_par_id)
    assert client.get_space_id(space_par_fqn) == space_par_id

    space_par_new_name = random_str()
    _rename_space(onezone_admin_token, space_par_id, space_par_new_name)

    try:
        # changes should not be reflected automatically since token is cached
        time.sleep(1)
        assert space_par_id == client.get_space_id(SPACE_PAR_NAME)
        with pytest.raises(SpaceNotFoundError):
            client.get_space_id(space_par_new_name)

        # but after cache expires the changes should be reflected
        time.sleep(3)
        with pytest.raises(SpaceNotFoundError):
            client.get_space_id(SPACE_PAR_NAME)

        assert space_par_id == client.get_space_id(space_par_new_name)

        # using fqn returns id from fqn so no resolution is made and old name
        # still works
        assert client.get_space_id(space_par_fqn) == space_par_id
    finally:
        _rename_space(onezone_admin_token, space_par_id, SPACE_PAR_NAME)
        time.sleep(3)


def test_provider_selector(
    onezone_ip, onezone_admin_token, client_krakow, client_paris
):
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
    file_id = _create_and_sync_file_in_space(
        space_specifier, client_krakow, client_paris
    )

    def assert_selected_provider(provider_domain):
        client.get_attributes(space_specifier, file_id=file_id)
        assert _get_selected_provider(client, space_specifier).domain == provider_domain

        random_mode = random.choice(["777", "775", "773", "771", "770"])
        client.set_attributes(space_specifier, {"mode": random_mode}, file_id=file_id)
        assert _get_selected_provider(client, space_specifier).domain == provider_domain

    # provider 'first_choice_provider' is chosen with accordance to
    # preferred providers
    assert_selected_provider(first_choice_provider)

    # with connection error raised 'first_choice_provider' should be
    # blacklisted for a while and next in line provider
    # - second_choice_provider - should be selected
    with _mock_http_client([first_choice_provider]):
        assert_selected_provider(second_choice_provider)

    assert_selected_provider(second_choice_provider)

    # with connection error raised by 'second_choice_provider' there should
    # be no available providers left
    with _mock_http_client([second_choice_provider]):
        with pytest.raises(NoAvailableProviderForSpaceError) as exc_info:
            client.get_attributes(space_specifier, file_id=file_id)

        assert exc_info.value.args == (space_specifier,)

    # even without mock providers should still be blacklisted
    with pytest.raises(NoAvailableProviderForSpaceError) as exc_info:
        client.set_attributes(space_specifier, {"mode": "777"}, file_id=file_id)

    assert exc_info.value.args == (space_specifier,)

    # but after blacklist time ends 'first_choice_provider' should be
    # again selected
    time.sleep(2)
    assert_selected_provider(first_choice_provider)


def test_provider_selector_with_readonly_provider(
    onezone_ip, onezone_admin_token, client_krakow, client_paris
):
    """Test readonly provider fallback on connection error."""
    providers = [PROVIDER_KRK_DOMAIN, PROVIDER_PAR_DOMAIN]
    random.shuffle(providers)
    first_choice_provider, second_choice_provider = providers
    first_choice_provider_id = _get_provider_id(first_choice_provider)

    client = OnedataFileRESTClient(
        onezone_ip,
        onezone_admin_token,
        [_random_provider_specifier(first_choice_provider)],
        verify_ssl=False,
    )

    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)
    space_id = client.get_space_id(space_specifier)
    file_id = _create_and_sync_file_in_space(
        space_specifier, client_krakow, client_paris
    )

    # pylint: disable=W0212
    client._provider_selector._blacklist_time_limit_ns = 1 * 10**9  # 1 second

    # mock token scope so that 'first_choice_provider' has readonly support
    _patch_provider_readonly_support(client, space_id, first_choice_provider_id)

    def get_selected_provider_domain(except_readonly):
        return _get_selected_provider(
            client, space_specifier, except_readonly=except_readonly
        ).domain

    def assert_selected_provider(read_provider_domain, write_provider_domain=None):
        client.get_attributes(space_specifier, file_id=file_id)
        assert get_selected_provider_domain(False) == read_provider_domain

        if write_provider_domain is None:
            write_provider_domain = read_provider_domain
        random_mode = random.choice(["777", "775", "773", "771", "770"])
        client.set_attributes(space_specifier, {"mode": random_mode}, file_id=file_id)
        assert get_selected_provider_domain(True) == write_provider_domain

    # provider 'first_choice_provider' is chosen with accordance to
    # preferred providers but only for read (readonly support)
    assert_selected_provider(first_choice_provider, second_choice_provider)

    # with connection error raised 'first_choice_provider' should be
    # blacklisted for a while and next in line provider
    # - second_choice_provider - should be selected
    with _mock_http_client([first_choice_provider]):
        assert_selected_provider(second_choice_provider)

    assert_selected_provider(second_choice_provider)

    # with connection error raised by 'second_choice_provider' there should
    # be no available providers left
    with _mock_http_client([second_choice_provider]):
        with pytest.raises(NoAvailableProviderForSpaceError) as exc_info:
            client.get_attributes(space_specifier, file_id=file_id)

        assert exc_info.value.args == (space_specifier,)

    # even without mock providers should still be blacklisted
    with pytest.raises(NoAvailableProviderForSpaceError) as exc_info:
        client.set_attributes(space_specifier, {"mode": "777"}, file_id=file_id)

    assert exc_info.value.args == (space_specifier,)

    # but after blacklist time ends 'first_choice_provider' should be
    # again selected for read and 'second_choice_provider' for write
    time.sleep(2)
    assert_selected_provider(first_choice_provider, second_choice_provider)

    # with connection error raised by 'second_choice_provider' there should
    # be no available providers for write but read should still work
    with _mock_http_client([second_choice_provider]):
        with pytest.raises(NoAvailableProviderForSpaceError) as exc_info:
            client.set_attributes(space_specifier, {"mode": "777"}, file_id=file_id)

        assert exc_info.value.args == (space_specifier,)

    client.get_attributes(space_specifier, file_id=file_id)
    assert get_selected_provider_domain(False) == first_choice_provider


def test_provider_selector_with_offline_provider(onezone_ip, onezone_admin_token):
    """Test offline provider should be omitted."""
    providers = [PROVIDER_KRK_DOMAIN, PROVIDER_PAR_DOMAIN]
    random.shuffle(providers)
    first_choice_provider, second_choice_provider = providers
    first_choice_provider_id = _get_provider_id(first_choice_provider)

    client = OnedataFileRESTClient(
        onezone_ip,
        onezone_admin_token,
        [_random_provider_specifier(first_choice_provider)],
        verify_ssl=False,
    )
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    _patch_provider_offline(client, first_choice_provider_id)

    client.get_attributes(space_specifier)
    assert (
        _get_selected_provider(client, space_specifier).domain == second_choice_provider
    )


def test_provider_selector_with_dummy_provider(onezone_ip, onezone_admin_token):
    """Test dummy provider should be omitted."""
    client_1 = OnedataFileRESTClient(
        onezone_ip,
        onezone_admin_token,
        ["dummy.org", _random_provider_specifier(PROVIDER_KRK_DOMAIN)],
        verify_ssl=False,
    )
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client_1)

    client_1.get_attributes(space_specifier)
    assert (
        _get_selected_provider(client_1, space_specifier).domain == PROVIDER_KRK_DOMAIN
    )

    client_2 = OnedataFileRESTClient(
        onezone_ip,
        onezone_admin_token,
        ["dummyId", _random_provider_specifier(PROVIDER_PAR_DOMAIN)],
        verify_ssl=False,
    )
    client_2.get_attributes(space_specifier)
    assert (
        _get_selected_provider(client_2, space_specifier).domain == PROVIDER_PAR_DOMAIN
    )


def test_get_file_id(client: OnedataFileRESTClient):
    """Test 'get_file_id' method."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    file_path = random_path()
    file_id = client.create_file(space_specifier, file_path, create_parents=True)

    assert file_id == client.get_file_id(space_specifier, file_path=file_path)


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
    with _mock_min_provider_version_supporting_new_file_attrs(Version("300.1.1")):
        requested_attr_keys = random.sample(_DEPRECATED_BASIC_FILE_ATTR_KEYS.keys(), 5)
        requested_attr_keys.append("acl")

        with pytest.raises(OnedataRESTError) as exc_info:
            client.get_attributes(space_specifier, attributes=requested_attr_keys)

        selected_provider = _get_selected_provider(client, space_specifier)
        error = exc_info.value
        assert error.http_code == 400
        assert error.category == "posix"
        assert error.details == (
            f"The provider chosen for this space ({selected_provider.domain}) is in version "
            f"({selected_provider.version}) that does not support the 'acl' "
            "attribute (requires Oneprovider version >= 300.1.1)"
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
    dir_id = client.get_file_id(space_specifier, file_path=dir_path)
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
    client_krakow.put_file_content(
        space_specifier, data=exp_file_content, **file_selector
    )

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
    client_krakow.put_file_content(space_specifier, data=file_content, **file_selector)

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


def test_eacces_file(onezone_ip, onezone_space_member_token):
    """Test 'get_file_content' on non-existing file."""
    client = OnedataFileRESTClient(
        onezone_ip, onezone_space_member_token, verify_ssl=False
    )

    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client)

    file_path = random_path()
    file_id = client.create_file(space_specifier, file_path, create_parents=True)
    file_selector = _random_file_selector(file_id, file_path)

    client.set_attributes(space_specifier, {"mode": "000"}, **file_selector)

    print(_get_selected_provider(client, space_specifier).domain)
    with pytest.raises(OnedataRESTError) as exc_info:
        file_content = random_bytes(1024)
        client.put_file_content(space_specifier, data=file_content, **file_selector)
        print(_get_selected_provider(client, space_specifier).domain)

    e = exc_info.value
    assert e.http_code == 400
    assert e.category == "posix"
    assert e.description == "Operation failed with POSIX error: eacces."
    assert e.details == {"errno": "eacces"}


def test_iter_file_content(client_krakow: OnedataFileRESTClient):
    """Test 'iter_file_content' method."""
    space_specifier = _random_space_specifier(SPACE_KRK_PAR_NAME, client_krakow)

    file_path = random_path()
    file_id = client_krakow.create_file(space_specifier, file_path, create_parents=True)
    file_selector = _random_file_selector(file_id, file_path)

    file_content = random_bytes(1024)
    client_krakow.put_file_content(space_specifier, data=file_content, **file_selector)

    chunk_size = random_int(4, 100)
    stream = client_krakow.iter_file_content(
        space_specifier, chunk_size=chunk_size, **file_selector
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
    client.put_file_content(
        space_specifier, data=rand_bytes, offset=100, **file_selector
    )
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
    client.put_file_content(space_specifier, data=file_content, **file_selector)

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
    client_krakow.put_file_content(space_specifier, data=file_content, **file_selector)

    with pytest.raises(ReadonlyTokenError):
        client_ro_krakow.remove(space_specifier, **file_selector)


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
    return _pack_space_fqn(space_name, client.get_space_id(space_name))


def _pack_space_fqn(space_name, space_id):
    return f"{space_name}@{space_id}"


def _random_file_selector(file_id, file_path):
    if random.choice([True, False]):
        return {"file_id": file_id}

    return {"file_path": file_path}


def _random_provider_specifier(domain):
    # return domain if random.choice([True, False]) else _get_provider_id(domain)
    return _get_provider_id(domain)


def _get_selected_provider(client, space_specifier, *, except_readonly=False):
    # pylint: disable=W0212
    oz_client = client._oz_client
    provider = next(
        client._provider_selector.iter_available_space_providers(
            space_specifier, oz_rest_client=oz_client, except_readonly=except_readonly
        )
    )
    return provider


def _create_and_sync_file_in_space(space_specifier, client_krakow, client_paris):
    file_id = client_krakow.create_file(
        space_specifier, random_str(), create_parents=True
    )
    for _ in range(10):
        result = client_paris.list_children(space_specifier, attributes=["fileId"])
        if {"fileId": file_id} in result["children"]:
            break
        time.sleep(1)
    else:
        assert False, "Failed to create and sync file between providers"

    return file_id


def _rename_space(token, space_id, new_name):
    result = requests.patch(
        f"https://{ZONE_DOMAIN}/api/v3/onezone/spaces/{space_id}",
        headers={"X-Auth-Token": token, "Content-type": "application/json"},
        data=json.dumps({"name": new_name}),
        verify=False,
    )
    if not result.ok:
        raise OnedataRESTError.from_response(result)


def _get_provider_id(host: str) -> str:
    result = requests.get(
        f"https://{host}/api/v3/oneprovider/configuration",
        verify=False,
    )
    return result.json()["providerId"]


def _patch_provider_readonly_support(client, space_id, provider_id):
    # pylint: disable=W0212
    client._oz_client._token_scope_cache_time_limit_ns = 30 * 10**9  # 30 seconds
    access_token_scope = client.get_token_scope()
    space_details = access_token_scope["dataAccessScope"]["spaces"][space_id]
    space_details["supports"][provider_id]["readonly"] = True
    client._oz_client._token_scope_cache = access_token_scope


def _patch_provider_offline(client, provider_id):
    # pylint: disable=W0212
    client._oz_client._token_scope_cache_time_limit_ns = 30 * 10**9  # 30 seconds
    access_token_scope = client.get_token_scope()
    access_token_scope["dataAccessScope"]["providers"][provider_id]["online"] = False
    client._oz_client._token_scope_cache = access_token_scope


@contextmanager
def _mock_http_client(raise_connection_error_for_provider_domains):
    # pylint: disable=C0415
    from onedatafilerestclient.http_client import HttpClient

    # pylint: disable=W0212
    original_send_request_method = HttpClient._send_request

    def mock_send_request(self, method, url, *args, **kwargs):
        for domain in raise_connection_error_for_provider_domains:
            if domain in url:
                raise requests.exceptions.ConnectionError()

        return original_send_request_method(self, method, url, *args, **kwargs)

    try:
        # pylint: disable=W0212
        HttpClient._send_request = mock_send_request
        yield
    finally:
        # pylint: disable=W0212
        HttpClient._send_request = original_send_request_method


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
