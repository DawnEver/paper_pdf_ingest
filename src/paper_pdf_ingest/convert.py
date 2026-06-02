import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── GPU detection ────────────────────────────────────────────────────────────


def detect_gpu_vram_gb() -> float:
    """Return available VRAM in GB, or 0 if no usable GPU found."""
    # Metal (Apple Silicon) — surya (used by marker) does not support MPS and
    # falls back to CPU, making marker slower than pymupdf4llm on Apple hardware.
    # Return 0 so choose_tool() always picks pymupdf4llm on Mac.
    try:
        out = subprocess.check_output(['system_profiler', 'SPDisplaysDataType'], text=True, timeout=5)
        if any('Chipset Model: Apple' in line for line in out.splitlines()):
            return 0.0
        for line in out.splitlines():
            m = re.search(r'VRAM.*?(\d+)\s*(GB|MB)', line, re.IGNORECASE)
            if m:
                v = float(m.group(1))
                return v if m.group(2).upper() == 'GB' else v / 1024
    except Exception:
        pass

    # CUDA
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.get_device_properties(0).total_memory / 1e9
    except Exception:
        pass

    # nvidia-smi
    try:
        out = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'],
            text=True,
            timeout=5,
        )
        mb = float(out.strip().splitlines()[0])
        return mb / 1024
    except Exception:
        pass

    return 0.0


def _find_marker_single() -> str | None:
    """Return path to marker_single binary, or None."""
    exe = shutil.which('marker_single')
    if exe:
        return exe
    # Check next to the running python (venv Scripts/ not always on PATH)
    exe_dir = os.path.dirname(sys.executable)
    exe_name = 'marker_single.exe' if os.name == 'nt' else 'marker_single'
    candidate = os.path.join(exe_dir, exe_name)
    if os.path.isfile(candidate):
        return candidate
    # Check sys.prefix bin
    candidate = os.path.join(sys.prefix, 'bin', 'marker_single')
    if os.path.isfile(candidate):
        return candidate
    return None


def choose_tool() -> str:
    vram = detect_gpu_vram_gb()
    if vram >= 4 and _find_marker_single():
        return 'marker'
    return 'pymupdf4llm'


# ── Converters ───────────────────────────────────────────────────────────────


def _run_marker(pdf: Path, out_dir: Path) -> str:
    """Run marker_single; return markdown text."""
    tmp = out_dir / '_marker_tmp'
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        marker = _find_marker_single()
        if not marker:
            msg = 'marker_single not found'
            raise FileNotFoundError(msg)
        subprocess.run(
            [marker, str(pdf), '--output_format', 'markdown', '--output_dir', str(tmp)],
            check=True,
        )
        md_files = list(tmp.rglob('*.md'))
        if not md_files:
            msg = 'marker produced no markdown'
            raise RuntimeError(msg)
        text = md_files[0].read_text(encoding='utf-8')
        for img in list(tmp.rglob('*.png')) + list(tmp.rglob('*.jpeg')) + list(tmp.rglob('*.jpg')):
            dest = out_dir / 'img' / 'flat' / img.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img, dest)
        return text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run_pymupdf4llm(pdf: Path, out_dir: Path) -> str:
    import pymupdf4llm

    (out_dir / 'img' / 'flat').mkdir(parents=True, exist_ok=True)
    return str(pymupdf4llm.to_markdown(str(pdf), write_images=True, image_path=str(out_dir / 'img' / 'flat')))


def convert(pdf: Path, out_dir: Path) -> tuple[str, str]:
    """Return (markdown_text, tool_used)."""
    tool = choose_tool()
    if tool == 'marker':
        return _run_marker(pdf, out_dir), 'marker'
    return _run_pymupdf4llm(pdf, out_dir), 'pymupdf4llm'


def detect_formula_regions(pdf_path: Path) -> list[dict]:
    """Detect formula regions across all pages of a PDF.

    Uses PyMuPDF to find blocks of text/drawing that look like formulas
    (isolated from body text, centered or indented, short lines with math symbols).

    Returns list of dicts with keys: page (0-based), bbox (x0,y0,x1,y1), text.
    """
    import fitz

    formulas: list[dict] = []
    doc = fitz.open(str(pdf_path))

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']

        for blk in blocks:
            if blk['type'] != 0:
                continue
            blk_text = ''.join(
                span.get('text', '') for line in blk.get('lines', []) for span in line.get('spans', [])
            )
            blk_text = blk_text.strip()
            if not blk_text or len(blk_text) > 500:
                continue

            # Formula heuristics: short blocks with math symbols
            math_score = sum(1 for c in blk_text if c in '=+-*/()[]{}^_∫∑∏√∂∞≈≠≤≥±×÷')
            if math_score >= 2 and len(blk_text) < 200:
                bbox = blk['bbox']
                formulas.append({
                    'page': page_num,
                    'bbox': (bbox[0], bbox[1], bbox[2], bbox[3]),
                    'text': blk_text,
                })

    doc.close()
    return formulas


def augment_markdown_with_formulas(md_text: str, pdf_path: Path) -> str:
    """Insert extracted formula text alongside formula images in markdown.

    For each detected formula region, if the corresponding formula image
    appears in the markdown, adds a code block with the LaTeX/plain text
    below the image.
    """
    try:
        formulas = detect_formula_regions(pdf_path)
    except Exception:
        return md_text

    if not formulas:
        return md_text

    lines = md_text.split('\n')
    # Build a map of page→formula texts for quick lookup
    page_formulas: dict[int, list[str]] = {}
    for f in formulas:
        page_formulas.setdefault(f['page'], []).append(f['text'])

    result: list[str] = []
    for line in lines:
        result.append(line)
        # Check if this line is a formula image (short alt text, image from PDF page)
        img_m = re.match(r'!\[([^\]]{0,20})\]\(([^)]*?(\d{4})[^)]*)\)', line.strip())
        if img_m:
            alt = img_m.group(1)
            page_str = img_m.group(3)
            if len(alt) <= 10 and page_str:
                try:
                    page_num = int(page_str) - 1  # filenames use 1-based page numbers
                except ValueError:
                    page_num = -1
                if page_num in page_formulas and page_formulas[page_num]:
                    formula_text = page_formulas[page_num].pop(0)
                    if formula_text and formula_text != alt:
                        result.append(f'```math\n{formula_text}\n```')

    return '\n'.join(result)
