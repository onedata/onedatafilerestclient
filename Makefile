.PHONY: submodules venv init format black-check static-analysis type-check lint test-with-clean test-without-clean dist pypi_check pypi_upload

STATIC_ANALYSER_IMAGE := "docker.onedata.org/python_static_analyser:v7"
SRC_FILES := onedatafilerestclient/ tests/ setup.py

UID := $(shell id -u)
GID := $(shell id -g)

define docker_run
	docker run --rm -i -v $(CURDIR):$(CURDIR) -w $(CURDIR) -u $(UID):$(GID) $(STATIC_ANALYSER_IMAGE) $1
endef

bold := $(shell tput bold)
normal := $(shell tput sgr0)
blue := $(shell tput setaf 4)

# Function to print target name
define print_target
	@echo ""
	@echo "$(blue)$(bold)$@:$(normal)"
endef

##
## Initialize project
##

submodules:
	$(call print_target)
	git submodule sync --recursive ${submodule}
	git submodule update --init --recursive ${submodule}

venv: SHELL:=/bin/bash
venv:
	$(call print_target)
	if [ ! -d "venv" ]; then virtualenv -p /usr/bin/python3 venv; fi
	if [ "x${VIRTUAL_ENV}" == "x" ]; then . venv/bin/activate; fi

init: venv submodules
	$(call print_target)
	pip install -r requirements-dev.txt

##
## Formatting
##

format:
	$(call print_target)
	$(call docker_run, isort -rc $(SRC_FILES))
	$(call docker_run, black --fast $(SRC_FILES))

##
## Linting
##

black-check:
	$(call print_target)
	$(call docker_run, black $(SRC_FILES) --check) || (echo "Code failed Black format checking. Please run 'make format' before commiting your changes."; exit 1)

static-analysis:
	$(call print_target)
	$(call docker_run, pylint $(SRC_FILES) --rcfile=.pylintrc --recursive=y)

type-check:
	$(call print_target)
	$(call docker_run, python3 -m tox -e mypy)

lint: black-check static-analysis type-check
	@:

##
## Testing
##

define run_tests
	./ct_run.py --verbose --image $(STATIC_ANALYSER_IMAGE) --onenv-config tests/test_env_config.yaml -s -x --junitxml=onedatafilerestclient-tests-results.xml $1
endef

test-with-clean:
	$(call print_target)
	$(call run_tests, --suite tests)

test-without-clean:
	$(call print_target)
	$(call run_tests, --no-clean --suite tests)

##
## Release
##

PYPI_PACKAGE_NAME := onedatafilerestclient

dist:
	$(call print_target)
	python3 -m build

pypi_check: dist
	$(call print_target)
	python3 -m twine check dist/*

pypi_upload: pypi_check
	$(call print_target)
	python3 -m twine upload --verbose dist/*

assert_uploaded:
	$(call print_target)
	@VERSION=$$(grep "__version__ =" setup.py | sed -E 's/__version__ = "([^\"]+)"/\1/'); \
	echo "Parsed version: $$VERSION"; \
	SANITIZED_VERSION=$$($(call docker_run, python3 -c "from packaging.version import Version; print(Version('$$VERSION'))")); \
	echo "Sanitized version: $$SANITIZED_VERSION"; \
	$(call docker_run, python3 -m pip install $(PYPI_PACKAGE_NAME)==$$SANITIZED_VERSION) || \
	(echo "Version $$SANITIZED_VERSION of package $(PYPI_PACKAGE_NAME) is NOT available on PyPI."; exit 1)
