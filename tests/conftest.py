"""Top-level shared test fixtures and helpers.

Available everywhere (unit/ and e2e/ subtrees).
"""
import gc
import shutil
from pathlib import Path

import fitz
import pytest

# ── Shared constants ───────────────────────────────────────────────────────────

LONG_BODY = 'Long body text that passes all thresholds. ' * 20  # well over 400 chars

# ── Synthetic PDF builder ──────────────────────────────────────────────────────


def make_test_pdf(pdf_path: Path, pages: list[dict]) -> None:
    """Create a minimal test PDF with text and optional image content.

    Each page dict: {'text': str, 'images': [(x0,y0,x1,y1), ...]}
    """
    doc = fitz.open()
    for page_data in pages:
        page = doc.new_page(width=612, height=792)
        text = page_data.get('text', '')
        if text:
            page.insert_textbox(fitz.Rect(50, 50, 550, 750), text, fontsize=11)
        for img_rect in page_data.get('images', []):
            page.draw_rect(fitz.Rect(*img_rect), color=(0.5, 0.5, 0.5), fill=(0.5, 0.5, 0.5))
    doc.save(str(pdf_path))
    doc.close()
    del doc
    gc.collect()


# ── Marker availability ────────────────────────────────────────────────────────


def marker_available() -> bool:
    """True when marker-pdf is usable: GPU ≥ 4 GB VRAM + marker_single on PATH."""
    from paper_pdf_ingest.convert import detect_gpu_vram_gb

    return detect_gpu_vram_gb() >= 4.0 and shutil.which('marker_single') is not None


_marker_skip = pytest.mark.skipif(not marker_available(), reason='marker_single not available or GPU < 4GB')


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def test_data_dir() -> Path:
    return Path(__file__).resolve().parent / 'data'
