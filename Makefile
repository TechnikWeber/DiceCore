# Convenience only — everything here is a one-liner you can also type yourself.
VENV ?= .venv
PY   := $(VENV)/bin/python

.PHONY: venv test lint run synth doctor clean

venv:                     ## create the venv and install everything for development
	python3 -m venv $(VENV)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -e '.[vision,server,dev]'

test:                     ## the whole suite; needs no hardware
	$(PY) -m pytest -q

lint:
	$(VENV)/bin/ruff check src tests

synth:                    ## fill the simulator folder with rendered rolls
	$(VENV)/bin/dicecore synth --count 20 --kinds d6,d20

run:                      ## API + setup page on http://localhost:8099/
	$(VENV)/bin/dicecore serve

doctor:                   ## what this machine can do, and what the camera says
	$(VENV)/bin/dicecore doctor

clean:
	rm -rf .pytest_cache .ruff_cache src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
