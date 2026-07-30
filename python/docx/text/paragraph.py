from __future__ import annotations

import xml.etree.ElementTree as ET

from .._xml import child, element, val
from ..enum.text import WD_ALIGN_PARAGRAPH
from ..oxml.ns import qn
from ..shared import Length
from .run import Run

_ALIGN_TO_XML = {
    WD_ALIGN_PARAGRAPH.LEFT: "left",
    WD_ALIGN_PARAGRAPH.CENTER: "center",
    WD_ALIGN_PARAGRAPH.RIGHT: "right",
    WD_ALIGN_PARAGRAPH.JUSTIFY: "both",
    WD_ALIGN_PARAGRAPH.DISTRIBUTE: "distribute",
}
_XML_TO_ALIGN = {value: key for key, value in _ALIGN_TO_XML.items()}


class ParagraphFormat:
    def __init__(self, paragraph: "Paragraph"):
        self._paragraph = paragraph

    @property
    def alignment(self):
        return self._paragraph.alignment

    @alignment.setter
    def alignment(self, value):
        self._paragraph.alignment = value

    def _spacing(self) -> ET.Element:
        return child(self._paragraph._pPr, "w:spacing")

    def _indent(self) -> ET.Element:
        return child(self._paragraph._pPr, "w:ind")

    def _length_get(self, parent: ET.Element, name: str) -> Length | None:
        raw = parent.get(qn(name))
        return None if raw is None else Length(int(raw) * 635)

    def _length_set(
        self, parent: ET.Element, name: str, value: Length | None
    ) -> None:
        self._paragraph._document._mark_dirty()
        key = qn(name)
        if value is None:
            parent.attrib.pop(key, None)
        else:
            parent.set(key, str(Length(value).twips))

    @property
    def left_indent(self) -> Length | None:
        return self._length_get(self._indent(), "w:left")

    @left_indent.setter
    def left_indent(self, value: Length | None) -> None:
        self._length_set(self._indent(), "w:left", value)

    @property
    def right_indent(self) -> Length | None:
        return self._length_get(self._indent(), "w:right")

    @right_indent.setter
    def right_indent(self, value: Length | None) -> None:
        self._length_set(self._indent(), "w:right", value)

    @property
    def first_line_indent(self) -> Length | None:
        indent = self._indent()
        hanging = self._length_get(indent, "w:hanging")
        if hanging is not None:
            return Length(-hanging)
        return self._length_get(indent, "w:firstLine")

    @first_line_indent.setter
    def first_line_indent(self, value: Length | None) -> None:
        self._paragraph._document._mark_dirty()
        indent = self._indent()
        indent.attrib.pop(qn("w:firstLine"), None)
        indent.attrib.pop(qn("w:hanging"), None)
        if value is None:
            return
        name = "w:hanging" if value < 0 else "w:firstLine"
        self._length_set(indent, name, Length(abs(value)))

    @property
    def space_before(self) -> Length | None:
        return self._length_get(self._spacing(), "w:before")

    @space_before.setter
    def space_before(self, value: Length | None) -> None:
        self._length_set(self._spacing(), "w:before", value)

    @property
    def space_after(self) -> Length | None:
        return self._length_get(self._spacing(), "w:after")

    @space_after.setter
    def space_after(self, value: Length | None) -> None:
        self._length_set(self._spacing(), "w:after", value)


class Paragraph:
    def __init__(self, element: ET.Element, parent):
        self._element = self._p = element
        self._parent = parent
        self._document = parent._document if hasattr(parent, "_document") else parent
        self.paragraph_format = ParagraphFormat(self)

    @property
    def _pPr(self) -> ET.Element:
        return child(self._p, "w:pPr", first=True)

    @property
    def runs(self) -> list[Run]:
        return [
            Run(node, self)
            for node in self._p.iter(qn("w:r"))
            if node is not self._p
        ]

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)

    @text.setter
    def text(self, value: str) -> None:
        self.clear()
        self.add_run(value)

    def add_run(self, text: str | None = None, style=None) -> Run:
        self._document._mark_dirty()
        node = element("w:r")
        self._p.append(node)
        run = Run(node, self)
        if text is not None:
            run.text = text
        if style is not None:
            run.style = style
        return run

    def clear(self) -> "Paragraph":
        self._document._mark_dirty()
        for node in list(self._p):
            if node.tag != qn("w:pPr"):
                self._p.remove(node)
        return self

    @property
    def alignment(self) -> WD_ALIGN_PARAGRAPH | None:
        node = self._pPr.find(qn("w:jc"))
        return _XML_TO_ALIGN.get(val(node))

    @alignment.setter
    def alignment(self, value: WD_ALIGN_PARAGRAPH | int | None) -> None:
        self._document._mark_dirty()
        ppr = self._pPr
        node = ppr.find(qn("w:jc"))
        if value is None:
            if node is not None:
                ppr.remove(node)
            return
        aligned = WD_ALIGN_PARAGRAPH(value)
        if node is None:
            node = ET.SubElement(ppr, qn("w:jc"))
        node.set(qn("w:val"), _ALIGN_TO_XML[aligned])

    @property
    def style(self):
        node = self._pPr.find(qn("w:pStyle"))
        style_id = val(node, "Normal")
        try:
            return self._document.styles[style_id]
        except KeyError:
            return None

    @style.setter
    def style(self, value) -> None:
        self._document._mark_dirty()
        ppr = self._pPr
        node = ppr.find(qn("w:pStyle"))
        if value is None:
            if node is not None:
                ppr.remove(node)
            return
        style = self._document.styles.resolve(value)
        if node is None:
            node = ET.SubElement(ppr, qn("w:pStyle"))
        node.set(qn("w:val"), style.style_id)

    def insert_paragraph_before(self, text: str | None = None, style=None) -> "Paragraph":
        self._document._mark_dirty()
        parent = getattr(self._parent, "_container_element", self._parent._element)
        index = list(parent).index(self._p)
        node = element("w:p")
        parent.insert(index, node)
        paragraph = Paragraph(node, self._parent)
        if text:
            paragraph.add_run(text)
        if style is not None:
            paragraph.style = style
        return paragraph
