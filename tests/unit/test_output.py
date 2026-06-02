import tempfile
from pathlib import Path

from paper_pdf_ingest.output import build_index, write_paper_output, write_section_files

LONG_BODY = 'Long body text that passes all thresholds. ' * 20


class TestWriteSectionFiles:
    def test_creates_md_files(self):
        sections = [
            ('## Introduction', 'Intro body text.'),
            ('## Methods', 'Methods body text.'),
            ('## Results', 'Results body text.'),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            md_dir = Path(tmp) / 'md'
            info = write_section_files(sections, md_dir)

            assert len(info) == 3
            assert (md_dir / '01-introduction.md').exists()
            assert (md_dir / '02-methods.md').exists()
            assert (md_dir / '03-results.md').exists()

    def test_clears_existing_dir(self):
        sections = [('## Intro', 'Body.')]
        with tempfile.TemporaryDirectory() as tmp:
            md_dir = Path(tmp) / 'md'
            md_dir.mkdir(parents=True)
            (md_dir / 'old-file.md').write_text('stale')

            write_section_files(sections, md_dir)

            assert not (md_dir / 'old-file.md').exists()
            assert (md_dir / '01-intro.md').exists()

    def test_empty_heading_name(self):
        sections = [('', 'Preamble body text.')]
        with tempfile.TemporaryDirectory() as tmp:
            md_dir = Path(tmp) / 'md'
            info = write_section_files(sections, md_dir)
            assert info[0]['slug'] == 'body'
            assert (md_dir / '01-body.md').exists()

    def test_info_structure(self):
        sections = [('## Test Section', 'Body content.')]
        with tempfile.TemporaryDirectory() as tmp:
            md_dir = Path(tmp) / 'md'
            info = write_section_files(sections, md_dir)
            assert info[0]['idx'] == 1
            assert info[0]['heading'] == '## Test Section'
            assert info[0]['slug'] == 'test-section'
            assert info[0]['fname'] == '01-test-section.md'


class TestBuildIndex:
    def test_builds_index_table(self):
        sections = [('## Intro', f'See Figure 1 for details. And Table 1 shows results. {LONG_BODY}')]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            md_dir = out_dir / 'md'
            md_dir.mkdir(parents=True)
            write_section_files(sections, md_dir)
            (out_dir / 'img' / 'sec01').mkdir(parents=True)

            n_fig, n_tbl = build_index(out_dir, md_dir, sections, {})
            assert n_fig == 1
            assert n_tbl == 1
            assert (out_dir / 'INDEX.md').exists()
            content = (out_dir / 'INDEX.md').read_text(encoding='utf-8')
            assert 'Figure 1' in content
            assert 'Table 1' in content

    def test_build_index_dedupes(self):
        sections = [('## Intro', f'See Figure 1. And also Figure 1 again. {LONG_BODY}')]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            md_dir = out_dir / 'md'
            md_dir.mkdir(parents=True)
            write_section_files(sections, md_dir)
            (out_dir / 'img' / 'sec01').mkdir(parents=True)

            n_fig, _ = build_index(out_dir, md_dir, sections, {})
            assert n_fig == 1

    def test_build_index_with_figure_images(self):
        sections = [('## Results', f'As shown in Figure 3. {LONG_BODY}')]
        figure_images = {'Figure 3': 'img/sec01/page-04-figure-3.png'}
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            md_dir = out_dir / 'md'
            md_dir.mkdir(parents=True)
            write_section_files(sections, md_dir)

            _, _ = build_index(out_dir, md_dir, sections, figure_images)
            content = (out_dir / 'INDEX.md').read_text(encoding='utf-8')
            assert 'img/sec01/page-04-figure-3.png' in content


class TestWritePaperOutput:
    def test_writes_paper_md(self):
        sections = [
            ('', 'Some preamble text. ' * 10),
            ('## Introduction', LONG_BODY),
            ('## Conclusion', LONG_BODY),
        ]
        md_text = f'# My Paper\n\n## Introduction\n{LONG_BODY}\n\n## Conclusion\n{LONG_BODY}'
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            n_sec, _n_fig, _n_tbl = write_paper_output(sections, out_dir, md_text)

            assert n_sec == 2  # Introduction + Conclusion (preamble excluded)
            assert (out_dir / 'paper.md').exists()
            content = (out_dir / 'paper.md').read_text(encoding='utf-8')
            assert 'My Paper' in content
            assert '## Abstract' in content
            assert '## Sections' in content

    def test_title_override(self):
        sections = [('## Intro', LONG_BODY)]
        md_text = f'## Intro\n{LONG_BODY}'
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            write_paper_output(sections, out_dir, md_text, title_override='Custom Title')
            content = (out_dir / 'paper.md').read_text(encoding='utf-8')
            assert '# Custom Title' in content

    def test_creates_img_dirs(self):
        sections = [('## Intro', LONG_BODY)]
        md_text = f'## Intro\n{LONG_BODY}'
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            write_paper_output(sections, out_dir, md_text)
            assert (out_dir / 'img' / 'flat').exists()
            assert (out_dir / 'md').exists()
