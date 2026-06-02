"""Shared helpers and fixtures for e2e pipeline tests."""
from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import pytest

import sys

import paper_pdf_ingest.convert  # ensure submodule is in sys.modules
from paper_pdf_ingest.convert import augment_markdown_with_formulas, convert

_convert_module = sys.modules['paper_pdf_ingest.convert']
from paper_pdf_ingest.output import write_paper_output
from paper_pdf_ingest.sections import clean_sections, split_sections


# ── PDF path helpers ──────────────────────────────────────────────────────────

def get_ieee_pdf_path() -> Path:
    return Path(__file__).resolve().parent.parent / 'data' / 'ieee-conference.pdf'


def get_hairpin_pdf_path() -> Path:
    """Path to wang-hairpin-2025 PDF stored in tests/data/."""
    return Path(__file__).resolve().parent.parent / 'data' / 'wang-hairpin-2025.pdf'


_hairpin_skip = pytest.mark.skipif(
    not get_hairpin_pdf_path().exists(),
    reason='wang-hairpin-2025 PDF not available (gitignored real paper data)',
)


# ── Pipeline runner ───────────────────────────────────────────────────────────

def run_full_pipeline(pdf: Path, out_dir: Path, method: str) -> tuple[Path, int, int, int]:
    """Force *method*, run full pipeline, return (out_dir, n_sec, n_fig, n_tbl)."""
    original = _convert_module.choose_tool
    _convert_module.choose_tool = lambda: method
    try:
        md_text, tool_used = convert(pdf, out_dir)
        assert tool_used == method, f'Expected {method}, got {tool_used}'
        md_text = augment_markdown_with_formulas(md_text, pdf)
        raw = split_sections(md_text)
        main, _app = clean_sections(raw)
        assert main, 'No sections extracted from PDF'
        n_sec, n_fig, n_tbl = write_paper_output(main, out_dir, md_text, pdf_path=pdf)
    finally:
        _convert_module.choose_tool = original
    return out_dir, n_sec, n_fig, n_tbl


# ── Module-scoped ingest cache (avoids re-running expensive OCR per test) ────

def _cached_ingest(pdf: Path, method: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run the full pipeline once per (pdf, method) pair per test session."""
    out = tmp_path_factory.mktemp(f'{pdf.stem}_{method}')
    run_full_pipeline(pdf, out, method)
    return out


@pytest.fixture(scope='module')
def hairpin_out_pymupdf4llm(tmp_path_factory):
    pdf = get_hairpin_pdf_path()
    if not pdf.exists():
        pytest.skip('wang-hairpin-2025 PDF not available')
    return _cached_ingest(pdf, 'pymupdf4llm', tmp_path_factory)


@pytest.fixture(scope='module')
def hairpin_out_marker(tmp_path_factory):
    from tests.conftest import marker_available
    pdf = get_hairpin_pdf_path()
    if not pdf.exists():
        pytest.skip('wang-hairpin-2025 PDF not available')
    if not marker_available():
        pytest.skip('marker_single not available or GPU < 4GB')
    return _cached_ingest(pdf, 'marker', tmp_path_factory)


# ── Image utilities ───────────────────────────────────────────────────────────

def read_png_size(path: Path) -> tuple[int, int]:
    """Read PNG width/height from IHDR (no PIL dependency)."""
    with open(path, 'rb') as f:
        if f.read(8) != b'\x89PNG\r\n\x1a\n':
            raise ValueError(f'Not a PNG: {path.name}')
        f.seek(8 + 4 + 4)
        w, h = struct.unpack('>ii', f.read(8))
    return w, h


def collect_pngs(out_dir: Path) -> list[Path]:
    return sorted(out_dir.rglob('img/sec*/*.png'))


def png_matches_label(p: Path, label: str) -> bool:
    """True if PNG filename ends with -<slug>.png for *label*."""
    slug = label.lower().replace(' ', '-')
    return p.name.lower().endswith(f'-{slug}.png')
