import shutil
import sys
from pathlib import Path

from .convert import augment_markdown_with_formulas, convert
from .output import write_paper_output
from .sections import clean_sections, split_sections
from .utils import slug


def main() -> None:
    if len(sys.argv) != 3:
        print('usage: ingest <pdf> <slug-dir>', file=sys.stderr)
        sys.exit(1)

    pdf = Path(sys.argv[1]).resolve()
    slug_dir = Path(sys.argv[2]).resolve()
    out_dir = slug_dir / '1-paper-text'

    raw_dest = slug_dir / '0-raw.pdf'
    if pdf != raw_dest:
        shutil.copy2(pdf, raw_dest)

    (out_dir / 'img' / 'flat').mkdir(parents=True, exist_ok=True)

    md_text, _tool_used = convert(pdf, out_dir)
    md_text = augment_markdown_with_formulas(md_text, pdf)

    raw_sections = split_sections(md_text)
    main_sections, appended_papers = clean_sections(raw_sections)

    if not main_sections:
        print(f'error: no sections found in {pdf}', file=sys.stderr)
        sys.exit(1)

    _n_sec, _n_fig, _n_tbl = write_paper_output(main_sections, out_dir, md_text, pdf_path=pdf)

    appended_dir = out_dir / 'appended'
    if appended_dir.exists():
        shutil.rmtree(appended_dir, ignore_errors=True)
    if appended_papers:
        appended_dir.mkdir(parents=True, exist_ok=True)
        for i, (title, ap_sections) in enumerate(appended_papers, 1):
            ap_slug = slug(title) or f'paper-{i}'
            ap_dir = appended_dir / f'{i:02d}-{ap_slug}'
            ap_dir.mkdir(parents=True, exist_ok=True)
            ap_img_flat = ap_dir / 'img' / 'flat'
            ap_img_flat.mkdir(parents=True, exist_ok=True)
            src_flat = out_dir / 'img' / 'flat'
            if src_flat.exists():
                for img in src_flat.iterdir():
                    if img.is_file():
                        shutil.copy2(img, ap_img_flat / img.name)
            _ap_n_sec, _ap_n_fig, _ap_n_tbl = write_paper_output(
                ap_sections,
                ap_dir,
                ap_sections[0][1] if ap_sections else '',
                title_override=title,
                pdf_path=pdf,
            )

    shutil.rmtree(out_dir / '_marker_tmp', ignore_errors=True)
    shutil.rmtree(out_dir / 'img' / 'flat', ignore_errors=True)


if __name__ == '__main__':
    main()
