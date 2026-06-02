"""Figure and equation rendering: disk I/O, markdown insertion, cross-section fixup."""
from __future__ import annotations

import re
from pathlib import Path

import fitz

from ..utils import RN_PATTERN as _RN, slug
from ._crop import crop_equation, crop_figure, get_equation_context
from ._map import FIG_TABLE_RE, build_equation_page_map, build_figure_page_map, build_page_section_map
_CAPTION_RE = re.compile(
    rf'(?P<label>Figure\s+\d+|Fig\.\s*\d+|Table\s+(?:\d+|{_RN}))\.(?P<rest>.+)', re.IGNORECASE
)


# ── Low-level render helpers ──────────────────────────────────────────────────


def _render_one(doc: fitz.Document, page_num: int, label: str, img_path: Path, content_below: bool = False) -> None:
    if img_path.exists():
        return
    page = doc[page_num]
    crop = crop_figure(page, label, content_below=content_below)
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat, clip=crop) if crop else page.get_pixmap(matrix=mat)
    img_path.parent.mkdir(parents=True, exist_ok=True)
    pix.pil_save(str(img_path))


def _render_one_equation(doc: fitz.Document, page_num: int, eq_num: str, img_path: Path) -> None:
    if img_path.exists():
        return
    page = doc[page_num]
    crop = crop_equation(page, eq_num)
    if crop is None:
        return  # equation position not found on page; skip
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat, clip=crop)
    img_path.parent.mkdir(parents=True, exist_ok=True)
    pix.pil_save(str(img_path))


# ── Markdown insertion helpers ────────────────────────────────────────────────


def _insert_figures_inline(
    section_file: Path,
    section_idx: int,
    figure_images: dict[str, str],
    figure_page_map: dict[str, int],
    page_section_map: dict[int, int],
) -> int:
    """Insert markdown image links before each figure/table caption in *section_file*.

    Returns number of figures inserted.
    """
    content = section_file.read_text(encoding='utf-8')
    insertions: list[tuple[int, str]] = []
    seen: set[str] = set()

    for m in _CAPTION_RE.finditer(content):
        label = m.group('label')
        normalized = re.sub(r'(?i)^Fig\.\s*', 'Figure ', label)
        if normalized in seen:
            continue
        img_rel = figure_images.get(normalized)
        if img_rel is None:
            continue

        # Skip mid-sentence references ("shown in Fig. 2.")
        preceding_start = content.rfind('\n', 0, m.start()) + 1
        prefix = content[preceding_start:m.start()].strip()
        if prefix and prefix[-1].isalpha() and len(prefix.split()) >= 2:
            continue

        seen.add(normalized)
        owning = page_section_map.get(figure_page_map.get(normalized, -1), section_idx)
        img_path = f'../img/sec{owning:02d}/{Path(img_rel).name}' if owning != section_idx else f'../{img_rel}'
        insertions.append((m.start(), f'\n\n![{label}]({img_path})\n\n'))

    for pos, img_md in reversed(insertions):
        content = content[:pos] + img_md + content[pos:]

    if insertions:
        section_file.write_text(content, encoding='utf-8')
    return len(insertions)


def _insert_equations_inline(
    section_file: Path,
    section_idx: int,
    eq_page_map: dict[str, int],
    figure_images: dict[str, str],
    page_section_map: dict[int, int],
    eq_context: dict[str, tuple[str | None, str | None]] | None = None,
) -> None:
    content = section_file.read_text(encoding='utf-8')
    changed = False
    seen: set[str] = set()
    # Tracks the minimum content position for the next insertion to preserve order
    # when multiple equations share the same lead-in sentence.
    min_insert_pos = 0

    for eq_label in sorted(eq_page_map, key=lambda k: int(k.split()[-1])):
        if eq_label in seen:
            continue
        eq_num = eq_label.split()[-1]
        img_rel = figure_images.get(eq_label)
        if not img_rel:
            continue
        owning = page_section_map.get(eq_page_map[eq_label])
        img_path = (
            f'../img/sec{owning:02d}/{Path(img_rel).name}' if owning is not None and owning != section_idx
            else f'../{img_rel}'
        )

        img_name = Path(img_rel).name
        if img_name in content:
            seen.add(eq_label)
            continue

        seen.add(eq_label)

        # ── Primary: explicit (N) reference present in markdown ──────────────
        # Don't advance min_insert_pos for (N) insertions — these happen
        # in-place at the (N) marker, which can be anywhere in the document
        # (including later than lead-in insertion positions for other equations).
        m = re.search(rf'\(\s*{eq_num}\s*\)', content)
        cross_ref_m = None  # saved for last-resort fallback
        if m:
            # Distinguish definition occurrence from a cross-reference like "from (5) and (6)".
            # A definition has nothing alphabetic before (N) on the same line AND nothing after.
            nl_before = content.rfind('\n', 0, m.start())
            text_before_on_line = content[nl_before + 1: m.start()]
            nl_after = content.find('\n', m.end())
            text_after_on_line = (
                content[m.end(): nl_after].strip() if nl_after != -1 else content[m.end():].strip()
            )
            is_cross_ref = bool(text_after_on_line) or bool(re.search(r'[a-zA-Z]', text_before_on_line))
            if not is_cross_ref:
                preceding = content[max(0, m.start() - 200): m.start()]
                if not re.search(rf'!\[.*?[Ee]quation.*?{eq_num}.*?\]', preceding):
                    insertion = f'\n\n![{eq_label}]({img_path})\n\n'
                    insert_at = max(m.start(), min_insert_pos)
                    content = content[:insert_at] + insertion + content[insert_at:]
                    min_insert_pos = insert_at + len(insertion)
                    changed = True
                continue
            cross_ref_m = m  # remember for last-resort fallback below

        # ── Fallback: locate insertion by lead-in text ────────────────────────
        ctx = (eq_context or {}).get(eq_label, (None, None))
        lead_in, formula_text = ctx

        key_pos = -1
        key_len = 0
        if lead_in:
            for suffix_len in (40, 28, 16):
                key = lead_in.strip()[-suffix_len:]
                if not key:
                    continue
                # Exact match first
                p = content.lower().find(key.lower())
                if p != -1:
                    key_pos, key_len = p, len(key)
                    break
                # Regex allowing _X_ markdown italic wrappers and spacing around them
                try:
                    tokens = re.split(r'(\w+)', key)
                    pat = ''.join(
                        # Short word: allow _word_ and trailing whitespace from removed markers
                        f'_?{re.escape(t)}_?\\s*'
                        if (re.match(r'^\w{1,4}$', t) and not t.isdigit())
                        else re.escape(t)
                        for t in tokens
                    )
                    m_key = re.search(pat, content, re.IGNORECASE)
                    if m_key:
                        key_pos, key_len = m_key.start(), m_key.end() - m_key.start()
                        break
                except re.error:
                    pass

        # ── Last resort: if lead-in not found, fall back to the cross-ref (N) ─
        if key_pos == -1:
            if cross_ref_m is None:
                continue
            # Re-search since content may have been modified by earlier insertions
            m2 = re.search(rf'\(\s*{eq_num}\s*\)', content)
            if m2 is None:
                continue
            preceding = content[max(0, m2.start() - 200): m2.start()]
            if not re.search(rf'!\[.*?[Ee]quation.*?{eq_num}.*?\]', preceding):
                insertion = f'\n\n![{eq_label}]({img_path})\n\n'
                insert_at = max(m2.start(), min_insert_pos)
                content = content[:insert_at] + insertion + content[insert_at:]
                # Advance min_insert_pos so later lead-in equations don't precede
                # this cross-ref insertion in the output.
                min_insert_pos = insert_at + len(insertion)
                changed = True
            continue

        # Find end of the lead-in line
        line_end = content.find('\n', key_pos + key_len)
        if line_end == -1:
            continue

        # Start the gap search from whichever is later: end of lead-in line or
        # min_insert_pos (so consecutive equations maintain correct order).
        search_from = max(line_end, min_insert_pos)
        gap_m = re.search(r'\n+', content[search_from: search_from + 300])
        if gap_m:
            insert_pos = search_from + gap_m.start() + 1
        else:
            insert_pos = search_from + 1

        formula_part = f'\n*{formula_text}*' if formula_text else ''
        insertion = f'\n![{eq_label}]({img_path}){formula_part}\n({eq_num})\n'
        content = content[:insert_pos] + insertion + content[insert_pos:]
        min_insert_pos = insert_pos + len(insertion)
        changed = True

    if changed:
        section_file.write_text(content, encoding='utf-8')


def _fix_cross_section_image_refs(
    out_dir: Path,
    body_sections: list[tuple[str, str]],
    page_section_map: dict[int, int],
) -> None:
    """Rewrite flat-image references that belong to a different section."""
    flat_pattern = re.compile(r'!\[([^\]]*)\]\((?:\.\./img/flat/)?([^)\s]+)\)')

    for idx, (heading, _) in enumerate(body_sections, 1):
        sec_slug = slug(heading) or 'body'
        sec_file = out_dir / 'md' / f'{idx:02d}-{sec_slug}.md'
        if not sec_file.exists():
            continue
        content = sec_file.read_text(encoding='utf-8')
        changed = False

        def _rewrite(m: re.Match, _idx: int = idx) -> str:
            nonlocal changed
            alt, fname = m.group(1), m.group(2)
            page_m = re.match(r'0-raw\.pdf-(\d{4})', fname)
            if page_m:
                page_num = int(page_m.group(1)) - 1
                owning = page_section_map.get(page_num)
                if owning is not None and owning != _idx:
                    changed = True
                    return f'![{alt}](../img/sec{owning:02d}/{fname})'
            return m.group(0)

        new_content = flat_pattern.sub(_rewrite, content)
        if changed:
            sec_file.write_text(new_content, encoding='utf-8')


# ── Public render entry points ────────────────────────────────────────────────


def render_figure_pages(
    pdf_path: Path,
    out_dir: Path,
    body_sections: list[tuple[str, str]],
) -> tuple[dict[str, str], dict[int, int]]:
    """Render cropped figure images and insert them inline at caption positions.

    Returns (figure_images, page_section_map) where figure_images maps normalised
    figure label → relative image path (for INDEX.md).
    """
    figure_page_map = build_figure_page_map(pdf_path)
    page_section_map = build_page_section_map(figure_page_map, body_sections, pdf_path)
    figure_images: dict[str, str] = {}

    doc = fitz.open(str(pdf_path))

    # Collect unique figure entries (label, normalized, page, owning_section)
    seen: dict[str, int] = {}
    unique_entries: list[tuple[str, str, int, int]] = []
    for idx, (heading, _) in enumerate(body_sections, 1):
        sec_slug = slug(heading) or 'body'
        sec_file = out_dir / 'md' / f'{idx:02d}-{sec_slug}.md'
        if not sec_file.exists():
            continue
        content = sec_file.read_text(encoding='utf-8')
        for m in FIG_TABLE_RE.finditer(content):
            label = re.sub(r'\s+', ' ', m.group(1)).strip()
            normalized = re.sub(r'^Fig\.\s*', 'Figure ', label)
            page_num = figure_page_map.get(normalized)
            if page_num is None or normalized in seen:
                continue
            owning = page_section_map.get(page_num, idx)
            seen[normalized] = owning
            unique_entries.append((label, normalized, page_num, owning))

    for label, normalized, page_num, owning in unique_entries:
        img_name = f'page-{page_num + 1:02d}-{normalized.lower().replace(" ", "-")}.png'
        img_path = out_dir / 'img' / f'sec{owning:02d}' / img_name
        _render_one(doc, page_num, label, img_path, content_below=label.upper().startswith('TABLE'))
        figure_images[normalized] = f'img/sec{owning:02d}/{img_name}'

    doc.close()

    _fix_cross_section_image_refs(out_dir, body_sections, page_section_map)

    for idx, (heading, _) in enumerate(body_sections, 1):
        sec_slug = slug(heading) or 'body'
        sec_file = out_dir / 'md' / f'{idx:02d}-{sec_slug}.md'
        if sec_file.exists():
            _insert_figures_inline(sec_file, idx, figure_images, figure_page_map, page_section_map)

    return figure_images, page_section_map


def render_equation_images(
    pdf_path: Path,
    out_dir: Path,
    body_sections: list[tuple[str, str]],
    figure_images: dict[str, str],
    figure_page_map: dict[str, int],
    page_section_map: dict[int, int],
) -> dict[str, str]:
    """Render equation images and insert them at equation number positions.

    Returns updated figure_images dict with equation entries added.
    """
    eq_page_map = build_equation_page_map(pdf_path)
    if not eq_page_map:
        return figure_images

    doc = fitz.open(str(pdf_path))

    for eq_label, page_num in eq_page_map.items():
        eq_num = eq_label.split()[-1]
        owning = page_section_map.get(page_num)
        if owning is None:
            for idx, (_heading, body) in enumerate(body_sections, 1):
                if re.search(rf'\( ?{eq_num} ?\)', body):
                    owning = idx
                    break
        # Last fallback: nearest mapped page's section (handles pages where figure
        # captions weren't extracted to markdown but equations still live there)
        if owning is None and page_section_map:
            nearest = min(page_section_map, key=lambda p: abs(p - page_num))
            owning = page_section_map[nearest]
        if owning is None:
            continue

        img_name = f'page-{page_num + 1:02d}-{eq_label.lower().replace(" ", "-")}.png'
        img_path = out_dir / 'img' / f'sec{owning:02d}' / img_name
        _render_one_equation(doc, page_num, eq_num, img_path)
        figure_images[eq_label] = f'img/sec{owning:02d}/{img_name}'

    # Build context (lead-in + formula text) for equations that may lack (N) in markdown
    eq_context: dict[str, tuple[str | None, str | None]] = {}
    for eq_label, page_num in eq_page_map.items():
        eq_num = eq_label.split()[-1]
        lead_in, formula_text = get_equation_context(doc[page_num], eq_num)
        eq_context[eq_label] = (lead_in, formula_text)

    doc.close()

    for idx, (heading, _) in enumerate(body_sections, 1):
        sec_slug = slug(heading) or 'body'
        sec_file = out_dir / 'md' / f'{idx:02d}-{sec_slug}.md'
        if sec_file.exists():
            _insert_equations_inline(sec_file, idx, eq_page_map, figure_images, page_section_map, eq_context)

    return figure_images
