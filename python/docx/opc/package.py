from __future__ import annotations


class OpcPackage:
    """Small compatibility facade around a document's OPC parts."""

    def __init__(self, document):
        self._document = document

    @classmethod
    def open(cls, pkg_file):
        from ..api import Document

        return Document(pkg_file).part.package

    def save(self, pkg_file) -> None:
        self._document.save(pkg_file)

    @property
    def parts(self):
        return tuple(self._document._parts)
