import re
import shutil
from pathlib import Path

from .figures import build_figure_page_map, render_equation_images, render_figure_pages
from .utils import RN_PATTERN as _RN
from .utils import extract_title_from_preamble, slug

# ── Section file I/O ─────────────────────────────────────────────────────────


def write_section_files(
    body_sections: list[tuple[str, str]],
    md_dir: Path,
) -> list[dict]:
    """Write per-section markdown files, deleting any existing content in md_dir. Returns section info list."""
    if md_dir.exists():
        shutil.rmtree(md_dir)
    md_dir.mkdir(parents=True, exist_ok=True)

    section_info = []
    for idx_s, (heading, body) in enumerate(body_sections, 1):
        s = slug(heading) or 'body'
        fname = f'{idx_s:02d}-{s}.md'
        (md_dir / fname).write_text(f'{heading}\n\n{body}\n', encoding='utf-8')
        section_info.append({'idx': idx_s, 'heading': heading, 'slug': s, 'fname': fname})
    return section_info


# ── Flat image routing ───────────────────────────────────────────────────────


def route_images(
    img_flat: Path,
    body_sections: list[tuple[str, str]],
    md_dir: Path,
    images_dir: Path,
) -> None:
    """Distribute flat images to per-section directories and rewrite image references.

    Images that are referenced in multiple sections are copied to the section
    where they are *first* referenced; later references are rewritten to point
    back to that owning section.
    """
    section_contents: dict[int, str] = {}
    for idx_s, (heading, _) in enumerate(body_sections, 1):
        s = slug(heading) or 'body'
        sec_file = md_dir / f'{idx_s:02d}-{s}.md'
        if sec_file.exists():
            section_contents[idx_s] = sec_file.read_text(encoding='utf-8')

    # Determine which section owns each flat image (first-referenced wins)
    img_owner: dict[str, int] = {}
    for img_file in sorted(img_flat.iterdir()):
        if not img_file.is_file():
            continue
        for idx_s, content in section_contents.items():
            if re.search(rf'\b{re.escape(img_file.name)}\b', content):
                img_owner[img_file.name] = idx_s
                break

    # Copy images to their owning section directories
    for img_file in sorted(img_flat.iterdir()):
        if not img_file.is_file():
            continue
        owner = img_owner.get(img_file.name)
        dest_folder = images_dir / f'sec{owner:02d}' if owner else images_dir / 'orphan'
        dest_folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(img_file), dest_folder / img_file.name)

    # Rewrite image references: own-section → local, cross-section → ../img/secXX/
    for idx_s, content in section_contents.items():
        sec_file = md_dir / f'{idx_s:02d}-{slug(body_sections[idx_s - 1][0]) or "body"}.md'
        changed = False

        def _rewrite(m: re.Match) -> str:
            nonlocal changed
            alt = m.group(1)
            fname = m.group(2)
            owner = img_owner.get(fname)
            if owner is None:
                changed = True
                return f'![{alt}](../img/orphan/{fname})'
            if owner == idx_s:
                changed = True
                return f'![{alt}](../img/sec{idx_s:02d}/{fname})'
            changed = True
            return f'![{alt}](../img/sec{owner:02d}/{fname})'

        content = re.sub(
            r'!\[([^\]]*)\]\((?:.*img/flat/)?([^)\s]+)[^)]*\)',
            _rewrite,
            content,
        )
        if changed:
            sec_file.write_text(content, encoding='utf-8')


# ── Raw converter clutter cleanup ────────────────────────────────────────────


def _clean_section_clutter(section_file: Path) -> int:
    """Remove raw converter artifacts from a section markdown file.

    Removes:
    1. Raw converter images: ``![](../img/secXX/0-raw.pdf-*.png)``
    2. Picture-text blocks: ``**----- Start of picture text -----** ... End ...``
    3. Consecutive blank lines (collapsed to max 2)

    Subfigure labels like (a), (b), (c) are extracted from picture-text blocks
    and preserved inline with the preceding figure caption.

    Returns number of artifacts removed.
    """
    content = section_file.read_text(encoding='utf-8')
    removed = 0

    # Extract subfigure labels from picture-text blocks before removing them
    # Pattern handles both single-line and multi-line blocks:
    # **----- Start of picture text -----**<br>\n...content...\n**----- End of picture text -----**
    pt_block = re.compile(
        r'\*\*----- Start of picture text -----\*\*<br>\s*\n(.*?)\*\*----- End of picture text -----\*\*',
        re.DOTALL,
    )

    def _preserve_subfigs(m: re.Match) -> str:
        nonlocal removed
        removed += 1
        inner = m.group(1).strip()
        # Strip HTML tags
        inner = re.sub(r'<br\s*/?>', '', inner)
        # Extract subfigure labels: (a), (b), (c) etc.
        sub_labels = re.findall(r'\([a-z]\)', inner)
        if sub_labels:
            return ' '.join(sub_labels) + '\n'
        return ''

    content = pt_block.sub(_preserve_subfigs, content)

    # Remove raw converter image references: ![alt](../img/secXX/<pdfname>.pdf-XXXX-XX.png)
    raw_img = re.compile(r'!\[[^\]]*\]\([^)]*?\.pdf-\d{4}-\d{2}\.png\)\s*')
    removed += len(raw_img.findall(content))
    content = raw_img.sub('', content)

    # Remove stray <br> tags
    content = re.sub(r'<br\s*/?>\s*', '', content)

    # Collapse 3+ consecutive blank lines into 2
    content = re.sub(r'\n{4,}', '\n\n\n', content)

    # Remove orphaned "Authorized licensed use..." IEEE copyright lines
    content = re.sub(
        r'\nAuthorized licensed use limited to:.*?Restrictions apply\.\s*\n',
        '\n',
        content,
        flags=re.DOTALL,
    )

    if removed:
        section_file.write_text(content, encoding='utf-8')

    return removed


def clean_all_sections(out_dir: Path, body_sections: list[tuple[str, str]]) -> int:
    """Run clutter cleanup on all section files. Returns total artifacts removed."""
    total = 0
    for idx, (heading, _) in enumerate(body_sections, 1):
        sec_slug = slug(heading) or 'body'
        sec_file = out_dir / 'md' / f'{idx:02d}-{sec_slug}.md'
        if sec_file.exists():
            total += _clean_section_clutter(sec_file)

    # Delete raw converter image files from disk
    img_dir = out_dir / 'img'
    if img_dir.exists():
        raw_pattern = re.compile(r'.*\.pdf-\d{4}-\d{2}\.png$')
        for img_file in img_dir.rglob('*.png'):
            if raw_pattern.match(img_file.name):
                img_file.unlink()
                total += 1

    return total


# ── INDEX.md builder ─────────────────────────────────────────────────────────


def build_index(
    out_dir: Path,
    md_dir: Path,
    body_sections: list[tuple[str, str]],
    figure_images: dict[str, str],
) -> tuple[int, int]:
    """Build and write INDEX.md. Returns (n_figures, n_tables)."""
    index_rows = [
        '| Number | File | Referenced in | Caption |',
        '|--------|------|---------------|---------|',
    ]
    fig_pattern = re.compile(rf'(Figure\s+\d+|Fig\.\s*\d+|Table\s+(?:\d+|{_RN}))', re.IGNORECASE)
    seen: dict[str, str] = {}
    for idx_s, (heading, _) in enumerate(body_sections, 1):
        s = slug(heading) or 'body'
        sec_file = md_dir / f'{idx_s:02d}-{s}.md'
        if not sec_file.exists():
            continue
        content = sec_file.read_text(encoding='utf-8')
        for m in fig_pattern.finditer(content):
            label = m.group(1)
            normalized_label = re.sub(r'(?i)^Fig\.\s*', 'Figure ', label)
            if normalized_label not in seen:
                seen[normalized_label] = f'md/{idx_s:02d}-{s}.md'
                img_path = figure_images.get(normalized_label, '—')
                index_rows.append(f'| {normalized_label} | {img_path} | md/{idx_s:02d}-{s}.md | — |')

    (out_dir / 'INDEX.md').write_text('# Figure / Table Index\n\n' + '\n'.join(index_rows) + '\n', encoding='utf-8')

    n_fig = len([r for r in index_rows if re.match(r'\| (?:Figure|Fig\.)', r)])
    n_tbl = len([r for r in index_rows if re.match(r'\| Table', r, re.IGNORECASE)])
    return n_fig, n_tbl


# ── Main paper output ────────────────────────────────────────────────────────


def write_paper_output(
    sections: list[tuple[str, str]],
    out_dir: Path,
    md_text: str,
    title_override: str | None = None,
    pdf_path: Path | None = None,
) -> tuple[int, int, int]:
    """Write per-section files, paper.md, images, INDEX.md for one paper.
    Returns (n_sections, n_figures, n_tables).
    """
    md_dir = out_dir / 'md'
    img_flat = out_dir / 'img' / 'flat'
    img_flat.mkdir(parents=True, exist_ok=True)

    body_sections = [s for s in sections if s[0] != '']
    if not body_sections:
        body_sections = sections

    section_info = write_section_files(body_sections, md_dir)
    section_links = [
        f'- [{si["idx"]:02d} {si["heading"].lstrip("#").strip()}](md/{si["fname"]})' for si in section_info
    ]

    # Route flat images (from marker/pymupdf4llm) to per-section dirs
    route_images(img_flat, body_sections, md_dir, out_dir / 'img')

    # Render cropped figure/table images and insert inline
    figure_images: dict[str, str] = {}
    if pdf_path and pdf_path.exists():
        figure_images, page_section_map = render_figure_pages(pdf_path, out_dir, body_sections)
        figure_page_map = build_figure_page_map(pdf_path)

        figure_images = render_equation_images(
            pdf_path, out_dir, body_sections, figure_images, figure_page_map, page_section_map
        )

    # Clean up raw converter clutter (raw images, picture-text blocks)
    clean_all_sections(out_dir, body_sections)

    # ── Title ──
    if title_override:
        title = title_override
    else:
        title = 'Untitled'
        best_pos = None
        for lvl in (1, 2, 3):
            title_m = re.search(rf'^{"#" * lvl}\s+(.+)', md_text, re.MULTILINE)
            if title_m:
                candidate = title_m.group(1).strip()
                if candidate.lower() == 'abstract':
                    continue
                if best_pos is None or title_m.start() < best_pos:
                    title = candidate
                    best_pos = title_m.start()

    # Fallback: plain-text preamble (pymupdf4llm output for 2-column IEEE)
    if title == 'Untitled':
        preamble = sections[0][1] if sections and sections[0][0] == '' else ''
        if preamble:
            title = extract_title_from_preamble(preamble)
        else:
            title = extract_title_from_preamble(md_text)

    # ── Abstract ──
    abstract_m = re.search(
        r'(?:^#{1,3}\s*abstract\s*\n)(.*?)(?=^#{1,3}\s|\Z)',
        md_text,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if abstract_m:
        abstract = abstract_m.group(1).strip()
    else:
        inline_m = re.search(
            r'(?:_?\*{0,2}Abstract\*{0,2}_?)\s*(?:\*{0,2})?[—\-](?:\*{0,2})?\s*(.+?)(?=\n\n|\Z)',
            md_text,
            re.IGNORECASE | re.DOTALL,
        )
        if inline_m:
            abstract = re.sub(r'\*{1,2}|_{1,2}', '', inline_m.group(1)).strip()[:1200]
        else:
            preamble_body = sections[0][1] if sections and sections[0][0] == '' else ''
            abstract = preamble_body[:800]

    paper_md = f'# {title}\n\n## Abstract\n{abstract}\n\n## Sections\n' + '\n'.join(section_links) + '\n'
    (out_dir / 'paper.md').write_text(paper_md, encoding='utf-8')

    n_fig, n_tbl = build_index(out_dir, md_dir, body_sections, figure_images)

    n_sec = len(body_sections)
    return n_sec, n_fig, n_tbl
