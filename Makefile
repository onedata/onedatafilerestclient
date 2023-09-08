.PHONY: submodules venv init format flake8 yapf mypy link

submodules:
		git submodule sync --recursive ${submodule}
		git submodule update --init --recursive ${submodule}

venv: SHELL:=/bin/bash
venv:
		if [ ! -d "venv" ]; then virtualenv -p /usr/bin/python3 venv; fi
		if [ "x${VIRTUAL_ENV}" == "x" ]; then . venv/bin/activate; fi

init: venv submodules
		pip install -r requirements-dev.txt

format:
		python3 -m yapf -i setup.py onedatafilerestclient/*.py tests/*.py

flake8:
		python3 -m tox -e flake8

yapf:
		python3 -m tox -e yapf

mypy:
		python3 -m tox -e mypy

lint: flake8 yapf mypy
		@:

test:
		python3 -m tox -e test



