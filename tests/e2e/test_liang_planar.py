"""E2E tests for the liang-planar-2025 paper (7-page IEEE 2-column PDF).

Ground truth:
  Title:    "Equivalent Circuit-Based Analysis of Current Sharing in Planar
             Transformer Parallel Windings"
  Sections: 6 total (01-title/abstract, 02-intro, 03-frequency, 04-circuit-model,
            05-conclusion, 06-references)
  Figures:  Fig. 1-8, 10-16  (15 figures; Fig. 9 does not exist -- numbering skip)
  Tables:   TABLE I
  Equations: (1)-(5) in sec03; (6)-(32) in sec04; (33)-(36) in sec05 (36 total)

Observed image dimensions at 2x render (fitz.Matrix(2.0,2.0)):
  figures  : w 187-528, h 141-435
  tables   : w 512, h 280
  equations: w 213-602, h 34-318

Full-page fallback: 1224x1584 (letter at 2x).
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import pytest

from tests.conftest import _marker_skip

from .conftest import (
    _cached_ingest,
    collect_pngs,
    png_matches_label,
    read_png_size,
)

# ── PDF path helper ────────────────────────────────────────────────────────────


def _get_liang_pdf() -> Path:
    return Path(__file__).resolve().parent.parent / 'data' / 'liang-planar-2025.pdf'


_liang_skip = pytest.mark.skipif(
    not _get_liang_pdf().exists(),
    reason='liang-planar-2025 PDF not available (gitignored real paper data)',
)


# ── Module-scoped ingest fixtures ──────────────────────────────────────────────


@pytest.fixture(scope='module')
def liang_out(tmp_path_factory):
    pdf = _get_liang_pdf()
    if not pdf.exists():
        pytest.skip('liang-planar-2025 PDF not available')
    return _cached_ingest(pdf, 'pymupdf4llm', tmp_path_factory)


@pytest.fixture(scope='module')
def liang_out_marker(tmp_path_factory):
    pdf = _get_liang_pdf()
    if not pdf.exists():
        pytest.skip('liang-planar-2025 PDF not available')
    return _cached_ingest(pdf, 'marker', tmp_path_factory)


# ── Ground truth ────────────────────────────────────────────────────────────────

_TITLE_KEYWORDS = ('Equivalent Circuit', 'Current Sharing', 'Planar Transformer')
_MIN_SECTIONS, _MAX_SECTIONS = 5, 10
_EXPECTED_TABLES = ['TABLE I']
_EXPECTED_FIGURES = list(range(1, 9)) + list(range(10, 17))  # 1-8, 10-16 (no 9)
_EXPECTED_EQ_SEC3 = list(range(1, 6))  # equations 1-5 in sec03
_EXPECTED_EQ_SEC4 = list(range(6, 33))  # equations 6-32 in sec04
_EXPECTED_EQ_SEC5 = list(range(33, 37))  # equations 33-36 in sec05
_FULL_PAGE = (1224, 1584)

_TOL = 30  # px tolerance for dimension checks

_FIGURE_SIZES: dict[str, tuple[int, int]] = {
    'figure-1': (525, 250),
    'figure-2': (518, 415),
    'figure-3': (528, 435),
    'figure-4': (239, 193),
    'figure-5': (483, 393),
    'figure-6': (304, 192),
    'figure-7': (187, 182),
    'figure-8': (291, 141),
    'figure-10': (506, 205),
    'figure-11': (243, 190),
    'figure-12': (355, 155),
    'figure-13': (456, 214),
    'figure-14': (447, 304),
    'figure-15': (275, 190),
    'figure-16': (279, 212),
}

_TABLE_SIZES: dict[str, tuple[int, int]] = {
    'table-i': (512, 280),
}

_EQ_SIZES: dict[str, tuple[int, int]] = {
    'equation-1': (213, 172),
    'equation-2': (301, 207),
    'equation-3': (301, 207),
    'equation-4': (324, 263),
    'equation-5': (246, 102),
    'equation-6': (327, 92),
    'equation-7': (317, 103),
    'equation-8': (368, 92),
    'equation-9': (310, 102),
    'equation-10': (348, 103),
    'equation-11': (381, 99),
    'equation-12': (394, 99),
    'equation-13': (382, 35),
    'equation-14': (237, 91),
    'equation-15': (238, 73),
    'equation-16': (275, 103),
    'equation-17': (291, 35),
    'equation-18': (506, 172),
    'equation-19': (505, 295),
    'equation-20': (521, 70),
    'equation-21': (470, 35),
    'equation-22': (418, 283),
    'equation-23': (418, 248),
    'equation-24': (424, 34),
    'equation-25': (377, 106),
    'equation-26': (520, 318),
    'equation-27': (517, 212),
    'equation-28': (274, 94),
    'equation-29': (492, 270),
    'equation-30': (427, 257),
    'equation-31': (386, 263),
    'equation-32': (295, 34),
    'equation-33': (602, 249),
    'equation-34': (270, 84),
    'equation-35': (292, 84),
    'equation-36': (409, 94),
}

# Global safety bounds
_FIG_W = (150, 1100)
_FIG_H = (80, 700)
_TBL_W = (150, 900)
_TBL_H = (50, 600)
_EQ_W = (80, 650)
_EQ_H = (20, 350)


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _section_md(out_dir: Path, prefix: str) -> Path | None:
    for p in (out_dir / 'md').glob(f'{prefix}-*.md'):
        return p
    return None


def _eq_image_line_numbers(content: str) -> dict[int, int]:
    result = {}
    for lineno, line in enumerate(content.splitlines(), 1):
        m = re.search(r'!\[Equation (\d+)\]', line)
        if m:
            result[int(m.group(1))] = lineno
    return result


# ── Tests: structure ───────────────────────────────────────────────────────────


class TestLiangStructure:
    """Section structure and paper.md content."""

    @_liang_skip
    def test_section_count_pymupdf4llm(self, liang_out):
        md_files = list((liang_out / 'md').glob('*.md'))
        assert _MIN_SECTIONS <= len(md_files) <= _MAX_SECTIONS, (
            f'pymupdf4llm: {len(md_files)} section files, expected {_MIN_SECTIONS}-{_MAX_SECTIONS}'
        )

    @_liang_skip
    @_marker_skip
    def test_section_count_marker(self, liang_out_marker):
        md_files = list((liang_out_marker / 'md').glob('*.md'))
        assert _MIN_SECTIONS <= len(md_files) <= _MAX_SECTIONS

    @_liang_skip
    def test_paper_md_title_pymupdf4llm(self, liang_out):
        title = (liang_out / 'paper.md').read_text('utf-8').split('\n', 1)[0]
        assert any(kw.lower() in title.lower() for kw in _TITLE_KEYWORDS), (
            f'pymupdf4llm: title {title!r} missing keyword'
        )

    @_liang_skip
    @_marker_skip
    def test_paper_md_title_marker(self, liang_out_marker):
        title = (liang_out_marker / 'paper.md').read_text('utf-8').split('\n', 1)[0]
        assert any(kw.lower() in title.lower() for kw in _TITLE_KEYWORDS)

    @_liang_skip
    def test_key_sections_present_pymupdf4llm(self, liang_out):
        all_text = ''.join(p.read_text('utf-8') for p in (liang_out / 'md').glob('*.md'))
        for kw in ('INTRODUCTION', 'CONCLUSION'):
            assert kw in all_text.upper(), f'pymupdf4llm: section "{kw}" not found'

    @_liang_skip
    @_marker_skip
    def test_key_sections_present_marker(self, liang_out_marker):
        all_text = ''.join(p.read_text('utf-8') for p in (liang_out_marker / 'md').glob('*.md'))
        for kw in ('INTRODUCTION', 'CONCLUSION'):
            assert kw in all_text.upper()

    @_liang_skip
    def test_index_md_has_all_figures_pymupdf4llm(self, liang_out):
        content = (liang_out / 'INDEX.md').read_text('utf-8')
        for fig_num in _EXPECTED_FIGURES:
            label = f'Figure {fig_num}'
            assert label in content, f'pymupdf4llm: {label} missing from INDEX.md'

    @_liang_skip
    def test_index_md_has_all_tables_pymupdf4llm(self, liang_out):
        content = (liang_out / 'INDEX.md').read_text('utf-8')
        for tbl in _EXPECTED_TABLES:
            assert tbl in content, f'pymupdf4llm: {tbl} missing from INDEX.md'

    @_liang_skip
    def test_no_figure_9_in_index_pymupdf4llm(self, liang_out):
        """Figure 9 does not exist in this paper — numbering skips 8→10."""
        content = (liang_out / 'INDEX.md').read_text('utf-8')
        assert 'Figure 9' not in content, 'pymupdf4llm: Figure 9 should not exist in INDEX.md'


# ── Tests: rendered images ──────────────────────────────────────────────────────


class TestLiangImages:
    """Figure, table, and equation image existence and dimension bounds."""

    @_liang_skip
    @pytest.mark.parametrize('fig_num', _EXPECTED_FIGURES)
    def test_figure_image_exists_pymupdf4llm(self, liang_out, fig_num):
        pngs = collect_pngs(liang_out)
        label = f'Figure {fig_num}'
        matches = [p for p in pngs if png_matches_label(p, label) or f'figure-{fig_num}' in p.name]
        assert matches, f'pymupdf4llm: no PNG for {label}'

    @_liang_skip
    @pytest.mark.parametrize('tbl', _EXPECTED_TABLES)
    def test_table_image_exists_pymupdf4llm(self, liang_out, tbl):
        pngs = collect_pngs(liang_out)
        matches = [p for p in pngs if png_matches_label(p, tbl)]
        assert matches, f'pymupdf4llm: no PNG for {tbl}'

    @_liang_skip
    @pytest.mark.parametrize('eq_num', _EXPECTED_EQ_SEC3)
    def test_equation_image_exists_in_sec03_pymupdf4llm(self, liang_out, eq_num):
        img_dir = liang_out / 'img' / 'sec03'
        label = f'equation-{eq_num}'
        matches = [p for p in img_dir.glob('*.png') if f'-{label}' in p.name] if img_dir.exists() else []
        assert matches, f'pymupdf4llm: no image for Equation {eq_num} in sec03/'

    @_liang_skip
    @pytest.mark.parametrize('eq_num', _EXPECTED_EQ_SEC4)
    def test_equation_image_exists_in_sec04_pymupdf4llm(self, liang_out, eq_num):
        img_dir = liang_out / 'img' / 'sec04'
        label = f'equation-{eq_num}'
        matches = [p for p in img_dir.glob('*.png') if f'-{label}' in p.name] if img_dir.exists() else []
        assert matches, f'pymupdf4llm: no image for Equation {eq_num} in sec04/'

    @_liang_skip
    @pytest.mark.parametrize('eq_num', _EXPECTED_EQ_SEC5)
    def test_equation_image_exists_in_sec05_pymupdf4llm(self, liang_out, eq_num):
        img_dir = liang_out / 'img' / 'sec05'
        label = f'equation-{eq_num}'
        matches = [p for p in img_dir.glob('*.png') if f'-{label}' in p.name] if img_dir.exists() else []
        assert matches, f'pymupdf4llm: no image for Equation {eq_num} in sec05/'

    @_liang_skip
    @pytest.mark.parametrize('slug', list(_FIGURE_SIZES.keys()))
    def test_figure_dimensions_pymupdf4llm(self, liang_out, slug):
        exp_w, exp_h = _FIGURE_SIZES[slug]
        matches = [p for p in collect_pngs(liang_out) if f'-{slug}' in p.name]
        assert matches, f'pymupdf4llm: no PNG matching slug "{slug}"'
        w, h = read_png_size(matches[0])
        assert abs(w - exp_w) <= _TOL, f'pymupdf4llm {slug}: width {w} != expected {exp_w} (+/-{_TOL})'
        assert abs(h - exp_h) <= _TOL, f'pymupdf4llm {slug}: height {h} != expected {exp_h} (+/-{_TOL})'

    @_liang_skip
    @pytest.mark.parametrize(('slug', 'exp'), list(_TABLE_SIZES.items()))
    def test_table_dimensions_pymupdf4llm(self, liang_out, slug, exp):
        exp_w, exp_h = exp
        matches = [p for p in collect_pngs(liang_out) if f'-{slug}' in p.name]
        assert matches, f'pymupdf4llm: no PNG matching slug "{slug}"'
        w, h = read_png_size(matches[0])
        assert abs(w - exp_w) <= _TOL, f'pymupdf4llm {slug}: width {w} != expected {exp_w} (+/-{_TOL})'
        assert abs(h - exp_h) <= _TOL, f'pymupdf4llm {slug}: height {h} != expected {exp_h} (+/-{_TOL})'

    @_liang_skip
    @pytest.mark.parametrize(('slug', 'exp'), list(_EQ_SIZES.items()))
    def test_equation_dimensions_pymupdf4llm(self, liang_out, slug, exp):
        exp_w, exp_h = exp
        all_pngs = list((liang_out / 'img').rglob(f'*-{slug}.png'))
        assert all_pngs, f'pymupdf4llm: no PNG matching slug "{slug}"'
        w, h = read_png_size(all_pngs[0])
        assert (w, h) != _FULL_PAGE, f'pymupdf4llm {slug}: full-page fallback used ({w}x{h})'
        assert abs(w - exp_w) <= _TOL, f'pymupdf4llm {slug}: width {w} != expected {exp_w} (+/-{_TOL})'
        assert abs(h - exp_h) <= _TOL, f'pymupdf4llm {slug}: height {h} != expected {exp_h} (+/-{_TOL})'

    @_liang_skip
    def test_no_full_page_fallback_pymupdf4llm(self, liang_out):
        """No image should be full-page fallback (1224x1584)."""
        for p in collect_pngs(liang_out):
            w, h = read_png_size(p)
            assert (w, h) != _FULL_PAGE, f'{p.name}: full-page fallback ({w}x{h})'

    # ── Marker variants ──────────────────────────────────────────────────────

    @_liang_skip
    @_marker_skip
    @pytest.mark.parametrize('slug', list(_FIGURE_SIZES.keys()))
    def test_figure_dimensions_marker(self, liang_out_marker, slug):
        exp_w, exp_h = _FIGURE_SIZES[slug]
        matches = [p for p in collect_pngs(liang_out_marker) if f'-{slug}' in p.name]
        assert matches, f'marker: no PNG matching slug "{slug}"'
        w, h = read_png_size(matches[0])
        assert abs(w - exp_w) <= _TOL, f'marker {slug}: width {w} != {exp_w} (+/-{_TOL})'
        assert abs(h - exp_h) <= _TOL, f'marker {slug}: height {h} != {exp_h} (+/-{_TOL})'

    @_liang_skip
    @_marker_skip
    def test_no_full_page_fallback_marker(self, liang_out_marker):
        for p in collect_pngs(liang_out_marker):
            w, h = read_png_size(p)
            assert (w, h) != _FULL_PAGE, f'marker {p.name}: full-page fallback ({w}x{h})'


# ── Tests: inline equation links in markdown ────────────────────────────────────


class TestLiangEquationLinks:
    """Equations must be linked inline in section markdown with correct ordering."""

    @_liang_skip
    def test_equations_1_to_5_inline_in_section03_pymupdf4llm(self, liang_out):
        sec3 = _section_md(liang_out, '03')
        assert sec3, 'pymupdf4llm: section 03 md file not found'
        content = sec3.read_text('utf-8')
        eq_lines = _eq_image_line_numbers(content)
        missing = [n for n in _EXPECTED_EQ_SEC3 if n not in eq_lines]
        assert not missing, f'pymupdf4llm: equations {missing} not found as inline images in {sec3.name}'

    @_liang_skip
    def test_equations_6_to_32_inline_in_section04_pymupdf4llm(self, liang_out):
        sec4 = _section_md(liang_out, '04')
        assert sec4, 'pymupdf4llm: section 04 md file not found'
        content = sec4.read_text('utf-8')
        eq_lines = _eq_image_line_numbers(content)
        found = [n for n in _EXPECTED_EQ_SEC4 if n in eq_lines]
        assert len(found) >= 20, f'pymupdf4llm: only {len(found)}/27 equations inline in section 04'

    @_liang_skip
    def test_equations_33_to_36_inline_in_section05_pymupdf4llm(self, liang_out):
        sec5 = _section_md(liang_out, '05')
        assert sec5, 'pymupdf4llm: section 05 md file not found'
        content = sec5.read_text('utf-8')
        eq_lines = _eq_image_line_numbers(content)
        found = [n for n in _EXPECTED_EQ_SEC5 if n in eq_lines]
        assert len(found) >= 2, f'pymupdf4llm: only {len(found)}/4 equations inline in section 05'

    @_liang_skip
    def test_equation_order_ascending_in_section03_pymupdf4llm(self, liang_out):
        sec3 = _section_md(liang_out, '03')
        assert sec3
        content = sec3.read_text('utf-8')
        eq_lines = _eq_image_line_numbers(content)
        present = sorted(n for n in _EXPECTED_EQ_SEC3 if n in eq_lines)
        for a, b in itertools.pairwise(present):
            assert eq_lines[a] < eq_lines[b], (
                f'pymupdf4llm: Equation {a} (line {eq_lines[a]}) after Equation {b} (line {eq_lines[b]}) — wrong order'
            )

    @_liang_skip
    def test_equation_order_ascending_in_section04_pymupdf4llm(self, liang_out):
        sec4 = _section_md(liang_out, '04')
        assert sec4
        content = sec4.read_text('utf-8')
        eq_lines = _eq_image_line_numbers(content)
        present = sorted(n for n in _EXPECTED_EQ_SEC4 if n in eq_lines)
        for a, b in itertools.pairwise(present):
            assert eq_lines[a] < eq_lines[b], (
                f'pymupdf4llm: Equation {a} (line {eq_lines[a]}) after Equation {b} (line {eq_lines[b]}) — wrong order'
            )

    @_liang_skip
    def test_no_figure_9_image_pymupdf4llm(self, liang_out):
        """Figure 9 should not be rendered — it does not exist in the paper."""
        all_pngs = collect_pngs(liang_out)
        fig9 = [p for p in all_pngs if 'figure-9' in p.name.lower()]
        assert not fig9, f'pymupdf4llm: Unexpected Figure 9 image: {[p.name for p in fig9]}'
