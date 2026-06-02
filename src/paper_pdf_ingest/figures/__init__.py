"""figures — PDF figure/table/equation extraction and rendering."""
from ._crop import crop_figure
from ._map import build_equation_page_map, build_figure_page_map, build_page_section_map
from ._render import render_equation_images, render_figure_pages

__all__ = [
    'build_figure_page_map',
    'build_page_section_map',
    'build_equation_page_map',
    'crop_figure',
    'render_figure_pages',
    'render_equation_images',
]
