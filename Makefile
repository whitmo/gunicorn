#!/usr/bin/make
PYTHON := /usr/bin/env python

unit_test:
	nosetests -s --with-coverage --cover-package=hooks hooks

sync-charm-helpers: bin/charm_helpers_sync.py
	@mkdir -p bin
	@$(PYTHON) bin/charm_helpers_sync.py -c charm-helpers.yaml

bin/charm_helpers_sync.py:
	@bzr cat lp:charm-helpers/tools/charm_helpers_sync/charm_helpers_sync.py > bin/charm_helpers_sync.py
