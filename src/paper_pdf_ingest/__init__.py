__version__ = '0.1.0'

from .convert import choose_tool, convert, detect_gpu_vram_gb
from .figures import build_figure_page_map, crop_figure, render_figure_pages
from .output import build_index, route_images, write_paper_output, write_section_files
from .sections import classify_section, clean_sections, split_sections
from .utils import extract_title_from_preamble, slug, strip_formatting

__all__ = [
    'build_figure_page_map',
    'build_index',
    'choose_tool',
    'classify_section',
    'clean_sections',
    'convert',
    'crop_figure',
    'detect_gpu_vram_gb',
    'extract_title_from_preamble',
    'render_figure_pages',
    'route_images',
    'slug',
    'split_sections',
    'strip_formatting',
    'write_paper_output',
    'write_section_files',
]
