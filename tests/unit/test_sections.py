from ..conftest import LONG_BODY
from paper_pdf_ingest.sections import (
    _is_paper_boundary,
    _paper_title_from_sections,
    classify_section,
    clean_sections,
    split_sections,
)

SAMPLE_MD = f"""# Title of Paper

Some preamble text here.

## Abstract

{LONG_BODY}

## Introduction

{LONG_BODY}

## Related Work

{LONG_BODY}

## Methodology

{LONG_BODY}

## Experiments

{LONG_BODY}

## Conclusion

{LONG_BODY}
"""


class TestSplitSections:
    def test_splits_level2_headings(self):
        sections = split_sections(SAMPLE_MD)
        assert len(sections) >= 6
        headings = [h for h, _ in sections]
        assert '' in headings
        assert any('Abstract' in h for h in headings)
        assert any('Introduction' in h for h in headings)
        assert any('Methodology' in h for h in headings)
        assert any('Conclusion' in h for h in headings)

    def test_preamble_is_empty_heading(self):
        sections = split_sections(SAMPLE_MD)
        assert sections[0][0] == ''
        assert len(sections[0][1]) > 0

    def test_fallback_for_few_headings(self):
        md = f"""# Title
Some text here.
## Section A
{LONG_BODY}
"""
        sections = split_sections(md)
        assert len(sections) >= 1
        combined_text = ' '.join(b for _, b in sections)
        assert 'Content' not in combined_text  # fallback uses different body

    def test_single_section_returns_whole(self):
        md = 'Just plain text without any real headings.\n\nMore text here.'
        sections = split_sections(md)
        assert len(sections) == 1
        assert sections[0][0] == ''
        assert 'plain text' in sections[0][1]

    def test_level1_heading_split(self):
        md = '\n'.join([
            f'# H1 First\n{LONG_BODY}\n',
            f'# H1 Second\n{LONG_BODY}\n',
            f'# H1 Third\n{LONG_BODY}\n',
            f'# H1 Fourth\n{LONG_BODY}\n',
        ])
        sections = split_sections(md)
        headings = [h for h, _ in sections if h]
        assert len(headings) >= 3


class TestClassifySection:
    def test_keep_normal_section(self):
        body = LONG_BODY
        assert classify_section('## Model Architecture', body) == 'keep'

    def test_discard_short_body(self):
        assert classify_section('## Short', 'tiny') == 'discard'

    def test_merge_up_diagram_label(self):
        assert classify_section('## (a)', 'Some diagram caption text here that is long enough') == 'merge-up'

    def test_merge_up_diagram_label_b(self):
        assert (
            classify_section('(b)', 'Another diagram caption with enough text to pass the minimum length check')
            == 'merge-up'
        )

    def test_discard_diagram_fragment_short(self):
        heading = '**V abc**'
        body = 'Some short figure caption remnants here.'
        assert classify_section(heading, body) == 'discard'


class TestIsPaperBoundary:
    def test_low_index_never_boundary(self):
        assert _is_paper_boundary('## Anything', 'Some body text', idx=0) is False
        assert _is_paper_boundary('## Anything', 'Some body text', idx=4) is False

    def test_not_boundary_for_normal_section(self):
        assert _is_paper_boundary('## Experiments', 'Normal experimental results text.', idx=5) is False

    def test_ieee_copyright_boundary(self):
        heading = 'IEEE Conference Paper'
        body = f'© 2024 IEEE. Personal use is permitted. {LONG_BODY}'
        assert _is_paper_boundary(heading, body, idx=5) is True

    def test_author_affiliation_boundary(self):
        heading = 'Author Information'
        body = 'John Smith, Student Member, IEEE\nUniversity of Example\njsmith@example.edu\n'
        assert _is_paper_boundary(heading, body, idx=5) is True


class TestPaperTitleFromSections:
    def test_extracts_first_heading(self):
        sections = [('## My Paper Title', 'body'), ('## Other', 'more body')]
        assert _paper_title_from_sections(sections) == 'My Paper Title'

    def test_fallback_untitled(self):
        assert _paper_title_from_sections([]) == 'untitled'

    def test_strips_hash_prefix(self):
        sections = [('###  Deep Title  ', 'body')]
        assert _paper_title_from_sections(sections) == 'Deep Title'


class TestCleanSections:
    def test_removes_noise_sections(self):
        sections = [
            ('', 'Preamble text that is long enough. ' * 5),
            ('## Model Overview', LONG_BODY),
            ('## (a)', 'Diagram label body text that is long enough to pass the merge-up threshold check.'),
            ('## Short', 'tiny'),
        ]
        main, appended = clean_sections(sections)
        assert len(main) >= 2
        assert len(appended) == 0

    def test_no_false_appended_papers(self):
        sections = split_sections(SAMPLE_MD)
        main, appended = clean_sections(sections)
        assert len(main) > 0
        assert len(appended) == 0

    def test_handles_empty_sections(self):
        main, appended = clean_sections([])
        assert main == []
        assert appended == []
