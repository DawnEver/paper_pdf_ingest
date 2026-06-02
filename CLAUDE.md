# paper_pdf_ingest


Always use the shared venv at `~/.local/share/paper-review-venv` — do **not** use `uv run` or the project's `.venv`.

```bash
~/.local/share/paper-review-venv/bin/pytest tests/ -q --override-ini="addopts="
```

The `--override-ini="addopts="` strips the coverage flags from `pyproject.toml` that require `pytest-cov` (not installed in the shared venv).
