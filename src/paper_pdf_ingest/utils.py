import re

RN_PATTERN = r'(?:IX|IV|V?I{1,3}|I{1,3}V?|VI{1,3}|XI{1,3}|XI?V|XV|XVI{1,3}|XXI{1,3}|XXI?V|XXV|XXXI{1,3}|XXXI?V|XXXIX)'


def slug(text: str, maxlen: int = 30) -> str:
    s = re.sub(r'^#+\s*', '', text).lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:maxlen].strip('-')


def strip_formatting(text: str) -> str:
    """Remove markdown images, links, and formatting characters."""
    clean = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    clean = re.sub(r'\[([^\]]*)\]\(.*?\)', r'\1', clean)
    return re.sub(r'[*#>|_\-`\s]', '', clean)


_AUTHOR_SIGNAL_RE = re.compile(
    r'@\w+\.\w+|Student\s+Member|Fellow,?\s*IEEE|University\s+of|'
    r'Research\s+Institute|Laboratory|Laboratories|Dept\.?\s+of',
    re.IGNORECASE,
)
# Multi-name author line: 3+ capitalized words that look like names
_MULTI_NAME_RE = re.compile(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){2,})$')
# Single name pair
_NAME_PAIR_RE = re.compile(r'^[A-Z][a-z]+\s[A-Z][a-z]+(\s[A-Z][a-z]+)?$')


def extract_title_from_preamble(preamble: str) -> str:
    """Extract paper title from plain-text preamble (no `#` headings).

    Collects leading non-empty lines before hitting author/abstract signals.
    """
    lines = preamble.split('\n')
    title_lines: list[str] = []
    name_count = 0

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('<!-- page'):
            if title_lines:
                break
            continue
        if _AUTHOR_SIGNAL_RE.search(stripped) or re.match(r'Abstract[—\-]', stripped):
            break
        # Multi-name line (merged authors): "Wenting Wang Tianjie Zou Hailin Huang"
        if _MULTI_NAME_RE.match(stripped):
            break
        # Single name pair: "Wenting Wang"
        if _NAME_PAIR_RE.match(stripped):
            name_count += 1
            if name_count >= 3:
                break
            continue

        name_count = 0
        title_lines.append(stripped)

    if title_lines:
        return ' '.join(title_lines)[:200]

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('<!--'):
            return stripped[:200]

    return 'Untitled'
