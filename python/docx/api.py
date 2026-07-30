from __future__ import annotations

from .document import Document as _Document


def Document(docx=None) -> _Document:
    """Return a document loaded from `docx`, or a new blank document."""
    return _Document.open(docx)
