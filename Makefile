.DEFAULT_GOAL := all

.PHONY: install-dev
install-dev:
	uv pip install -U pip wheel
	uv pip install -e ".[dev]"

.PHONY: setup-hooks
setup-hooks:
	pre-commit install
	pre-commit install --hook-type pre-push

.PHONY: lint
lint:
	ruff check src tests
	ruff format --check src tests

.PHONY: fmt
fmt:
	ruff check --fix src tests
	ruff format src tests

.PHONY: test
test:
	pytest

.PHONY: test-cov
test-cov:
	pytest --cov=src/paper_pdf_ingest --cov-report html

.PHONY: all
all: fmt lint test

.PHONY: clean
clean:
	python -c "import pathlib, shutil; p = pathlib.Path('.'); [shutil.rmtree(d, ignore_errors=True) for d in p.rglob('__pycache__') if d.is_dir()]; [shutil.rmtree(pathlib.Path(x), ignore_errors=True) for x in ('dist', 'build', '.pytest_cache', '.ruff_cache', 'htmlcov', '.venv')]"
