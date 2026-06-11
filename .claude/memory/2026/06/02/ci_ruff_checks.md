---
name: ci-ruff-checks
description: Ruff lint + format MUST pass in CI; auto-fix first, then handle remaining issues manually
metadata:
  type: feedback
---

Always verify `ruff check && ruff format --check` pass before pushing. The CI runs both with zero tolerance.

**Why:** First CI run on this repo failed with 100+ lint violations and format mismatches — everything from os.path→pathlib (PTH), ambiguous Unicode chars (RUF001/002/003), import ordering (E402/I001), unused variables (B007), fixture redefinitions (F811).

**How to apply:**
1. Run `uv run ruff check --fix` first for auto-fixable issues
2. Run `uv run ruff format` for formatting
3. Handle remaining check-only violations manually — common patterns:
   - PTH: prefer `Path(...).parent` / `Path(...) / 'file'` over `os.path.dirname`/`os.path.join`
   - RUF001/002/003: use ASCII equivalents in comments/strings (en dash → hyphen, × → x)
   - F811 in tests: don't import conftest fixtures — pytest discovers them automatically
   - RUF001 in intentional math detection strings: add `# noqa: RUF001`
4. Run `uv run ruff check && uv run ruff format --check` to confirm clean
