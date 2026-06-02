"""Figure and equation region cropping from PDF pages."""

from __future__ import annotations

import re
import warnings

import fitz


def crop_figure(page: fitz.Page, label: str, content_below: bool = False) -> fitz.Rect | None:
    """Return a tight crop rect for *label* on *page*, or None to fall back to full page.

    Strategy (works for typical IEEE 2-column layouts):
    1. Find the caption text block that starts with the label ("Fig. X." / "Table X.").
    2. Collect graphic content blocks (images + drawings):
       - content_below=False (figures): content ABOVE the caption
       - content_below=True  (tables):  content BELOW the caption
    3. The crop spans from the top of those blocks down to the bottom of the caption,
       with a small margin. Column width is inferred from the caption block's x-span.
    """
    page_rect = page.rect
    blocks = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']

    caption_rect = _find_caption_rect(blocks, label)
    if caption_rect is None:
        return None

    cap_top, cap_bottom = caption_rect.y0, caption_rect.y1
    cap_x0, cap_x1 = caption_rect.x0, caption_rect.x1
    half_page = page_rect.height / 2
    page_mid = page_rect.width / 2

    # Constrain crop to not bleed into adjacent captions in the same column
    upper_bound, lower_bound = _find_caption_bounds(blocks, cap_x0, cap_top, cap_bottom, page_mid)

    col_x0, col_x1 = _column_bounds(page_rect, cap_x0)

    if content_below:
        # Stop before the first full-column-width body paragraph (table has ended)
        body_lower = _find_body_text_lower(page, cap_bottom, col_x0, col_x1)
        lower_bound = min(lower_bound, body_lower)

    graphic_rects = _collect_graphic_rects(
        page,
        cap_top,
        cap_bottom,
        half_page,
        col_x0,
        col_x1,
        content_below,
        upper_bound=upper_bound,
        lower_bound=lower_bound,
    )

    extra_x_rects: list = []
    if content_below:
        # Collect table row text rects: used for x-expansion and (if no drawings) y-bottom
        row_rects, row_bottom = _collect_table_row_bounds(page, cap_bottom, col_x0, col_x1, lower_bound)
        extra_x_rects = row_rects
        if not graphic_rects and row_bottom > cap_bottom:
            lower_bound = min(lower_bound, row_bottom)

    return _build_crop_rect(
        page_rect,
        cap_x0,
        cap_x1,
        cap_top,
        cap_bottom,
        half_page,
        graphic_rects,
        content_below,
        upper_bound=upper_bound,
        lower_bound=lower_bound,
        extra_x_rects=extra_x_rects,
    )


def crop_equation(page: fitz.Page, eq_num: str) -> fitz.Rect | None:
    """Find and crop the equation region for equation number *eq_num*.

    Locates "(N)" on the page, collects image/graphic blocks above it in the
    same column within a reasonable distance, then merges nearby candidates.
    Falls back to any equation-shaped image block when the number isn't found.
    """
    page_rect = page.rect
    page_mid = page_rect.width / 2
    blocks = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']

    eq_num_y, eq_num_x = _find_eq_number_pos(blocks, eq_num)
    candidates = _collect_eq_candidates(page, eq_num_y, eq_num_x, page_mid, page_rect)

    if candidates:
        candidates.sort(key=lambda r: r.y0)
        merged = _merge_nearby(candidates, gap=15)
        if merged:
            margin = 8
            r = merged[0]
            return fitz.Rect(
                max(0.0, r.x0 - margin),
                max(0.0, r.y0 - margin),
                min(page_rect.width, r.x1 + margin),
                min(page_rect.height, r.y1 + margin),
            )

    # Fallback: text-rendered equation — crop the PDF text region around (N)
    if eq_num_y is None:
        return None
    return _crop_eq_text_region(blocks, eq_num, eq_num_x, page_mid, page_rect)


# ── Helpers ───────────────────────────────────────────────────────────────────

_CAP_LABEL_RE = re.compile(r'(?:Fig\.|Figure|Table)\s+', re.IGNORECASE)
# Maximum block height for a caption (incl. multi-line subfigure layouts).
# Body-text paragraphs are typically 80-200 pt; IEEE captions are <=60 pt.
_CAP_MAX_HEIGHT = 45.0


def _find_caption_bounds(
    blocks: list, cap_x0: float, cap_top: float, cap_bottom: float, page_mid: float
) -> tuple[float, float]:
    """Return (upper_bound, lower_bound) y-coords from nearest same-column captions above/below.

    Uses a height threshold to distinguish compact caption blocks (≤60 pt) from
    taller body-text paragraphs that happen to contain a figure cross-reference.
    """
    upper_bound = 0.0
    lower_bound = float('inf')
    same_col_left = cap_x0 < page_mid

    for blk in blocks:
        if blk['type'] != 0:
            continue
        blk_text = ''.join(span.get('text', '') for line in blk.get('lines', []) for span in line.get('spans', []))
        bx0, y0, bx1, y1 = blk['bbox']
        blk_height = y1 - y0
        # Only compact blocks that look like captions (short text, narrow height)
        if len(blk_text) > 350 or not _CAP_LABEL_RE.search(blk_text) or blk_height > _CAP_MAX_HEIGHT:
            continue
        blk_col_left = (bx0 + bx1) / 2 < page_mid
        if blk_col_left != same_col_left:
            continue  # different column — ignore
        if y1 <= cap_top and abs(y0 - cap_top) > 3:
            upper_bound = max(upper_bound, y1)
        elif y0 >= cap_bottom and abs(y0 - cap_top) > 3:
            lower_bound = min(lower_bound, y0)
    return upper_bound, lower_bound


_MIN_TABLE_HEIGHT = 40.0  # body text must start at least this far below the table caption


def _find_body_text_lower(page: fitz.Page, cap_bottom: float, col_x0: float, col_x1: float) -> float:
    """Return y0 of first full-column-width body-paragraph text block below the table.

    Body paragraphs span ≥70% of the column width.  We require a minimum gap of
    _MIN_TABLE_HEIGHT below cap_bottom so the table header is not mistaken for body text.
    """
    col_width = col_x1 - col_x0
    threshold = col_width * 0.70
    earliest_body_y = cap_bottom + _MIN_TABLE_HEIGHT

    def _in_col(r: fitz.Rect) -> bool:
        return col_x0 < (r.x0 + r.x1) / 2 < col_x1

    for blk in sorted(page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks'], key=lambda b: b['bbox'][1]):
        if blk['type'] != 0:
            continue
        r = fitz.Rect(blk['bbox'])
        if r.y0 < earliest_body_y or not _in_col(r):
            continue
        if r.width >= threshold:
            return r.y0
    return float('inf')


def _collect_table_row_bounds(
    page: fitz.Page, cap_bottom: float, col_x0: float, col_x1: float, lower_bound: float
) -> tuple[list[fitz.Rect], float]:
    """Return (row_rects, last_y1) for table-row text blocks below the caption.

    row_rects are used to expand the crop x-bounds.  last_y1 is the y1 of the
    last row block (used as content_bottom when no drawing elements are present).
    """
    col_width = col_x1 - col_x0
    threshold = col_width * 0.70
    limit = min(cap_bottom + 300, lower_bound)
    last_y1 = cap_bottom
    rects: list[fitz.Rect] = []

    def _in_col(r: fitz.Rect) -> bool:
        return col_x0 < (r.x0 + r.x1) / 2 < col_x1

    for blk in page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']:
        if blk['type'] != 0:
            continue
        r = fitz.Rect(blk['bbox'])
        if r.y0 < cap_bottom - 5 or r.y1 > limit or not _in_col(r):
            continue
        rects.append(r)
        if r.width < threshold:
            last_y1 = max(last_y1, r.y1)
    return rects, last_y1


def _find_caption_rect(blocks: list, label: str) -> fitz.Rect | None:
    """Return the best-match caption block for *label*.

    Collects all short blocks (≤350 chars) that contain "label." and returns
    the one with the SMALLEST height — caption blocks are compact (1-2 lines),
    while body-text blocks that contain a cross-reference to the same figure
    are typically much taller.

    Also tries the "Fig. N." short form when *label* is "Figure N", so that
    captions using the abbreviated form are found even when the caller passes
    the normalised form.
    """
    label = re.sub(r'\s+', ' ', label).strip()  # normalise newlines from 2-col extraction
    patterns = [re.compile(re.escape(label) + r'\.', re.IGNORECASE)]
    m = re.match(r'^Figure\s+(\d+)$', label, re.IGNORECASE)
    if m:
        patterns.append(re.compile(rf'Fig\.\s*{m.group(1)}\.', re.IGNORECASE))

    candidates: list[tuple[float, fitz.Rect]] = []
    for blk in blocks:
        if blk['type'] != 0:
            continue
        blk_text = ''.join(span.get('text', '') for line in blk.get('lines', []) for span in line.get('spans', []))
        if len(blk_text) > 350:
            continue
        for pat in patterns:
            if pat.search(blk_text):
                bbox = blk['bbox']
                height = bbox[3] - bbox[1]
                candidates.append((height, fitz.Rect(bbox)))
                break

    if not candidates:
        return None
    # Pick the most compact block -- true captions are 1-2 lines, body refs are paragraph-tall
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _column_bounds(page_rect: fitz.Rect, cap_x0: float) -> tuple[float, float]:
    page_mid = page_rect.width / 2
    if cap_x0 < page_mid:
        return 0.0, page_mid + 20
    return page_mid - 20, page_rect.width


def _collect_graphic_rects(
    page: fitz.Page,
    cap_top: float,
    cap_bottom: float,
    half_page: float,
    col_x0: float,
    col_x1: float,
    content_below: bool,
    upper_bound: float = 0.0,
    lower_bound: float = float('inf'),
) -> list[fitz.Rect]:
    def _in_col(r: fitz.Rect) -> bool:
        return col_x0 < (r.x0 + r.x1) / 2 < col_x1

    rects: list[fitz.Rect] = []

    for blk in page.get_text('dict')['blocks']:
        if blk['type'] != 1:
            continue
        r = fitz.Rect(blk['bbox'])
        if content_below:
            if r.y0 >= cap_bottom - 10 and r.y1 - cap_bottom <= half_page and _in_col(r) and r.y1 <= lower_bound:
                rects.append(r)
        elif r.y1 <= cap_top + 20 and cap_top - r.y0 <= half_page and _in_col(r) and r.y0 >= upper_bound:
            rects.append(r)

    try:
        for draw in page.get_drawings():
            r = fitz.Rect(draw['rect'])
            if r.height < 3 or r.width < 3:
                continue
            if content_below:
                if r.y0 >= cap_bottom - 10 and r.y1 - cap_bottom <= half_page and _in_col(r) and r.y1 <= lower_bound:
                    rects.append(r)
            elif r.y1 <= cap_top + 20 and cap_top - r.y0 <= half_page and _in_col(r) and r.y0 >= upper_bound:
                rects.append(r)
    except (RuntimeError, AttributeError) as e:
        warnings.warn(f'get_drawings() failed on page {page.number}: {e}', stacklevel=2)

    return rects


def _build_crop_rect(
    page_rect: fitz.Rect,
    cap_x0: float,
    cap_x1: float,
    cap_top: float,
    cap_bottom: float,
    half_page: float,
    graphic_rects: list[fitz.Rect],
    content_below: bool,
    upper_bound: float = 0.0,
    lower_bound: float = float('inf'),
    extra_x_rects: list | None = None,
) -> fitz.Rect | None:
    margin = 6
    x0, x1 = cap_x0, cap_x1
    for r in list(graphic_rects) + list(extra_x_rects or []):
        x0 = min(x0, r.x0)
        x1 = max(x1, r.x1)

    eff_lower = lower_bound if lower_bound < float('inf') else page_rect.height

    if not graphic_rects:
        warnings.warn(
            f'no graphic elements found for {"table" if content_below else "figure"} crop '
            f'(cap_top={cap_top:.1f}); falling back to half-page estimate',
            stacklevel=4,
        )

    if content_below:
        content_top = cap_top
        content_bottom = max(
            (r.y1 for r in graphic_rects),
            default=min(page_rect.height, cap_bottom + half_page, eff_lower),
        )
        content_bottom = min(content_bottom, eff_lower)
    else:
        content_top = min(
            (r.y0 for r in graphic_rects),
            default=max(0.0, cap_top - half_page, upper_bound),
        )
        content_top = max(content_top, upper_bound)
        content_bottom = cap_bottom

    crop = fitz.Rect(
        max(0.0, x0 - margin),
        max(0.0, content_top - margin),
        min(page_rect.width, x1 + margin),
        min(page_rect.height, content_bottom + margin),
    )
    return crop if crop.height >= 40 else None


def _find_eq_number_pos(blocks: list, eq_num: str) -> tuple[float | None, float | None]:
    """Find the y/x position of equation number (N) on the page.

    Returns the y/x centre of the specific LINE (not block) containing "(N)" so that
    the crop region is tight even when (N) appears at the bottom of a multi-line block.
    Matches both standalone "(N)" blocks and inline "formula... (N)" at end of block.
    """
    pattern = re.compile(rf'\({re.escape(eq_num)}\)\s*$')
    for blk in blocks:
        if blk['type'] != 0:
            continue
        # Scan individual lines to find the one ending with (N)
        for line in blk.get('lines', []):
            line_text = ''.join(span.get('text', '') for span in line.get('spans', [])).strip()
            if pattern.search(line_text):
                lb = line['bbox']
                return (lb[1] + lb[3]) / 2, (lb[0] + lb[2]) / 2
        # Fallback: check full block text (some renderers produce single-span blocks)
        blk_text = ''.join(
            span.get('text', '') for line in blk.get('lines', []) for span in line.get('spans', [])
        ).strip()
        if pattern.search(blk_text):
            bbox = blk['bbox']
            return (bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2
    return None, None


_MAX_EQ_IMG_DIST = 80  # points — image must be within this distance above eq number
_MAX_EQ_TEXT_ABOVE = 80  # points — how far above (N) we look for multi-line formula text


_BODY_END_RE = re.compile(r'(?:is|are|as|by|of|for|with|from|follows):\s*$', re.IGNORECASE)


def _is_body_text_line(text: str) -> bool:
    """Return True if the text line looks like body prose rather than an equation formula.

    Two tests:
    1. Ends with a colon-phrase that closes a body sentence ("...calculated by:", "...set as:")
    2. Has 5+ tokens and high alphabetic density (>60%) — typical prose sentence fragment
    """
    stripped = text.strip()
    if not stripped:
        return False
    if _BODY_END_RE.search(stripped):
        return True
    tokens = stripped.split()
    if len(tokens) < 5:
        return False
    total = sum(1 for c in stripped if not c.isspace())
    alpha = sum(1 for c in stripped if c.isalpha())
    return total > 0 and alpha / total > 0.60


def _crop_eq_text_region(
    blocks: list,
    eq_num: str,
    eq_num_x: float | None,
    page_mid: float,
    page_rect: fitz.Rect,
    margin_top: int = 2,
    margin_bottom: int = 6,
    margin_side: int = 8,
) -> fitz.Rect | None:
    """Crop the PDF page region that contains a text-rendered equation.

    Finds the BLOCK containing "(N)", uses its full bbox (all formula lines), then
    adds any short non-paragraph blocks immediately above (for spanning equations).
    Full-width equations (N near right page margin > 92%) relax the column filter.
    """
    pattern = re.compile(rf'\({re.escape(eq_num)}\)\s*$')
    eq_col_left = (eq_num_x < page_mid) if eq_num_x is not None else True
    is_full_width = eq_num_x is not None and eq_num_x > page_rect.width * 0.92

    # Step 1: find the block containing (N) and extract only the equation lines from it.
    # Walk backwards from the (N) line, stopping at body-text lines.
    eq_line_rects: list[fitz.Rect] = []

    for blk in blocks:
        if blk['type'] != 0:
            continue
        blk_col_left = (blk['bbox'][0] + blk['bbox'][2]) / 2 < page_mid
        if not is_full_width and blk_col_left != eq_col_left:
            continue
        lines = blk.get('lines', [])
        # Find the index of the line ending with (N)
        eq_line_idx = None
        for i, line in enumerate(lines):
            lt = ''.join(s.get('text', '') for s in line.get('spans', [])).strip()
            if pattern.search(lt):
                eq_line_idx = i
                break
        if eq_line_idx is None:
            continue

        # Collect backward from eq_line_idx until body-text line or block start
        collected = []
        for i in range(eq_line_idx, -1, -1):
            line = lines[i]
            lt = ''.join(s.get('text', '') for s in line.get('spans', [])).strip()
            if i < eq_line_idx and _is_body_text_line(lt):
                break  # stop before body paragraph text
            lb = line['bbox']
            if lb[2] > lb[0] and lb[3] > lb[1]:  # skip degenerate lines
                collected.append(fitz.Rect(lb))
        eq_line_rects = collected
        break

    if not eq_line_rects:
        return None

    eq_block_rect = fitz.Rect(
        min(r.x0 for r in eq_line_rects),
        min(r.y0 for r in eq_line_rects),
        max(r.x1 for r in eq_line_rects),
        max(r.y1 for r in eq_line_rects),
    )

    # Step 2: sibling/above blocks — same column, not body text.
    # Only needed when (N) is in its own narrow block (len==1).
    # Includes same-level blocks (formula beside (N)) and blocks within _MAX_EQ_TEXT_ABOVE above.
    body_threshold = max(eq_block_rect.width * 1.1, 200)
    above: list[fitz.Rect] = []
    # Run sibling search when the collected region is narrow (equation-number only, formula elsewhere)
    needs_sibling_search = len(eq_line_rects) <= 3 and eq_block_rect.width < 100
    if not is_full_width and needs_sibling_search:
        for blk in blocks:
            if blk['type'] != 0:
                continue
            r = fitz.Rect(blk['bbox'])
            blk_col_left = (r.x0 + r.x1) / 2 < page_mid
            if blk_col_left != eq_col_left:
                continue
            # Accept blocks that overlap in y with the (N) block or are above within threshold
            y_overlaps = r.y0 < eq_block_rect.y1 + 10 and r.y1 > eq_block_rect.y0 - 5
            y_above = r.y1 < eq_block_rect.y0 and eq_block_rect.y0 - r.y0 <= _MAX_EQ_TEXT_ABOVE
            if not (y_overlaps or y_above):
                continue
            # Skip the (N) block itself
            if abs(r.x0 - eq_block_rect.x0) < 2 and abs(r.y0 - eq_block_rect.y0) < 2:
                continue
            if r.width > body_threshold:
                continue
            blk_lines = blk.get('lines', [])
            if any(_is_body_text_line(''.join(s.get('text', '') for s in ln.get('spans', []))) for ln in blk_lines):
                continue
            above.append(r)

    all_rects = [eq_block_rect, *above]
    x0 = min(r.x0 for r in all_rects)
    y0 = min(r.y0 for r in all_rects)
    x1 = max(r.x1 for r in all_rects)
    y1 = max(r.y1 for r in all_rects)

    return fitz.Rect(
        max(0.0, x0 - margin_side),
        max(0.0, y0 - margin_top),
        min(page_rect.width, x1 + margin_side),
        min(page_rect.height, y1 + margin_bottom),
    )


def get_equation_context(page: fitz.Page, eq_num: str) -> tuple[str | None, str | None]:
    """Return (lead_in_text, formula_text) for equation *eq_num*.

    lead_in_text: the body-prose sentence immediately before the formula,
                  used to locate the insertion point in the markdown when
                  the explicit (N) reference is absent.
    formula_text: concatenated span text of formula lines (may contain unicode
                  math chars; useful as a plain-text hint for AI readers).

    Strategy: walk backward from the (N) line within its block (same logic as
    _crop_eq_text_region) until hitting a body-text line — that line is the
    lead-in.  For standalone (N) blocks that contain no body text, fall back
    to the last body-text LINE of the preceding same-column block.
    """
    page_rect = page.rect
    page_mid = page_rect.width / 2
    blocks = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']

    eq_num_y, eq_num_x = _find_eq_number_pos(blocks, eq_num)
    if eq_num_y is None:
        return None, None

    eq_col_left = (eq_num_x < page_mid) if eq_num_x is not None else True
    pattern = re.compile(rf'\({re.escape(eq_num)}\)\s*$')

    lead_in_text: str | None = None
    formula_parts: list[str] = []
    eq_block_y0: float | None = None  # y0 of the (N)-containing block

    # ── Step 1: within-block backward walk ────────────────────────────────────
    for blk in blocks:
        if blk['type'] != 0:
            continue
        blk_col_left = (blk['bbox'][0] + blk['bbox'][2]) / 2 < page_mid
        if blk_col_left != eq_col_left:
            continue
        lines = blk.get('lines', [])
        eq_line_idx = None
        for i, line in enumerate(lines):
            lt = ''.join(s.get('text', '') for s in line.get('spans', [])).strip()
            if pattern.search(lt):
                eq_line_idx = i
                break
        if eq_line_idx is None:
            continue

        eq_block_y0 = blk['bbox'][1]

        # Walk backward: collect formula lines, then ALL consecutive body-text lines
        # that form the lead-in sentence (may span multiple lines, e.g. "...can be\n"
        # "easily obtained in the cylindrical coordinate system as:").
        lead_in_parts: list[str] = []
        collecting_lead_in = False
        for i in range(eq_line_idx - 1, -1, -1):
            lt = ''.join(s.get('text', '') for s in lines[i].get('spans', [])).strip()
            if _is_body_text_line(lt):
                collecting_lead_in = True
                lead_in_parts.insert(0, lt)
            elif lt:
                if collecting_lead_in:
                    break  # formula line interrupts body → stop
                formula_parts.insert(0, lt)
        if lead_in_parts:
            lead_in_text = ' '.join(lead_in_parts)
        break  # found the block

    # ── Step 2: fallback — last body-text LINE of the preceding same-col block ─
    if lead_in_text is None and eq_block_y0 is not None:
        best_y1 = 0.0
        for blk in blocks:
            if blk['type'] != 0:
                continue
            bx0, _by0, bx1, by1 = blk['bbox']
            blk_col_left = (bx0 + bx1) / 2 < page_mid
            if blk_col_left != eq_col_left or by1 > eq_block_y0 + 5:
                continue
            if by1 <= best_y1:
                continue
            # Find the last body-text line in this block
            for line in reversed(blk.get('lines', [])):
                lt = ''.join(s.get('text', '') for s in line.get('spans', [])).strip()
                if _is_body_text_line(lt):
                    best_y1 = by1
                    lead_in_text = lt
                    break

    formula_text = ' '.join(formula_parts).strip() or None
    return lead_in_text, formula_text


def _collect_eq_candidates(
    page: fitz.Page,
    eq_num_y: float | None,
    eq_num_x: float | None,
    page_mid: float,
    page_rect: fitz.Rect,
) -> list[fitz.Rect]:
    candidates: list[fitz.Rect] = []
    for blk in page.get_text('dict')['blocks']:
        if blk['type'] != 1:
            continue
        r = fitz.Rect(blk['bbox'])
        if r.width < 30 or r.height < 8:
            continue
        if eq_num_y is not None:
            same_col = (eq_num_x < page_mid) == ((r.x0 + r.x1) / 2 < page_mid)  # type: ignore[operator]
            if same_col and r.y1 <= eq_num_y + 10 and eq_num_y - r.y0 < _MAX_EQ_IMG_DIST:
                candidates.append(r)
        elif r.width > 50 and r.height > 10 and r.width / max(r.height, 1) > 1.5:
            if r.y0 > 60 and r.y1 < page_rect.height - 60:
                candidates.append(r)
    return candidates


def _merge_nearby(rects: list[fitz.Rect], gap: float) -> list[fitz.Rect]:
    merged: list[fitz.Rect] = []
    for r in rects:
        if merged and r.y0 - merged[-1].y1 < gap:
            merged[-1] = fitz.Rect(min(merged[-1].x0, r.x0), merged[-1].y0, max(merged[-1].x1, r.x1), r.y1)
        else:
            merged.append(r)
    return merged
