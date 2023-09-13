# OnedataFileRESTClient

[![Build status](https://github.com/onedata/onedatafilerestclient/actions/workflows/workflow.yml/badge.svg)](https://github.com/onedata/onedatafilerestclient/actions)
[![Version](https://img.shields.io/pypi/pyversions/onedatafilerestclient.svg)](https://pypi.python.org/pypi/onedatafilerestclient)

OnedataFileRESTClient is a Python client to the Onedata file REST API [Onedata REST API](https://onedata.org/#/home/api/stable/oneprovider).

## Installing

You can install OnedataFileRESTClient from [PyPI](https://pypi.python.org/pypi/onedatafilerestclient) as follows:

```
pip install onedatafilerestclient
```

## Building and running tests manually

```bash
virtualenv -p /usr/bin/python3 venv
. venv/bin/activate

# Install tox
pip install -r requirements-dev.txt

# Run flake8 check
tox -c tox.ini -e flake8

# Run yapf format check
tox -c tox.ini -e yapf

# Run mypy typing check
tox -c tox.ini -e mypy

# Run PyFilesystem test suite (requires preexisting K8S Onedata deployment in default namespace)
tox -c tox.ini -e tests
```

## Running tests automatically

```bash
virtualenv -p /usr/bin/python3 venv
. venv/bin/activate

./ct_run.py --verbose --image onedata/pybuilder:v2 --onenv-config tests/test_env_config.yaml --no-clean -s --suite flake8 --suite yapf --suite mypy --suite tests
```