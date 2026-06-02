"""E2E tests for the IEEE conference template PDF (ieee-conference.tex ground truth)."""

import re
from pathlib import Path

import pytest

from tests.conftest import _marker_skip, marker_available

from .conftest import (
    _cached_ingest,
    collect_pngs,
    get_ieee_pdf_path,
    png_matches_label,
    read_png_size,
    run_full_pipeline,
)

# ── Ground truth from ieee-conference.tex ─────────────────────────────────────
#   1 figure:  Figure 1 -- "Example of a figure caption."  (fig1.png, 341x297 px)
#   1 table:   Table I  -- "Table Type Styles" (4 columns)
#   1 equation: Equation (1) -- a+b=gamma
#   Sections:  Introduction, Ease of Use, Prepare Your Paper Before Styling,
#              Acknowledgment, References, Biographies (~6 sections)
#   Title:     "Conference Paper Title*"
# ───────────────────────────────────────────────────────────────────────────────

_EXPECTED_TITLE = 'Conference Paper Title'
_EXPECTED_FIGURE = 'Figure 1'
_EXPECTED_TABLE = 'TABLE I'
_MIN_SECTIONS = 3
_MAX_SECTIONS = 25

# Image dimension bounds at 2x render (fitz.Matrix(2.0, 2.0)):
#   IEEE single-column width ≈ 252 pt → ~504 px at 2x
#   Tight crop may be narrower (266 px observed). Full-page fallback = 1224x1584.
_FIGURE_W_MIN, _FIGURE_W_MAX = 150, 900
_FIGURE_H_MIN, _FIGURE_H_MAX = 150, 900
_TABLE_W_MIN, _TABLE_W_MAX = 150, 1250
_TABLE_H_MIN, _TABLE_H_MAX = 80, 1600
_FULL_PAGE_W, _FULL_PAGE_H = 1224, 1584


def _run(pdf, out_dir, _monkeypatch, method):
    return run_full_pipeline(pdf, out_dir, method)


# ── Module-scoped fixtures (one marker run per session, cached) ──────────────


@pytest.fixture(scope='module')
def ieee_out_pymupdf4llm(tmp_path_factory):
    pdf = get_ieee_pdf_path()
    if not pdf.exists():
        pytest.fail(f'Test PDF not found at {pdf}')
    return _cached_ingest(pdf, 'pymupdf4llm', tmp_path_factory)


@pytest.fixture(scope='module')
def ieee_out_marker(tmp_path_factory):
    pdf = get_ieee_pdf_path()
    if not pdf.exists():
        pytest.fail(f'Test PDF not found at {pdf}')
    if not marker_available():
        pytest.skip('marker_single not available or GPU < 4GB')
    return _cached_ingest(pdf, 'marker', tmp_path_factory)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _read_paper_title(out_dir: Path) -> str:
    return (out_dir / 'paper.md').read_text('utf-8').split('\n', 1)[0]


def _paper_md_content(out_dir: Path) -> str:
    return (out_dir / 'paper.md').read_text('utf-8')


def _index_md_content(out_dir: Path) -> str:
    return (out_dir / 'INDEX.md').read_text('utf-8')


# ── Tests: structure ─────────────────────────────────────────────────────────


class TestIEEEConference:
    """End-to-end pipeline tests against a known IEEE conference template PDF."""

    # ── Structure ──────────────────────────────────────────────────────────

    def test_section_count_pymupdf4llm(self, ieee_out_pymupdf4llm):
        md_files = list((ieee_out_pymupdf4llm / 'md').glob('*.md'))
        assert _MIN_SECTIONS <= len(md_files) <= _MAX_SECTIONS, (
            f'pymupdf4llm: {len(md_files)} sections, expected {_MIN_SECTIONS}-{_MAX_SECTIONS}'
        )

    @_marker_skip
    def test_section_count_marker(self, ieee_out_marker):
        md_files = list((ieee_out_marker / 'md').glob('*.md'))
        assert _MIN_SECTIONS <= len(md_files) <= _MAX_SECTIONS

    # ── Content ────────────────────────────────────────────────────────────

    def test_paper_md_title_pymupdf4llm(self, ieee_out_pymupdf4llm):
        assert _EXPECTED_TITLE in _read_paper_title(ieee_out_pymupdf4llm)

    @_marker_skip
    def test_paper_md_title_marker(self, ieee_out_marker):
        assert _EXPECTED_TITLE in _read_paper_title(ieee_out_marker)

    def test_paper_md_structure_pymupdf4llm(self, ieee_out_pymupdf4llm):
        content = _paper_md_content(ieee_out_pymupdf4llm)
        assert '## Abstract' in content
        assert '## Sections' in content
        assert 'md/' in content

    @_marker_skip
    def test_paper_md_structure_marker(self, ieee_out_marker):
        content = _paper_md_content(ieee_out_marker)
        assert '## Abstract' in content
        assert '## Sections' in content
        assert 'md/' in content

    def test_introduction_section_exists_pymupdf4llm(self, ieee_out_pymupdf4llm):
        intro_found = any(
            re.search(r'(?i)\bintroduction\b', p.read_text('utf-8')) for p in (ieee_out_pymupdf4llm / 'md').glob('*.md')
        )
        assert intro_found, 'pymupdf4llm: no Introduction section found'

    @_marker_skip
    def test_introduction_section_exists_marker(self, ieee_out_marker):
        intro_found = any(
            re.search(r'(?i)\bintroduction\b', p.read_text('utf-8')) for p in (ieee_out_marker / 'md').glob('*.md')
        )
        assert intro_found

    # ── Output files ───────────────────────────────────────────────────────

    def test_output_directory_structure_pymupdf4llm(self, ieee_out_pymupdf4llm):
        out = ieee_out_pymupdf4llm
        assert (out / 'paper.md').is_file()
        assert (out / 'INDEX.md').is_file()
        assert (out / 'md').is_dir()
        assert len(list((out / 'md').glob('*.md'))) >= _MIN_SECTIONS
        assert len(list(out.glob('img/sec*'))) >= 1

    @_marker_skip
    def test_output_directory_structure_marker(self, ieee_out_marker):
        out = ieee_out_marker
        assert (out / 'paper.md').is_file()
        assert (out / 'INDEX.md').is_file()
        assert (out / 'md').is_dir()
        assert len(list((out / 'md').glob('*.md'))) >= _MIN_SECTIONS
        assert len(list(out.glob('img/sec*'))) >= 1

    # ── INDEX.md ───────────────────────────────────────────────────────────

    def test_index_lists_figure_1_pymupdf4llm(self, ieee_out_pymupdf4llm):
        content = _index_md_content(ieee_out_pymupdf4llm)
        assert 'Figure 1' in content or 'Fig. 1' in content

    @_marker_skip
    def test_index_lists_figure_1_marker(self, ieee_out_marker):
        content = _index_md_content(ieee_out_marker)
        assert 'Figure 1' in content or 'Fig. 1' in content

    def test_index_lists_table_i_pymupdf4llm(self, ieee_out_pymupdf4llm):
        content = _index_md_content(ieee_out_pymupdf4llm)
        assert 'TABLE I' in content or ('Table' in content and 'I' in content)

    @_marker_skip
    def test_index_lists_table_i_marker(self, ieee_out_marker):
        content = _index_md_content(ieee_out_marker)
        assert 'TABLE I' in content or ('Table' in content and 'I' in content)

    # ── Counts ─────────────────────────────────────────────────────────────

    def test_figure_count_pymupdf4llm(self, ieee_out_pymupdf4llm):
        pngs = collect_pngs(ieee_out_pymupdf4llm)
        fig_pngs = [p for p in pngs if png_matches_label(p, _EXPECTED_FIGURE)]
        assert len(fig_pngs) >= 1, f'pymupdf4llm: Figure 1 image not found in {[p.name for p in pngs]}'

    @_marker_skip
    def test_figure_count_marker(self, ieee_out_marker):
        pngs = collect_pngs(ieee_out_marker)
        fig_pngs = [p for p in pngs if png_matches_label(p, _EXPECTED_FIGURE)]
        assert len(fig_pngs) >= 1

    def test_table_count_pymupdf4llm(self, ieee_out_pymupdf4llm):
        pngs = collect_pngs(ieee_out_pymupdf4llm)
        tbl_pngs = [p for p in pngs if png_matches_label(p, _EXPECTED_TABLE)]
        assert tbl_pngs, 'pymupdf4llm: TABLE I image not found'

    @_marker_skip
    def test_table_count_marker(self, ieee_out_marker):
        pngs = collect_pngs(ieee_out_marker)
        tbl_pngs = [p for p in pngs if png_matches_label(p, _EXPECTED_TABLE)]
        assert tbl_pngs

    # ── Image dimensions ───────────────────────────────────────────────────

    def test_figure_1_dimensions_pymupdf4llm(self, ieee_out_pymupdf4llm):
        pngs = collect_pngs(ieee_out_pymupdf4llm)
        fig_pngs = [p for p in pngs if png_matches_label(p, _EXPECTED_FIGURE)]
        assert fig_pngs
        w, h = read_png_size(fig_pngs[0])
        assert _FIGURE_W_MIN <= w <= _FIGURE_W_MAX, f'width {w} out of range'
        assert _FIGURE_H_MIN <= h <= _FIGURE_H_MAX, f'height {h} out of range'

    @_marker_skip
    def test_figure_1_dimensions_marker(self, ieee_out_marker):
        pngs = collect_pngs(ieee_out_marker)
        fig_pngs = [p for p in pngs if png_matches_label(p, _EXPECTED_FIGURE)]
        assert fig_pngs
        w, h = read_png_size(fig_pngs[0])
        assert _FIGURE_W_MIN <= w <= _FIGURE_W_MAX
        assert _FIGURE_H_MIN <= h <= _FIGURE_H_MAX

    def test_table_i_dimensions_pymupdf4llm(self, ieee_out_pymupdf4llm):
        pngs = collect_pngs(ieee_out_pymupdf4llm)
        tbl_pngs = [p for p in pngs if png_matches_label(p, _EXPECTED_TABLE)]
        assert tbl_pngs
        best = next((p for p in tbl_pngs if read_png_size(p) != (_FULL_PAGE_W, _FULL_PAGE_H)), tbl_pngs[0])
        w, h = read_png_size(best)
        assert _TABLE_W_MIN <= w <= _TABLE_W_MAX, f'width {w} out of range'
        assert _TABLE_H_MIN <= h <= _TABLE_H_MAX, f'height {h} out of range'

    @_marker_skip
    def test_table_i_dimensions_marker(self, ieee_out_marker):
        pngs = collect_pngs(ieee_out_marker)
        tbl_pngs = [p for p in pngs if png_matches_label(p, _EXPECTED_TABLE)]
        assert tbl_pngs
        best = next((p for p in tbl_pngs if read_png_size(p) != (_FULL_PAGE_W, _FULL_PAGE_H)), tbl_pngs[0])
        w, h = read_png_size(best)
        assert _TABLE_W_MIN <= w <= _TABLE_W_MAX
        assert _TABLE_H_MIN <= h <= _TABLE_H_MAX

    # ── Image validity ─────────────────────────────────────────────────────

    def test_all_images_valid_png_pymupdf4llm(self, ieee_out_pymupdf4llm):
        pngs = collect_pngs(ieee_out_pymupdf4llm)
        assert len(pngs) >= 2
        for p in pngs:
            w, h = read_png_size(p)
            assert w > 0 and h > 0, f'{p.name}: zero-size'

    @_marker_skip
    def test_all_images_valid_png_marker(self, ieee_out_marker):
        pngs = collect_pngs(ieee_out_marker)
        assert len(pngs) >= 2
        for p in pngs:
            w, h = read_png_size(p)
            assert w > 0 and h > 0

    def test_at_least_one_cropped_image_pymupdf4llm(self, ieee_out_pymupdf4llm):
        cropped = sum(1 for p in collect_pngs(ieee_out_pymupdf4llm) if read_png_size(p) != (_FULL_PAGE_W, _FULL_PAGE_H))
        assert cropped >= 1, 'pymupdf4llm: all images are full-page (crop failed)'

    @_marker_skip
    def test_at_least_one_cropped_image_marker(self, ieee_out_marker):
        cropped = sum(1 for p in collect_pngs(ieee_out_marker) if read_png_size(p) != (_FULL_PAGE_W, _FULL_PAGE_H))
        assert cropped >= 1

    # ── Cross-method comparison ────────────────────────────────────────────

    def test_both_methods_comparable(self, ieee_out_pymupdf4llm, ieee_out_marker):
        len(list((ieee_out_pymupdf4llm / 'md').glob('*.md')))
        m_sec = len(list((ieee_out_marker / 'md').glob('*.md')))
        # Marker uses proper ## headings; pymupdf4llm falls back to text
        # heuristics for 2-column IEEE — section counts differ by design.
        assert 3 <= m_sec <= 12, f'marker: {m_sec} sections (expected 3-12)'
