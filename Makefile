SHELL := bash
PYTHON_VERSION := 3.8
.PHONY: docs

install:
	{ python$(PYTHON_VERSION) -m venv venv || py -$(PYTHON_VERSION) -m venv venv ; } && \
	{ . venv/bin/activate || venv/Scripts/activate.bat ; } && \
	python3 -m pip install --upgrade pip && \
	pip install -r frozen_requirements.txt -e . && \
	{ mypy --install-types --non-interactive || echo "" ; } && \
	echo "Installation complete"

ci-install:
	{ python3 -m venv venv || py -3 -m venv venv ; } && \
	{ . venv/bin/activate || venv/Scripts/activate.bat ; } && \
	python3 -m pip install --upgrade pip && \
	pip install -r frozen_requirements.txt -e . && \
	echo "Installation complete"

reinstall:
	{ rm -R venv || echo "" ; } && \
	{ python$(PYTHON_VERSION) -m venv venv || py -$(PYTHON_VERSION) -m venv venv ; } && \
	{ . venv/bin/activate || venv/Scripts/activate.bat ; } && \
	python3 -m pip install --upgrade pip && \
	pip install -r dev_requirements.txt -r test_requirements.txt -e . && \
	{ mypy --install-types --non-interactive || echo "" ; } && \
	make requirements && \
	echo "Installation complete"

clean:
	{ . venv/bin/activate || venv/Scripts/activate.bat ; } && \
	daves-dev-tools uninstall-all\
	 -e .\
     -e pyproject.toml\
     -e tox.ini\
     -e frozen_requirements.txt && \
	daves-dev-tools clean

distribute:
	{ . venv/bin/activate || venv/Scripts/activate.bat ; } && \
	daves-dev-tools distribute --skip-existing

upgrade:
	{ . venv/bin/activate || venv/Scripts/activate.bat ; } && \
	dependence freeze\
	 -nv '*' . pyproject.toml tox.ini dev_requirements.txt \
	 > .frozen_requirements.txt && \
	pip install --upgrade --upgrade-strategy eager\
	 -r .frozen_requirements.txt && \
	rm .frozen_requirements.txt && \
	make requirements

requirements:
	{ . venv/bin/activate || venv/Scripts/activate.bat ; } && \
	dependence update\
	 setup.cfg pyproject.toml tox.ini && \
	dependence freeze\
	 -e pip\
	 -e wheel\
	 . pyproject.toml tox.ini dev_requirements.txt\
	 > frozen_requirements.txt && \
	dependence freeze -nv '*' -d 0 tox.ini > test_requirements.txt

# Run all tests
test:
	{ . venv/bin/activate || venv/Scripts/activate.bat ; } && \
	if [[ "$$(python -V)" = "Python $(PYTHON_VERSION)."* ]] ;\
	then tox -r -p -o ;\
	else tox -r -e pytest ;\
	fi

format:
	{ . venv/bin/activate || venv/Scripts/activate.bat ; } && \
	isort . && black . && flake8 && mypy

docs:
	{ . venv/bin/activate || venv/Scripts/activate.bat ; } && \
	mkdocs build && \
	mkdocs serve
