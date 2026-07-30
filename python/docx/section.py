from __future__ import annotations

import xml.etree.ElementTree as ET

from ._xml import child
from .enum.section import WD_ORIENT
from .oxml.ns import qn
from .shared import Length


class Section:
    def __init__(self, sect_pr: ET.Element, document):
        self._sectPr = sect_pr
        self._document = document

    def _page_size(self) -> ET.Element:
        return child(self._sectPr, "w:pgSz")

    def _margins(self) -> ET.Element:
        return child(self._sectPr, "w:pgMar")

    def _twip_get(self, node: ET.Element, attr: str) -> Length | None:
        value = node.get(qn(attr))
        return None if value is None else Length(int(value) * 635)

    def _twip_set(self, node: ET.Element, attr: str, value: Length) -> None:
        self._document._mark_dirty()
        node.set(qn(attr), str(Length(value).twips))

    @property
    def page_width(self) -> Length | None:
        return self._twip_get(self._page_size(), "w:w")

    @page_width.setter
    def page_width(self, value: Length) -> None:
        self._twip_set(self._page_size(), "w:w", value)

    @property
    def page_height(self) -> Length | None:
        return self._twip_get(self._page_size(), "w:h")

    @page_height.setter
    def page_height(self, value: Length) -> None:
        self._twip_set(self._page_size(), "w:h", value)

    @property
    def orientation(self) -> WD_ORIENT:
        return (
            WD_ORIENT.LANDSCAPE
            if self._page_size().get(qn("w:orient")) == "landscape"
            else WD_ORIENT.PORTRAIT
        )

    @orientation.setter
    def orientation(self, value: WD_ORIENT) -> None:
        self._document._mark_dirty()
        page_size = self._page_size()
        if WD_ORIENT(value) == WD_ORIENT.LANDSCAPE:
            page_size.set(qn("w:orient"), "landscape")
        else:
            page_size.attrib.pop(qn("w:orient"), None)

    def _margin_property(name: str):
        def getter(self):
            return self._twip_get(self._margins(), f"w:{name}")

        def setter(self, value):
            self._twip_set(self._margins(), f"w:{name}", value)

        return property(getter, setter)

    top_margin = _margin_property("top")
    bottom_margin = _margin_property("bottom")
    left_margin = _margin_property("left")
    right_margin = _margin_property("right")
    header_distance = _margin_property("header")
    footer_distance = _margin_property("footer")
    gutter = _margin_property("gutter")
