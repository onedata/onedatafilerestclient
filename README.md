# OnedataFileRESTClient

OnedataFileRESTClient is a Python client to the Onedata file REST API [Onedata REST API].

## Installing

You can install OnedataFileRESTClient from pip as follows:

```
pip install onedatafilerestclient
```

## Building and running tests

```bash
virtualenv -p /usr/bin/python3 venv
. venv/bin/activate

# Install tox
pip install -r requirements-dev.txt

# Run flake8 check
tox -c tox.ini -e flake8

# Run mypy typing check
tox -c tox.ini -e mypy

# Run PyFilesystem test suite
tox -c tox.ini -e tests
```
