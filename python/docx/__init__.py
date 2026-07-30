"""A standalone python-docx-compatible subset accelerated by Mojo."""

from .api import Document
from .shared import Cm, Emu, Inches, Length, Mm, Pt, RGBColor

__all__ = [
    "Document",
    "Length",
    "Inches",
    "Cm",
    "Mm",
    "Pt",
    "Emu",
    "RGBColor",
]
__version__ = "0.1.0"
