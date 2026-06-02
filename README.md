# paper_pdf_ingest

Python library that converts academic paper PDFs into per-section markdown files and cropped figure/table images — designed to feed LLM-based review pipelines.

## Features

- **Auto-selects converter**: uses [marker-pdf](https://github.com/VikParuchuri/marker) (GPU ≥ 4 GB) or [pymupdf4llm](https://github.com/pymupdf/RAG) (CPU fallback)
- **Section splitting**: handles both markdown-headed and Roman-numeral (IEEE 2-column) layouts
- **Figure & table cropping**: tight bounding-box crops per label, rendered as PNG
- **Equation augmentation**: detects and inlines formula text alongside images
- **Multi-paper PDFs**: splits appended conference/journal versions into separate subtrees
- **Clean output**: removes raw converter artefacts, routes images to per-section directories

## Output layout

```
<slug>/
  0-raw.pdf
  1-paper-text/
    paper.md          ← title + abstract + section index
    md/               ← 01-intro.md, 02-method.md, …
    img/
      sec01/          ← images owned by section 01
      sec02/
      orphan/         ← unreferenced images
    INDEX.md          ← figure/table number ↔ file mapping
    appended/         ← additional papers bundled in the PDF
```

## Installation

Requires Python 3.12+.

```bash
pip install git+https://github.com/DawnEver/paper_pdf_ingest.git
```

Or editable install for development:

```bash
git clone https://github.com/DawnEver/paper_pdf_ingest.git
cd paper_pdf_ingest
uv sync --all-extras   # installs dev deps
```

## Usage

### CLI

```bash
ingest path/to/paper.pdf path/to/output-slug/
```

### Python API

```python
from paper_pdf_ingest import convert, split_sections, clean_sections, write_paper_output
from pathlib import Path

pdf = Path("paper.pdf")
out = Path("output/my-paper/1-paper-text")
out.mkdir(parents=True, exist_ok=True)

md_text, tool = convert(pdf, out)
sections, appended = clean_sections(split_sections(md_text))
write_paper_output(sections, out, md_text, pdf_path=pdf)
```

## Development

```bash
uv sync --all-extras
uv run pytest           # run tests
make test-cov           # tests + HTML coverage report
make lint               # ruff check + format check
make fmt                # auto-fix formatting
```

Unit tests live in `tests/unit/`; end-to-end tests (require real PDFs) in `tests/e2e/`.

## Requirements

| Dependency | Purpose |
|---|---|
| `pymupdf` | PDF parsing and rendering |
| `pymupdf4llm` | Markdown conversion (CPU path) |
| `pdfplumber` | Supplementary text extraction |
| `marker-pdf` *(optional)* | High-quality conversion on GPU ≥ 4 GB |

## License

MIT
