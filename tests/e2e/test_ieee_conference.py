"""E2E tests for the IEEE conference template PDF (ieee-conference.tex ground truth)."""
import re
import tempfile
from pathlib import Path

import pytest

from ..conftest import _marker_skip, marker_available
from .conftest import collect_pngs, get_ieee_pdf_path, png_matches_label, read_png_size, run_full_pipeline

# ── Ground truth from ieee-conference.tex ─────────────────────────────────────
#   1 figure:  Figure 1 — "Example of a figure caption."  (fig1.png, 341×297 px)
#   1 table:   Table I  — "Table Type Styles" (4 columns)
#   1 equation: Equation (1) — a+b=γ
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
#   Tight crop may be narrower (266 px observed). Full-page fallback = 1224×1584.
_FIGURE_W_MIN, _FIGURE_W_MAX = 150, 900
_FIGURE_H_MIN, _FIGURE_H_MAX = 150, 900
_TABLE_W_MIN, _TABLE_W_MAX = 150, 1250
_TABLE_H_MIN, _TABLE_H_MAX = 80, 1600
_FULL_PAGE_W, _FULL_PAGE_H = 1224, 1584


def _run(pdf, out_dir, _monkeypatch, method):
    return run_full_pipeline(pdf, out_dir, method)


class TestIEEEConference:
    """End-to-end pipeline tests against a known IEEE conference template PDF."""

    @pytest.fixture
    def pdf(self):
        p = get_ieee_pdf_path()
        if not p.exists():
            pytest.fail(f'Test PDF not found at {p}')
        return p

    @pytest.fixture
    def out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    # ── Structure ──────────────────────────────────────────────────────────

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_section_count(self, pdf, out_dir, monkeypatch, method):
        _, n_sec, _, _ = _run(pdf, out_dir, monkeypatch, method)
        assert _MIN_SECTIONS <= n_sec <= _MAX_SECTIONS, (
            f'{method}: expected {_MIN_SECTIONS}–{_MAX_SECTIONS} sections, got {n_sec}'
        )

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_figure_count(self, pdf, out_dir, monkeypatch, method):
        _, _, n_fig, _ = _run(pdf, out_dir, monkeypatch, method)
        assert n_fig == 1, f'{method}: expected exactly 1 figure, got {n_fig}'

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_table_count(self, pdf, out_dir, monkeypatch, method):
        _, _, _, n_tbl = _run(pdf, out_dir, monkeypatch, method)
        assert n_tbl >= 1, f'{method}: expected at least 1 table, got {n_tbl}'

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_output_directory_structure(self, pdf, out_dir, monkeypatch, method):
        _run(pdf, out_dir, monkeypatch, method)
        assert (out_dir / 'paper.md').is_file()
        assert (out_dir / 'INDEX.md').is_file()
        assert (out_dir / 'md').is_dir()
        assert len(list((out_dir / 'md').glob('*.md'))) >= _MIN_SECTIONS
        assert len(list(out_dir.glob('img/sec*'))) >= 1

    # ── Content ────────────────────────────────────────────────────────────

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_paper_md_title(self, pdf, out_dir, monkeypatch, method):
        _run(pdf, out_dir, monkeypatch, method)
        title_line = (out_dir / 'paper.md').read_text('utf-8').split('\n', 1)[0]
        assert _EXPECTED_TITLE in title_line

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_paper_md_structure(self, pdf, out_dir, monkeypatch, method):
        _run(pdf, out_dir, monkeypatch, method)
        content = (out_dir / 'paper.md').read_text('utf-8')
        assert '## Abstract' in content
        assert '## Sections' in content
        assert 'md/' in content

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_introduction_section_exists(self, pdf, out_dir, monkeypatch, method):
        _run(pdf, out_dir, monkeypatch, method)
        intro_found = any(
            re.search(r'(?i)\bintroduction\b', p.read_text('utf-8'))
            for p in (out_dir / 'md').glob('*.md')
        )
        assert intro_found, f'{method}: no Introduction section found'

    # ── INDEX.md ───────────────────────────────────────────────────────────

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_index_lists_figure_1(self, pdf, out_dir, monkeypatch, method):
        _run(pdf, out_dir, monkeypatch, method)
        content = (out_dir / 'INDEX.md').read_text('utf-8')
        assert 'Figure 1' in content or 'Fig. 1' in content

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_index_lists_table_i(self, pdf, out_dir, monkeypatch, method):
        _run(pdf, out_dir, monkeypatch, method)
        content = (out_dir / 'INDEX.md').read_text('utf-8')
        assert 'TABLE I' in content or ('Table' in content and 'I' in content)

    # ── Image files and dimensions ─────────────────────────────────────────

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_figure_1_image_exists_and_dimensions(self, pdf, out_dir, monkeypatch, method):
        _run(pdf, out_dir, monkeypatch, method)
        pngs = collect_pngs(out_dir)
        fig_pngs = [p for p in pngs if png_matches_label(p, _EXPECTED_FIGURE)]
        assert len(fig_pngs) == 1, f'{method}: expected 1 Figure 1 image, found {[p.name for p in pngs]}'
        w, h = read_png_size(fig_pngs[0])
        assert _FIGURE_W_MIN <= w <= _FIGURE_W_MAX, f'width {w} out of range'
        assert _FIGURE_H_MIN <= h <= _FIGURE_H_MAX, f'height {h} out of range'

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_table_i_image_exists_and_dimensions(self, pdf, out_dir, monkeypatch, method):
        _run(pdf, out_dir, monkeypatch, method)
        pngs = collect_pngs(out_dir)
        tbl_pngs = [p for p in pngs if png_matches_label(p, _EXPECTED_TABLE)]
        assert tbl_pngs, f'{method}: Table I image not found'
        # prefer non-full-page render
        best = next((p for p in tbl_pngs if read_png_size(p) != (_FULL_PAGE_W, _FULL_PAGE_H)), tbl_pngs[0])
        w, h = read_png_size(best)
        assert _TABLE_W_MIN <= w <= _TABLE_W_MAX, f'width {w} out of range'
        assert _TABLE_H_MIN <= h <= _TABLE_H_MAX, f'height {h} out of range'

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_all_images_valid_png_and_nonzero(self, pdf, out_dir, monkeypatch, method):
        _run(pdf, out_dir, monkeypatch, method)
        pngs = collect_pngs(out_dir)
        assert len(pngs) >= 2
        for p in pngs:
            w, h = read_png_size(p)
            assert w > 0 and h > 0, f'{p.name}: zero-size'

    @pytest.mark.parametrize('method', [
        pytest.param('pymupdf4llm'),
        pytest.param('marker', marks=[_marker_skip]),
    ])
    def test_at_least_one_cropped_image(self, pdf, out_dir, monkeypatch, method):
        _run(pdf, out_dir, monkeypatch, method)
        cropped = sum(
            1 for p in collect_pngs(out_dir)
            if read_png_size(p) != (_FULL_PAGE_W, _FULL_PAGE_H)
        )
        assert cropped >= 1, f'{method}: all images are full-page (crop failed)'

    # ── Cross-method comparison ────────────────────────────────────────────

    def test_both_methods_comparable(self, pdf, monkeypatch):
        results: dict[str, tuple[int, int, int]] = {}
        with tempfile.TemporaryDirectory() as tmp:
            _, n_sec, n_fig, n_tbl = _run(pdf, Path(tmp), monkeypatch, 'pymupdf4llm')
            results['pymupdf4llm'] = (n_sec, n_fig, n_tbl)
            assert n_fig == 1
            assert n_tbl >= 1

        if marker_available():
            with tempfile.TemporaryDirectory() as tmp:
                _, n_sec, n_fig, n_tbl = _run(pdf, Path(tmp), monkeypatch, 'marker')
                results['marker'] = (n_sec, n_fig, n_tbl)
            p_sec = results['pymupdf4llm'][0]
            m_sec = results['marker'][0]
            assert abs(p_sec - m_sec) <= 2, f'Section counts diverge: pymupdf4llm={p_sec}, marker={m_sec}'
            assert n_fig == 1
            assert n_tbl >= 1
