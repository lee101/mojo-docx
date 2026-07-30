from __future__ import annotations

import xml.etree.ElementTree as ET

from .oxml.ns import qn
from .shared import Length


class InlineShape:
    def __init__(self, inline: ET.Element, document):
        self._inline = inline
        self._document = document

    def _extent(self) -> ET.Element:
        extent = self._inline.find(qn("wp:extent"))
        if extent is None:
            extent = ET.SubElement(self._inline, qn("wp:extent"))
        return extent

    @property
    def width(self) -> Length:
        return Length(int(self._extent().get("cx", "0")))

    @width.setter
    def width(self, value: Length) -> None:
        self._document._mark_dirty()
        self._extent().set("cx", str(int(value)))

    @property
    def height(self) -> Length:
        return Length(int(self._extent().get("cy", "0")))

    @height.setter
    def height(self, value: Length) -> None:
        self._document._mark_dirty()
        self._extent().set("cy", str(int(value)))


class InlineShapeCollection:
    def __init__(self, document):
        self._document = document

    def __iter__(self):
        for inline in self._document._element.iter(qn("wp:inline")):
            yield InlineShape(inline, self._document)

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __getitem__(self, index: int) -> InlineShape:
        return list(self)[index]
