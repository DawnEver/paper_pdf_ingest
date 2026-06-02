# paper_pdf_ingest

Standalone Python library — PDF → per-section markdown + cropped figure images.

## Dev workflow

```bash
# Install dev deps (once)
uv sync --all-extras

# Run tests
uv run pytest

# Run tests with coverage
make test-cov

# Lint + format
make lint
make fmt
```

## Used by paper-review

The parent `paper-review` pipeline installs this library into a shared venv:

```bash
~/.local/share/paper-review-venv/bin/pip install -e .
```

When working on the library from within the paper-review context, use that venv to run tests:

```bash
~/.local/share/paper-review-venv/bin/pytest tests/ -q
```
