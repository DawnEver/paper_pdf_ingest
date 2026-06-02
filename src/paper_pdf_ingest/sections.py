import re

from .utils import RN_PATTERN as _RN, strip_formatting

_KEEP_HEADINGS = re.compile(r'result|experiment|evaluat|ablat|comparison', re.IGNORECASE)

# ── Section splitter ─────────────────────────────────────────────────────────
# Match: "III. INTERFERENCE MITIGATION..." — no $ anchor because body text
# may leak onto the same line in 2-column IEEE pymupdf4llm output.
_ROMAN_HEADING_RE = re.compile(rf'^({_RN})\.\s+([A-Z][A-Z\s,/-]{{4,}})')
_STANDALONE_RE = re.compile(r'^(ACKNOWLEDGMENT|REFERENCES|APPENDIX|CONCLUSION)S?\s*$')
_CLEAN_HEADING_RE = re.compile(r'^((?:I{1,3}V?|VI{1,3}|IX|X{1,3}V?I{0,2})\.)')


def _clean_heading_text(heading: str) -> str:
    """Strip trailing lowercase body text from Roman-numeral headings.

    Processes line by line so continuations aren't lost when the first
    line already has trailing lowercase text.
    """
    m = _CLEAN_HEADING_RE.match(heading)
    if not m:
        return heading
    prefix = m.group(1)
    rest = heading[m.end():].strip()
    result = []
    for line in rest.split('\n'):
        for w in line.strip().split():
            if w[0].islower():
                break
            result.append(w)
    return f'{prefix} {" ".join(result)}'.strip()


def _split_plaintext(md: str) -> list[tuple[str, str]]:
    """Fallback: split on Roman-numeral sections and standalone ALL-CAPS headings.

    Used when pymupdf4llm produces flat text without markdown `#` headings
    (common for 2-column IEEE papers).
    """
    lines = md.split('\n')
    sections: list[tuple[str, str]] = []
    current_heading = ''
    current_body: list[str] = []
    in_preamble = True
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        # Roman numeral section heading: "I. INTRODUCTION", "II. METHOD", etc.
        m = _ROMAN_HEADING_RE.match(stripped)
        if m:
            if in_preamble and current_body:
                sections.append(('', '\n'.join(current_body).strip()))
            elif not in_preamble and current_body:
                sections.append((current_heading, '\n'.join(current_body).strip()))

            heading_text = stripped
            # Check next line for title continuation (ALL CAPS subtitle)
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt and re.match(r'^[A-Z][A-Z\s,/-]{4,}', nxt):
                    i += 1
                    heading_text += '\n' + nxt

            current_heading = _clean_heading_text(heading_text)
            current_body = []
            in_preamble = False
            i += 1
            continue

        # Standalone ALL-CAPS section: ACKNOWLEDGMENT, REFERENCES, etc.
        if _STANDALONE_RE.match(stripped):
            if in_preamble and current_body:
                sections.append(('', '\n'.join(current_body).strip()))
            elif not in_preamble and current_body:
                sections.append((current_heading, '\n'.join(current_body).strip()))

            current_heading = stripped
            current_body = []
            in_preamble = False
            i += 1
            continue

        current_body.append(lines[i])
        i += 1

    # Final section
    body_text = '\n'.join(current_body).strip()
    if in_preamble and body_text:
        sections.append(('', body_text))
    elif not in_preamble and body_text:
        sections.append((current_heading, body_text))

    if len(sections) < 2:
        return [('', md)]

    return sections


def split_sections(md: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) pairs. heading='' for preamble.

    Picks the *shallowest* heading level that has ≥3 matches (favours
    top-level sections over fine-grained subsections).  Falls back to
    plain-text heuristics (Roman numerals, ALL-CAPS lines) when no
    markdown headings are found — handles pymupdf4llm output for
    2-column IEEE papers.
    """
    counts = {lvl: len(re.findall(rf'^{"#" * lvl} ', md, re.MULTILINE)) for lvl in (1, 2, 3)}

    best = None
    for lvl in (1, 2, 3):
        if counts[lvl] >= 3:
            best = lvl
            break

    if best is not None:
        # Single-level split: inner capture "(##)" → 2 groups per heading
        pattern = rf'^({"#" * best})\s'
        parts = re.split(f'({pattern}.*)', md, flags=re.MULTILINE)
        sections: list[tuple[str, str]] = []
        preamble = parts[0].strip()
        if preamble:
            sections.append(('', preamble))
        i = 1
        while i < len(parts) - 2:
            heading_line = parts[i].strip()
            body = parts[i + 2].strip()
            sections.append((heading_line, body))
            i += 3
    else:
        # All-heading fallback: single capture group → 1 group per heading
        pattern = r'^#+\s'
        parts = re.split(f'({pattern}.*)', md, flags=re.MULTILINE)
        sections = []
        preamble = parts[0].strip()
        if preamble:
            sections.append(('', preamble))
        i = 1
        while i < len(parts) - 1:
            heading_line = parts[i].strip()
            body = parts[i + 1].strip() if i + 1 < len(parts) else ''
            sections.append((heading_line, body))
            i += 2

    if len(sections) < 2:
        sections = _split_plaintext(md)

    return sections


# ── Section classification ──────────────────────────────────────────────────


def classify_section(heading: str, body: str) -> str:
    """Classify a section as 'keep', 'discard', or 'merge-up'.

    'merge-up': heading is a diagram label (e.g. (a), (b)) — discard
    the heading but merge its body into the previous section.
    'discard':  pure OCR noise — discard heading and body.
    'keep':     legitimate section.
    """
    clean_body = strip_formatting(body)
    clean_heading = re.sub(r'[*#]', '', heading).strip()

    # diagram sub-labels: (a), (b), (c), (d) — never real sections
    if re.match(r'^\([a-z]\)$', clean_heading):
        return 'merge-up'

    # body too short to be substantive → discard
    if len(clean_body) < 80:
        return 'discard'

    # diagram-label headings from figure/diagram fragments
    if re.match(r'^\*{0,2}[A-Za-z_][\w\s\[\]*]{0,20}\*{0,2}$', clean_heading):
        # body is mostly garbled table markup → discard
        if len(clean_body) < 400:
            if _KEEP_HEADINGS.search(clean_heading):
                return 'keep'
            pipe_ratio = clean_body.count('|') / max(len(clean_body), 1)
            if pipe_ratio > 0.05:
                return 'discard'
        # or body is short enough to be just figure caption remnants
        if len(clean_body) < 200:
            return 'discard'

    return 'keep'


def _is_paper_boundary(heading: str, body: str, idx: int) -> bool:
    """Detect if this section starts a new independent paper appended after
    the main paper.  Only checked for sections beyond the first few.
    """
    if idx < 5:
        return False

    top = heading + '\n' + body[:500]

    author_score = 0
    if re.search(r'@\w+\.\w+\.?\w+', top):
        author_score += 1
    if re.search(r'(?:University|Institute|College|Technische)\s+(?:of\s+)?\w+', top):
        author_score += 1
    if re.search(r'\b(?:Student\s+Member|Fellow|Senior\s+Member|Member)\s*,?\s*IEEE\b', top):
        author_score += 1
    if re.search(r'\{[^}]*@[^}]*\}', top):
        author_score += 1
    if author_score >= 2:
        return True

    if re.search(r'©\s*20\d{2}\s*IEEE', top):
        return True

    if re.search(r'20\d{2}\s+IEEE\s+.*?(?:Conference|Expo|Convention)', top):
        return True

    if re.search(r'\bI\.\s+INTRODUCTION\b', (heading + '\n' + body)[:200]) and idx >= 5:
        return True

    return bool(idx >= 5 and re.search(r'Abstract[—\-]', top))


def _paper_title_from_sections(sections_list: list[tuple[str, str]]) -> str:
    """Extract a title from the first heading of a paper fragment."""
    for heading, _ in sections_list:
        if heading:
            return heading.lstrip('#').strip()[:80]
    return 'untitled'


def clean_sections(
    sections: list[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[tuple[str, list[tuple[str, str]]]]]:
    """Filter noise sections and detect appended-paper boundaries.

    Returns:
      main_sections  — sections belonging to the primary paper
      appended       — list of (title, sections) for each appended paper

    """
    cleaned: list[tuple[str, str]] = []
    for heading, body in sections:
        action = classify_section(heading, body)
        if action == 'discard':
            continue
        if action == 'merge-up':
            if cleaned:
                prev_heading, prev_body = cleaned[-1]
                cleaned[-1] = (prev_heading, prev_body + '\n\n' + body)
            elif heading:
                cleaned.append((heading, body))
        else:
            cleaned.append((heading, body))

    main_sections: list[tuple[str, str]] = []
    appended: list[tuple[str, list[tuple[str, str]]]] = []
    current_batch: list[tuple[str, str]] = []
    found_boundary = False

    for idx, (heading, body) in enumerate(cleaned):
        if _is_paper_boundary(heading, body, idx):
            if current_batch:
                if not found_boundary:
                    main_sections = current_batch
                    found_boundary = True
                else:
                    title = _paper_title_from_sections(current_batch)
                    appended.append((title, current_batch))
            current_batch = [(heading, body)]
        else:
            current_batch.append((heading, body))

    if current_batch:
        if not found_boundary:
            main_sections = current_batch
        else:
            title = _paper_title_from_sections(current_batch)
            appended.append((title, current_batch))

    return main_sections, appended
