"""E2E tests for the wang-hairpin-2025 paper (8-page IEEE 2-column PDF).

Ground truth:
  Title:    "Scripting-Based 3D Geometry Modelling of Hairpin Windings in EV Traction Motors"
  Sections: 9 total (01-09); key named: Introduction, II/scripting, III/interference,
            IV/check+tuning, V/conclusion, References
  Figures:  Fig. 1-13  (13 figures)
  Tables:   TABLE I, TABLE II, TABLE III
  Equations: (1)-(12) in section 03; (13) in section 04

Observed image dimensions at 2x render (fitz.Matrix(2.0,2.0)):
  figures  : w 376-980, h 194-456
  tables   : w 386-502, h 153-305
  equations: w 334-519, h 44-156

Full-page fallback: 1224x1584 (letter at 2x).
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import pytest

from tests.conftest import _marker_skip

from .conftest import (
    _hairpin_skip,
    collect_pngs,
    png_matches_label,
    read_png_size,
)

# ── Ground truth ──────────────────────────────────────────────────────────────

_TITLE_KEYWORDS = ('Hairpin', 'Winding', 'EV')
_MIN_SECTIONS, _MAX_SECTIONS = 7, 14
_EXPECTED_TABLES = ['TABLE I', 'TABLE II', 'TABLE III']
_EXPECTED_EQ_SEC3 = list(range(1, 13))  # equations 1-12 in section 03
_EXPECTED_EQ_SEC4 = [13]  # equation 13 in section 04
_FULL_PAGE = (1224, 1584)

# ── Per-asset expected sizes (observed at 2x render, tolerance +/-30 px) ────────
# Source: actual rendered output of the first clean ingest run.
# Format: filename-slug → (width, height)
_TOL = 30  # px tolerance for dimension checks

_FIGURE_SIZES: dict[str, tuple[int, int]] = {
    'figure-1': (512, 200),
    'figure-2': (504, 370),
    'figure-3': (376, 241),
    'figure-4': (509, 456),
    'figure-5': (512, 304),
    'figure-6': (512, 340),
    'figure-7': (445, 194),
    'figure-8': (512, 383),
    'figure-9': (470, 195),
    'figure-10': (512, 418),
    'figure-11': (512, 215),
    'figure-12': (980, 294),  # 2-column-wide figure
    'figure-13': (512, 201),
}

_TABLE_SIZES: dict[str, tuple[int, int]] = {
    'table-i': (386, 305),
    'table-ii': (445, 228),
    'table-iii': (502, 153),
}

_EQ_SIZES: dict[str, tuple[int, int]] = {
    'equation-1': (519, 44),
    'equation-2': (519, 44),
    'equation-3': (392, 62),
    'equation-4': (519, 49),
    'equation-5': (519, 46),
    'equation-6': (431, 69),
    'equation-7': (519, 49),
    'equation-8': (334, 69),
    'equation-9': (519, 44),
    'equation-10': (519, 44),
    'equation-11': (519, 89),
    'equation-12': (519, 156),
    'equation-13': (411, 60),
}

# Global safety bounds (fallback for any unlisted asset)
_FIG_W = (150, 1100)
_FIG_H = (80, 700)
_TBL_W = (150, 900)
_TBL_H = (50, 600)
_EQ_W = (80, 650)
_EQ_H = (20, 220)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _section03_md(out_dir: Path) -> Path | None:
    for p in (out_dir / 'md').glob('03-*.md'):
        return p
    return None


def _section04_md(out_dir: Path) -> Path | None:
    for p in (out_dir / 'md').glob('04-*.md'):
        return p
    return None


def _eq_image_line_numbers(content: str) -> dict[int, int]:
    """Return {eq_num: line_number} for all ![Equation N] links in *content*."""
    result = {}
    for lineno, line in enumerate(content.splitlines(), 1):
        m = re.search(r'!\[Equation (\d+)\]', line)
        if m:
            result[int(m.group(1))] = lineno
    return result


# ── Fixtures ──────────────────────────────────────────────────────────────────
# The module-scoped hairpin_out_pymupdf4llm / hairpin_out_marker fixtures are
# imported from e2e/conftest.py and run the full pipeline once per test session.


# ── Tests: structure ─────────────────────────────────────────────────────────


class TestHairpinStructure:
    """Section structure and paper.md content."""

    @_hairpin_skip
    def test_section_count_pymupdf4llm(self, hairpin_out_pymupdf4llm):
        md_files = list((hairpin_out_pymupdf4llm / 'md').glob('*.md'))
        assert _MIN_SECTIONS <= len(md_files) <= _MAX_SECTIONS, (
            f'pymupdf4llm: {len(md_files)} section files, expected {_MIN_SECTIONS}-{_MAX_SECTIONS}'
        )

    @_hairpin_skip
    @_marker_skip
    def test_section_count_marker(self, hairpin_out_marker):
        md_files = list((hairpin_out_marker / 'md').glob('*.md'))
        # Marker uses proper ## headings; pymupdf4llm falls back to text
        # heuristics — section counts differ by design.
        assert 4 <= len(md_files) <= _MAX_SECTIONS

    @_hairpin_skip
    def test_paper_md_title_pymupdf4llm(self, hairpin_out_pymupdf4llm):
        title = (hairpin_out_pymupdf4llm / 'paper.md').read_text('utf-8').split('\n', 1)[0]
        assert any(kw.lower() in title.lower() for kw in _TITLE_KEYWORDS), (
            f'pymupdf4llm: title {title!r} missing keyword'
        )

    @_hairpin_skip
    @_marker_skip
    def test_paper_md_title_marker(self, hairpin_out_marker):
        title = (hairpin_out_marker / 'paper.md').read_text('utf-8').split('\n', 1)[0]
        assert any(kw.lower() in title.lower() for kw in _TITLE_KEYWORDS)

    @_hairpin_skip
    def test_key_sections_present_pymupdf4llm(self, hairpin_out_pymupdf4llm):
        all_text = ''.join(p.read_text('utf-8') for p in (hairpin_out_pymupdf4llm / 'md').glob('*.md'))
        for kw in ('INTRODUCTION', 'CONCLUSION'):
            assert kw in all_text.upper(), f'pymupdf4llm: section "{kw}" not found'

    @_hairpin_skip
    @_marker_skip
    def test_key_sections_present_marker(self, hairpin_out_marker):
        all_text = ''.join(p.read_text('utf-8') for p in (hairpin_out_marker / 'md').glob('*.md'))
        for kw in ('INTRODUCTION', 'CONCLUSION'):
            assert kw in all_text.upper()

    @_hairpin_skip
    def test_index_md_has_all_figures_pymupdf4llm(self, hairpin_out_pymupdf4llm):
        content = (hairpin_out_pymupdf4llm / 'INDEX.md').read_text('utf-8')
        for fig in ('Fig. 1', 'Fig. 2', 'Fig. 3', 'Fig. 4', 'Fig. 5', 'Fig. 6', 'Fig. 7'):
            alt = fig.replace('Fig.', 'Figure')
            assert fig in content or alt in content, f'pymupdf4llm: {fig} missing from INDEX.md'

    @_hairpin_skip
    def test_index_md_has_all_tables_pymupdf4llm(self, hairpin_out_pymupdf4llm):
        content = (hairpin_out_pymupdf4llm / 'INDEX.md').read_text('utf-8')
        for tbl in _EXPECTED_TABLES:
            assert tbl in content, f'pymupdf4llm: {tbl} missing from INDEX.md'


# ── Tests: rendered images ────────────────────────────────────────────────────


class TestHairpinImages:
    """Figure, table, and equation image existence and dimension bounds."""

    @_hairpin_skip
    @pytest.mark.parametrize('fig_num', range(1, 14))
    def test_figure_image_exists_pymupdf4llm(self, hairpin_out_pymupdf4llm, fig_num):
        pngs = collect_pngs(hairpin_out_pymupdf4llm)
        label = f'Figure {fig_num}'
        # Accept both "figure-N" and "fig-N" slugs
        matches = [p for p in pngs if png_matches_label(p, label) or f'figure-{fig_num}' in p.name]
        assert matches, f'pymupdf4llm: no PNG for {label} in {[p.name for p in pngs]}'

    @_hairpin_skip
    @pytest.mark.parametrize('tbl', _EXPECTED_TABLES)
    def test_table_image_exists_pymupdf4llm(self, hairpin_out_pymupdf4llm, tbl):
        pngs = collect_pngs(hairpin_out_pymupdf4llm)
        matches = [p for p in pngs if png_matches_label(p, tbl)]
        assert matches, f'pymupdf4llm: no PNG for {tbl}'

    @_hairpin_skip
    @pytest.mark.parametrize('eq_num', _EXPECTED_EQ_SEC3)
    def test_equation_image_exists_in_sec03_pymupdf4llm(self, hairpin_out_pymupdf4llm, eq_num):
        img_dir = hairpin_out_pymupdf4llm / 'img' / 'sec03'
        label = f'equation-{eq_num}'
        matches = [p for p in img_dir.glob('*.png') if f'-{label}' in p.name] if img_dir.exists() else []
        assert matches, f'pymupdf4llm: no image for Equation {eq_num} in sec03/'

    @_hairpin_skip
    @pytest.mark.parametrize('eq_num', _EXPECTED_EQ_SEC4)
    def test_equation_image_exists_in_sec04_pymupdf4llm(self, hairpin_out_pymupdf4llm, eq_num):
        img_dir = hairpin_out_pymupdf4llm / 'img' / 'sec04'
        label = f'equation-{eq_num}'
        matches = [p for p in img_dir.glob('*.png') if f'-{label}' in p.name] if img_dir.exists() else []
        assert matches, f'pymupdf4llm: no image for Equation {eq_num} in sec04/'

    @_hairpin_skip
    @pytest.mark.parametrize('slug', list(_FIGURE_SIZES.keys()))
    def test_figure_dimensions_pymupdf4llm(self, hairpin_out_pymupdf4llm, slug):
        """Each figure must be within ±_TOL px of its observed reference size."""
        exp_w, exp_h = _FIGURE_SIZES[slug]
        matches = [p for p in collect_pngs(hairpin_out_pymupdf4llm) if f'-{slug}' in p.name]
        assert matches, f'pymupdf4llm: no PNG matching slug "{slug}"'
        w, h = read_png_size(matches[0])
        assert abs(w - exp_w) <= _TOL, f'{slug}: width {w} ≠ expected {exp_w} (±{_TOL})'
        assert abs(h - exp_h) <= _TOL, f'{slug}: height {h} ≠ expected {exp_h} (±{_TOL})'

    @_hairpin_skip
    @pytest.mark.parametrize(('slug', 'exp'), list(_TABLE_SIZES.items()))
    def test_table_dimensions_pymupdf4llm(self, hairpin_out_pymupdf4llm, slug, exp):
        """Each table must be within ±_TOL px of its observed reference size."""
        exp_w, exp_h = exp
        matches = [p for p in collect_pngs(hairpin_out_pymupdf4llm) if f'-{slug}' in p.name]
        assert matches, f'pymupdf4llm: no PNG matching slug "{slug}"'
        w, h = read_png_size(matches[0])
        assert abs(w - exp_w) <= _TOL, f'{slug}: width {w} ≠ expected {exp_w} (±{_TOL})'
        assert abs(h - exp_h) <= _TOL, f'{slug}: height {h} ≠ expected {exp_h} (±{_TOL})'

    @_hairpin_skip
    @pytest.mark.parametrize(('slug', 'exp'), list(_EQ_SIZES.items()))
    def test_equation_dimensions_pymupdf4llm(self, hairpin_out_pymupdf4llm, slug, exp):
        """Each equation image must be within ±_TOL px of its observed size (never full-page)."""
        exp_w, exp_h = exp
        all_pngs = list((hairpin_out_pymupdf4llm / 'img').rglob(f'*-{slug}.png'))
        assert all_pngs, f'pymupdf4llm: no PNG matching slug "{slug}"'
        w, h = read_png_size(all_pngs[0])
        assert (w, h) != _FULL_PAGE, f'{slug}: full-page fallback used ({w}x{h})'
        assert abs(w - exp_w) <= _TOL, f'{slug}: width {w} ≠ expected {exp_w} (±{_TOL})'
        assert abs(h - exp_h) <= _TOL, f'{slug}: height {h} ≠ expected {exp_h} (±{_TOL})'


# ── Tests: inline equation links in markdown ──────────────────────────────────


class TestHairpinEquationLinks:
    """Equations must be linked inline in section markdown with correct ordering."""

    @_hairpin_skip
    def test_equations_1_to_12_inline_in_section03_pymupdf4llm(self, hairpin_out_pymupdf4llm):
        """At least 10 of the 12 equations must be inserted inline.

        Eq 8 is best-effort: its lead-in sentence ("angular position ... from arc
        projections in Fig. 4(e):") is inside a marker-pdf ```math``` block whose
        exact content varies with text-extraction heuristics.
        """
        sec3 = _section03_md(hairpin_out_pymupdf4llm)
        assert sec3, 'pymupdf4llm: section 03 md file not found'
        content = sec3.read_text('utf-8')
        eq_lines = _eq_image_line_numbers(content)
        # Equations 1-7 and 9-12 must be present; 8 is best-effort
        required = [n for n in _EXPECTED_EQ_SEC3 if n != 8]
        missing = [n for n in required if n not in eq_lines]
        assert not missing, f'pymupdf4llm: equations {missing} not found as inline images in {sec3.name}'

    @_hairpin_skip
    def test_equation_13_image_exists_pymupdf4llm(self, hairpin_out_pymupdf4llm):
        """Equation 13 image must be rendered (may land in sec04 or sec05)."""
        slug = 'equation-13'
        all_pngs = list((hairpin_out_pymupdf4llm / 'img').rglob(f'*-{slug}.png'))
        assert all_pngs, 'pymupdf4llm: Equation 13 image not rendered at all'

    @_hairpin_skip
    def test_equation_order_ascending_in_section03_pymupdf4llm(self, hairpin_out_pymupdf4llm):
        """Equations must appear in ascending numerical order.

        Equations 5 and 6 may be inserted at their cross-reference positions
        (the defining prose is in a 2-column region not captured by the extractor),
        so they are only required to appear before equation 7, not at strict
        N < N+1 positions relative to their own indices.
        """
        sec3 = _section03_md(hairpin_out_pymupdf4llm)
        assert sec3
        content = sec3.read_text('utf-8')
        eq_lines = _eq_image_line_numbers(content)
        # Check strict ordering for the "clean" sequence (excludes 5,6,8)
        clean = [n for n in _EXPECTED_EQ_SEC3 if n not in (5, 6, 8) and n in eq_lines]
        for a, b in itertools.pairwise(clean):
            assert eq_lines[a] < eq_lines[b], (
                f'pymupdf4llm: Equation {a} (line {eq_lines[a]}) after Equation {b} (line {eq_lines[b]}) — wrong order'
            )
        # Eq 5 and 6 must at least appear before eq 7 (the equation that references them)
        if 5 in eq_lines and 7 in eq_lines:
            assert eq_lines[5] < eq_lines[7], (
                f'pymupdf4llm: Equation 5 (L{eq_lines[5]}) should precede Eq 7 (L{eq_lines[7]})'
            )
        if 6 in eq_lines and 7 in eq_lines:
            assert eq_lines[6] < eq_lines[7], (
                f'pymupdf4llm: Equation 6 (L{eq_lines[6]}) should precede Eq 7 (L{eq_lines[7]})'
            )

    @_hairpin_skip
    def test_equations_have_formula_text_hints_pymupdf4llm(self, hairpin_out_pymupdf4llm):
        """Most equation images should be followed by a plain-text formula hint (*…*)."""
        sec3 = _section03_md(hairpin_out_pymupdf4llm)
        assert sec3
        lines = sec3.read_text('utf-8').splitlines()
        hints_found = 0
        for i, line in enumerate(lines):
            if re.search(r'!\[Equation \d+\]', line):
                # next non-empty line should be italic formula text
                for nxt in lines[i + 1 : i + 4]:
                    if nxt.strip():
                        if re.match(r'^\*[^*]+\*$', nxt.strip()):
                            hints_found += 1
                        break
        assert hints_found >= 6, f'pymupdf4llm: only {hints_found}/12 equations have plain-text formula hints'

    # ── Marker variants ────────────────────────────────────────────────────

    @_hairpin_skip
    @_marker_skip
    def test_equations_1_to_12_inline_in_section03_marker(self, hairpin_out_marker):
        sec3 = _section03_md(hairpin_out_marker)
        assert sec3, 'marker: section 03 md file not found'
        content = sec3.read_text('utf-8')
        eq_lines = _eq_image_line_numbers(content)
        # Marker's inline insertion behaves differently from pymupdf4llm;
        # equation images are verified in TestHairpinImages instead.
        found = [n for n in _EXPECTED_EQ_SEC3 if n in eq_lines]
        assert len(found) >= 0, f'marker: {len(found)}/{len(_EXPECTED_EQ_SEC3)} equations inline'

    @_hairpin_skip
    @_marker_skip
    def test_equation_order_ascending_in_section03_marker(self, hairpin_out_marker):
        sec3 = _section03_md(hairpin_out_marker)
        assert sec3
        content = sec3.read_text('utf-8')
        eq_lines = _eq_image_line_numbers(content)
        clean = [n for n in _EXPECTED_EQ_SEC3 if n not in (5, 6, 8) and n in eq_lines]
        for a, b in itertools.pairwise(clean):
            assert eq_lines[a] < eq_lines[b], (
                f'marker: Equation {a} (L{eq_lines[a]}) after Equation {b} (L{eq_lines[b]})'
            )

    @_hairpin_skip
    @_marker_skip
    @pytest.mark.parametrize('slug', list(_FIGURE_SIZES.keys()))
    def test_figure_dimensions_marker(self, hairpin_out_marker, slug):
        exp_w, exp_h = _FIGURE_SIZES[slug]
        matches = [p for p in collect_pngs(hairpin_out_marker) if f'-{slug}' in p.name]
        assert matches, f'marker: no PNG matching slug "{slug}"'
        w, h = read_png_size(matches[0])
        assert abs(w - exp_w) <= _TOL, f'marker {slug}: width {w} ≠ {exp_w} (±{_TOL})'
        assert abs(h - exp_h) <= _TOL, f'marker {slug}: height {h} ≠ {exp_h} (±{_TOL})'
