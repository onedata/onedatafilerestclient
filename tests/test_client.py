# coding: utf-8
"""Test OnedataFileRESTClient methods."""

import os
import time

from onedatafilerestclient import OnedataFileRESTClient, OnedataRESTError

import pytest

from .common import random_bytes, random_int, random_path, random_str


@pytest.fixture
def client(onezone_ip, onezone_admin_token):
    """Create OnedataFileRESTClient instance."""
    return OnedataFileRESTClient(onezone_ip, onezone_admin_token)


@pytest.fixture
def client_ro(onezone_ip, onezone_readonly_token):
    """Create readonly OnedataFileRESTClient instance."""
    return OnedataFileRESTClient(onezone_ip, onezone_readonly_token)


@pytest.fixture
def client_krakow(onezone_ip, onezone_admin_token):
    """Create OnedataFileRESTClient instance bound to 'krakow' provider."""
    return OnedataFileRESTClient(
        onezone_ip, onezone_admin_token,
        ['dev-oneprovider-krakow.default.svc.cluster.local'])


@pytest.fixture
def client_ro_krakow(onezone_ip, onezone_readonly_token):
    """Create OnedataFileRESTClient instance bound to 'paris' provider."""
    return OnedataFileRESTClient(
        onezone_ip, onezone_readonly_token,
        ['dev-oneprovider-krakow.default.svc.cluster.local'])


def test_list_spaces(client):
    """Test 'list_spaces' method."""
    spaces = client.list_spaces()

    assert 'test_onedatarestfs' in spaces


def test_unsupported_space(client):
    """Test handling of an unsupported space."""
    spaces = client.list_spaces()

    assert 'test_onedatarestfs_nosupport' not in spaces


def test_create_file(client):
    """Test 'create_file' method."""
    file_path = random_path()
    file_id = client.create_file('test_onedatarestfs', file_path, 'REG', True)
    file_content = random_bytes(1024)

    client.put_file_content('test_onedatarestfs', file_id, 0, file_content)

    content = client.get_file_content('test_onedatarestfs',
                                      0,
                                      len(file_content),
                                      file_id=file_id)

    assert (content == file_content)


def test_create_and_list_files(client):
    """Test 'readdir' method."""
    file_count = 24

    test_dir = random_path()

    files = [
        os.path.join(test_dir, random_str(random_int(lower_bound=10)))
        for _ in range(file_count)
    ]

    for f in files:
        client.create_file('test_onedatarestfs', f, 'REG', True)

    res = client.readdir('test_onedatarestfs', test_dir)

    assert 'children' in res
    assert len(res['children']) == file_count


def test_delete_file(client):
    """Test 'remove' method."""
    test_dir = random_path()
    file_path = os.path.join(test_dir, random_str())
    client.create_file('test_onedatarestfs', file_path, 'REG', True)

    res = client.readdir('test_onedatarestfs', test_dir)

    assert len(res['children']) == 1

    client.remove('test_onedatarestfs', file_path)

    res = client.readdir('test_onedatarestfs', test_dir)

    assert len(res['children']) == 0


def test_rename_file(client):
    """Test 'move' method."""
    test_dir = random_path()
    file_path = os.path.join(test_dir, random_str())

    target_test_dir = random_path()
    target_file_path = os.path.join(target_test_dir, random_str())

    client.create_file('test_onedatarestfs', file_path, 'REG', True)

    res = client.readdir('test_onedatarestfs', test_dir)

    assert len(res['children']) == 1

    client.create_file('test_onedatarestfs', target_test_dir, 'DIR', True)

    client.move('test_onedatarestfs', file_path, 'test_onedatarestfs',
                target_file_path)

    res = client.readdir('test_onedatarestfs', test_dir)

    assert len(res['children']) == 0

    res = client.readdir('test_onedatarestfs', target_test_dir)

    assert len(res['children']) == 1


def test_readonly_token_read_same_provider(client_krakow, client_ro_krakow):
    """Test 'get_file_content' method using readonly token."""
    test_dir = random_path()
    file_path = os.path.join(test_dir, random_str())

    file_id = client_krakow.create_file('test_onedatarestfs', file_path, 'REG',
                                        True)
    file_content = random_bytes(1024)
    client_krakow.put_file_content('test_onedatarestfs', file_id, 0,
                                   file_content)

    assert client_krakow.get_provider_for_space(
        'test_onedatarestfs') == client_ro_krakow.get_provider_for_space(
            'test_onedatarestfs')

    assert client_ro_krakow.get_file_content('test_onedatarestfs',
                                             0,
                                             1024,
                                             file_id=file_id) == file_content


def test_readonly_token_read_random_provider(client, client_ro):
    """Test 'get_file_content' method using ro token from any provider."""
    test_dir = random_path()
    file_path = os.path.join(test_dir, random_str())

    file_id = client.create_file('test_onedatarestfs', file_path, 'REG', True)
    file_content = random_bytes(1024)
    client.put_file_content('test_onedatarestfs', file_id, 0, file_content)

    #
    # Since providers are selected randomly, we have to wait until
    # both providers supporting this space are aware of the file
    # and it's location
    #
    retry_count = 30
    while retry_count > 0:
        try:
            assert client_ro.get_file_content('test_onedatarestfs',
                                              0,
                                              1024,
                                              file_id=file_id) == file_content
            break
        except OnedataRESTError:
            time.sleep(1)
            retry_count -= 1

    assert retry_count > 0


def test_readonly_token_delete_eacces(client_krakow, client_ro_krakow):
    """Test 'remove' method using readonly token."""
    test_dir = random_path()
    file_path = os.path.join(test_dir, random_str())

    file_id = client_krakow.create_file('test_onedatarestfs', file_path, 'REG',
                                        True)
    file_content = random_bytes(1024)
    client_krakow.put_file_content('test_onedatarestfs', file_id, 0,
                                   file_content)

    with pytest.raises(OnedataRESTError) as excinfo:
        client_ro_krakow.remove('test_onedatarestfs', file_path)

    e = excinfo.value
    assert e.http_code == 400
    assert e.error_category == 'posix'
    assert e.error_details == {"errno": "eacces"}
    assert e.description == "Operation failed with POSIX error: eacces."


def test_enoent_space(client):
    """Test 'get_file_content' on non-existing space."""
    with pytest.raises(OnedataRESTError) as excinfo:
        client.get_file_content('NO_SUCH_SPACE',
                                0,
                                1024,
                                file_path=random_path())

    e = excinfo.value
    assert e.http_code == 400
    assert e.error_category == 'posix'
    assert e.error_details == "Space NO_SUCH_SPACE doesn't exist"
    assert e.description == "enoent"


def test_enoent_file(client):
    """Test 'get_file_content' on non-existing file."""
    test_dir = random_path()
    file_path = os.path.join(test_dir, random_str())

    with pytest.raises(OnedataRESTError) as excinfo:
        client.get_file_content('test_onedatarestfs',
                                0,
                                1024,
                                file_path=file_path)

    e = excinfo.value
    assert e.http_code == 400
    assert e.error_category == 'posix'
    assert e.error_details == {"errno": "enoent"}
    assert e.description == "Operation failed with POSIX error: enoent."
