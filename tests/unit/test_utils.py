import pytest

from paper_pdf_ingest.utils import slug, strip_formatting


class TestSlug:
    def test_basic_heading(self):
        assert slug('## Introduction') == 'introduction'

    def test_strips_leading_hashes(self):
        assert slug('# Title With Spaces') == 'title-with-spaces'

    def test_special_characters_replaced(self):
        assert slug('## 1. Related Work & Background') == '1-related-work-background'

    def test_maxlen_truncation(self):
        # truncates to 20 chars, trailing dash stripped
        assert slug('## Very Long Section Title That Exceeds Thirty Characters', maxlen=20) == 'very-long-section-ti'

    def test_trailing_dash_removed(self):
        assert slug('## Trailing---') == 'trailing'

    def test_empty_heading(self):
        assert slug('') == ''

    def test_multiple_hash_levels(self):
        assert slug('### Deep Subsection', maxlen=20) == 'deep-subsection'


class TestStripFormatting:
    def test_removes_images(self):
        # strip_formatting removes spaces too (in \s class)
        result = strip_formatting('text ![alt](path.png) text')
        assert result == 'texttext'
        assert 'alt' not in result
        assert 'path.png' not in result

    def test_removes_links(self):
        result = strip_formatting('click [here](url) now')
        assert result == 'clickherenow'
        assert 'url' not in result

    def test_removes_markdown_chars(self):
        result = strip_formatting('**bold** _italic_ `code` | pipe # hash > quote')
        assert 'bold' in result
        assert 'italic' in result
        assert 'code' in result
        assert '*' not in result
        assert '|' not in result
        assert '#' not in result
        assert '>' not in result

    def test_empty_string(self):
        assert strip_formatting('') == ''

    @pytest.mark.parametrize(
        ('text', 'expected'),
        [
            ('![fig](a.png)', ''),
            ('[link](http://x)', 'link'),
            ('**bold**', 'bold'),
            ('', ''),
        ],
    )
    def test_strip_parametrized(self, text, expected):
        assert strip_formatting(text) == expected
