"""Label → page and page → section mapping utilities."""
from __future__ import annotations

import re
from pathlib import Path

import fitz

from ..utils import RN_PATTERN as _RN
FIG_TABLE_RE = re.compile(rf'(Figure\s+\d+|Fig\.\s*\d+|Table\s+(?:\d+|{_RN}))', re.IGNORECASE)


def build_figure_page_map(pdf_path: Path) -> dict[str, int]:
    """Return dict mapping normalized figure/table labels to 0-based page numbers.

    Prioritises the page whose caption block is most compact (shortest height).
    True caption blocks are 1-2 lines tall; body-text cross-references like
    "…results shown in Fig. 14. In comparison, …" are in tall paragraph blocks.
    Falls back to the first mention page when no caption block is found.
    """
    # Per-label: (min_caption_height, page_num)
    caption_candidates: dict[str, tuple[float, int]] = {}
    mention_pages: dict[str, int] = {}
    doc = fitz.open(str(pdf_path))
    for page_num in range(len(doc)):
        blocks = doc[page_num].get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']
        for blk in blocks:
            if blk['type'] != 0:
                continue
            blk_text = ''.join(
                span.get('text', '') for line in blk.get('lines', []) for span in line.get('spans', [])
            )
            if len(blk_text) > 350:
                continue
            blk_height = blk['bbox'][3] - blk['bbox'][1]
            for m in FIG_TABLE_RE.finditer(blk_text):
                label = re.sub(r'\s+', ' ', m.group(1)).strip()
                normalized = re.sub(r'(?i)^Fig\.\s*', 'Figure ', label)
                # Caption: "label." must appear in the block text
                is_caption = bool(
                    re.search(re.escape(label) + r'\.', blk_text, re.IGNORECASE)
                )
                if is_caption:
                    prev = caption_candidates.get(normalized)
                    if prev is None or blk_height < prev[0]:
                        caption_candidates[normalized] = (blk_height, page_num)
                if normalized not in mention_pages:
                    mention_pages[normalized] = page_num
    doc.close()
    result = dict(mention_pages)
    result.update({norm: page for norm, (_, page) in caption_candidates.items()})
    return result


def build_page_section_map(
    figure_page_map: dict[str, int],
    body_sections: list[tuple[str, str]],
    pdf_path: Path | None = None,
) -> dict[int, int]:
    """Map page number -> 1-based section index based on where figure captions appear.

    A figure caption (label + period, e.g. "Fig. 2.") indicates the section
    that *owns* that figure's page.  Plain mentions ("Fig. 2") are
    cross-references and do not confer ownership.

    If *pdf_path* is provided, also scans each PDF page for section headings
    from *body_sections* and propagates ownership to all pages between the
    first and last mapped page.  This ensures equation-only pages and other
    pages without figure captions still receive correct section assignment.
    """
    page_to_section: dict[int, int] = {}
    for idx, (_heading, body) in enumerate(body_sections, 1):
        for fig_label, page_num in figure_page_map.items():
            if page_num in page_to_section:
                continue
            if re.compile(re.escape(fig_label) + r'\.', re.IGNORECASE).search(body):
                page_to_section[page_num] = idx

    # Detect section heading pages from the PDF to cover pages without figure
    # captions.  This is essential for 2-column IEEE papers where section
    # boundaries may fall on pages that have no figure/table captions.
    if pdf_path:
        doc = fitz.open(str(pdf_path))
        seen_pages = set(page_to_section)
        for idx, (_heading, body) in enumerate(body_sections, 1):
            if idx in page_to_section.values():
                continue  # already owns a page via caption
            heading_text = re.sub(r'^#+\s*', '', _heading).strip()
            if not heading_text:
                continue
            # Match numbered section headings (Roman numerals) to avoid false
            # positives from short subsection letters (A., B., etc.).
            m = re.match(r'^(I{1,3}V?|IV|V|VI{0,3})\.', heading_text)
            if not m:
                continue
            numeral = m.group(1)
            for page_num in range(len(doc)):
                if page_num in seen_pages:
                    continue
                page_text = doc[page_num].get_text('text')
                if re.search(rf'\b{re.escape(numeral)}\.\s+[A-Z]', page_text):
                    page_to_section[page_num] = idx
                    seen_pages.add(page_num)
                    break
        doc.close()

    # Fill unmapped pages by forward propagation: each unmapped page inherits
    # the section of the nearest lower-numbered mapped page.
    if page_to_section:
        sorted_pages = sorted(page_to_section)
        last_sec = page_to_section[sorted_pages[0]]
        for page in range(sorted_pages[0], sorted_pages[-1] + 1):
            ps = page_to_section.get(page)
            if ps is not None:
                last_sec = ps
            else:
                page_to_section[page] = last_sec

    return page_to_section
def build_equation_page_map(pdf_path: Path) -> dict[str, int]:
    """Map equation numbers like 'Equation (2)' to 0-based pages.

    Scans for parenthesized equation numbers near the right margin (IEEE
    convention) and also at the end of text lines (pymupdf4llm style).
    """
    eq_pages: dict[str, int] = {}
    doc = fitz.open(str(pdf_path))
    page_width = doc[0].rect.width
    for page_num in range(len(doc)):
        blocks = doc[page_num].get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']
        for blk in blocks:
            if blk['type'] != 0:
                continue
            blk_text = ''.join(
                span.get('text', '') for line in blk.get('lines', []) for span in line.get('spans', [])
            ).strip()
            bbox = blk['bbox']

            # Standalone equation number at column right margin: "(1)", "(12)"
            # Left column right edge ≈ 0.40-0.47×width; right column ≈ 0.87-0.97×width
            m = re.match(r'^\((\d+)\)$', blk_text)
            if m and bbox[0] > page_width * 0.35:
                key = f'Equation {m.group(1)}'
                if key not in eq_pages:
                    eq_pages[key] = page_num
                continue

            # Equation number at end of line (pymupdf4llm style): "...= result (5)"
            # Use x1 (right edge) > 40% page width to accept both left- and right-column equations
            m = re.search(r'\((\d+)\)\s*$', blk_text)
            if m and bbox[2] > page_width * 0.40:
                key = f'Equation {m.group(1)}'
                if key not in eq_pages:
                    eq_pages[key] = page_num

            # Per-line scan: catch (N) on its own line inside a multi-line prose block
            # (e.g. "...as:\n[formula chars]\n(1)\nwhere ...") — the block-level checks above
            # would not match because blk_text contains surrounding prose.
            for line in blk.get('lines', []):
                line_text = ''.join(
                    s.get('text', '') for s in line.get('spans', [])
                ).strip()
                line_bbox = line['bbox']
                m_line = re.match(r'^\((\d+)\)$', line_text)
                if m_line and line_bbox[0] > page_width * 0.35:
                    key = f'Equation {m_line.group(1)}'
                    if key not in eq_pages:
                        eq_pages[key] = page_num
    doc.close()
    return eq_pages
