from pathlib import Path

import pytest

try:
    import fitz  # noqa: F401

    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


@pytest.mark.skipif(not HAS_FITZ, reason='PyMuPDF not installed')
class TestFigurePageMap:
    def test_nonexistent_pdf_raises(self):
        from paper_pdf_ingest.figures import build_figure_page_map

        with pytest.raises(Exception):
            build_figure_page_map(Path('/nonexistent/path.pdf'))
