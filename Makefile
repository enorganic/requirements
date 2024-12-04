SHELL := bash
# This is the version of python used for linting
LINT_PYTHON_VERSION := 3.8
.PHONY: docs

# Create all environments
install:
	{ hatch --version || pipx install --upgrade hatch || python3 -m pip install --upgrade hatch ; } && \
	hatch run pip install --upgrade pip && \
	hatch run docs:pip install --upgrade pip && \
	hatch run docs:pip install --upgrade pip && \
	hatch run test:pip install --upgrade pip && \
	{ hatch run mypy --install-types --non-interactive || echo "" ; } && \
	echo "Installation complete"

# Re-create all environments, from scratch (no reference to pinned
# requirements)
reinstall:
	{ hatch --version || pipx install --upgrade hatch || python3 -m pip install --upgrade hatch ; } && \
	echo "" > default_requirements.txt && \
	echo "" > docs_requirements.txt && \
	echo "" > test_requirements.txt && \
	hatch env prune && \
	make && \
	make requirements

distribute:
	hatch build && hatch publish && rm -rf dist

# This will upgrade all requirements, and refresh pinned requirements to
# match
upgrade:
	echo "" > default_requirements.txt && \
	echo "" > docs_requirements.txt && \
	echo "" > test_requirements.txt && \
	hatch run dependence freeze\
	 --include-pointer /tool/hatch/envs/default\
	 --include-pointer /project\
	 pyproject.toml > .requirements.txt && \
	hatch run pip install --upgrade --upgrade-strategy eager\
	 -r .requirements.txt && \
	rm .requirements.txt && \
	hatch run docs:dependence freeze\
	 --include-pointer /tool/hatch/envs/docs\
	 --include-pointer /project\
	 pyproject.toml > .requirements.txt && \
	hatch run docs:pip install --upgrade --upgrade-strategy eager\
	 -r .requirements.txt && \
	hatch run test:dependence freeze\
	 --include-pointer /tool/hatch/envs/test\
	 --include-pointer /project\
	 pyproject.toml > .requirements.txt && \
	hatch run test:pip install --upgrade --upgrade-strategy eager\
	 -r .requirements.txt && \
	rm .requirements.txt && \
	make requirements

# This will update pinned requirements to align with the
# package versions installed in each environment, and will align the project
# dependency versions with those installed in the default environment
requirements:
	hatch run dependence update\
	 --include-pointer /tool/hatch/envs/default\
	 --include-pointer /project\
	 pyproject.toml && \
	hatch run docs:dependence update pyproject.toml --include-pointer /tool/hatch/envs/docs && \
	hatch run test:dependence update pyproject.toml --include-pointer /tool/hatch/envs/test && \
	hatch run dependence freeze\
	 -e pip \
	 -e wheel \
	 --include-pointer /tool/hatch/envs/default \
	 . \
	 pyproject.toml \
	 > default_requirements.txt && \
	hatch run docs:dependence freeze\
	 -e pip \
	 -e wheel \
	 --include-pointer /tool/hatch/envs/docs \
	 . \
	 pyproject.toml \
	 > docs_requirements.txt && \
	hatch run test:dependence freeze\
	 -e pip \
	 -e wheel \
	 --include-pointer /tool/hatch/envs/test \
	 . \
	 pyproject.toml \
	 > test_requirements.txt

# Run all tests
test:
	if [[ "$$(python -V)" = "Python $(LINT_PYTHON_VERSION)."* ]] ;\
	then hatch run lint && hatch run test:test ;\
	else hatch run test:test ;\
	fi

format:
	hatch run ruff check --select I --fix . && \
	hatch run ruff format . && \
	hatch run ruff check . && \
	hatch run mypy && \
	echo "Format Successful!"

docs:
	hatch run docs:mkdocs build && \
	hatch run docs:mkdocs serve
