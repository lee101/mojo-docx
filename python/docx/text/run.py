from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .._xml import child, element, on_off, set_on_off, val
from ..enum.text import WD_BREAK
from ..oxml.ns import qn
from ..shared import Length, Pt, RGBColor

_SPLIT_TEXT = re.compile(r"(\t|\r\n|\r|\n)")


class ColorFormat:
    def __init__(self, run: "Run"):
        self._run = run

    @property
    def rgb(self) -> RGBColor | None:
        color = self._run._rPr.find(qn("w:color"))
        value = val(color)
        if value is None or value.lower() == "auto":
            return None
        try:
            return RGBColor.from_string(value)
        except ValueError:
            return None

    @rgb.setter
    def rgb(self, value: RGBColor | tuple[int, int, int] | None) -> None:
        self._run._document._mark_dirty()
        rpr = self._run._rPr
        color = rpr.find(qn("w:color"))
        if value is None:
            if color is not None:
                rpr.remove(color)
            return
        if color is None:
            color = ET.SubElement(rpr, qn("w:color"))
        color.set(qn("w:val"), str(RGBColor(*value)))


class Font:
    def __init__(self, run: "Run"):
        self._run = run
        self.color = ColorFormat(run)

    @property
    def name(self) -> str | None:
        fonts = self._run._rPr.find(qn("w:rFonts"))
        return None if fonts is None else fonts.get(qn("w:ascii"))

    @name.setter
    def name(self, value: str | None) -> None:
        self._run._document._mark_dirty()
        rpr = self._run._rPr
        fonts = rpr.find(qn("w:rFonts"))
        if value is None:
            if fonts is not None:
                rpr.remove(fonts)
            return
        if fonts is None:
            fonts = ET.SubElement(rpr, qn("w:rFonts"))
        fonts.set(qn("w:ascii"), value)
        fonts.set(qn("w:hAnsi"), value)

    @property
    def size(self) -> Length | None:
        size = self._run._rPr.find(qn("w:sz"))
        value = val(size)
        return None if value is None else Pt(float(value) / 2)

    @size.setter
    def size(self, value: Length | None) -> None:
        self._run._document._mark_dirty()
        rpr = self._run._rPr
        size = rpr.find(qn("w:sz"))
        if value is None:
            if size is not None:
                rpr.remove(size)
            return
        if size is None:
            size = ET.SubElement(rpr, qn("w:sz"))
        size.set(qn("w:val"), str(int(round(Length(value).pt * 2))))

    @property
    def bold(self) -> bool | None:
        return self._run.bold

    @bold.setter
    def bold(self, value: bool | None) -> None:
        self._run.bold = value

    @property
    def italic(self) -> bool | None:
        return self._run.italic

    @italic.setter
    def italic(self, value: bool | None) -> None:
        self._run.italic = value

    @property
    def underline(self) -> bool | None:
        return self._run.underline

    @underline.setter
    def underline(self, value: bool | None) -> None:
        self._run.underline = value


class Run:
    def __init__(self, element: ET.Element, parent):
        self._element = self._r = element
        self._parent = parent
        self._document = parent._document
        self.font = Font(self)

    @property
    def _rPr(self) -> ET.Element:
        return child(self._r, "w:rPr", first=True)

    @property
    def text(self) -> str:
        pieces: list[str] = []
        for node in self._r:
            if node.tag == qn("w:t"):
                pieces.append(node.text or "")
            elif node.tag == qn("w:tab"):
                pieces.append("\t")
            elif node.tag in {qn("w:br"), qn("w:cr")}:
                pieces.append("\n")
            elif node.tag == qn("w:noBreakHyphen"):
                pieces.append("\N{NON-BREAKING HYPHEN}")
        return "".join(pieces)

    @text.setter
    def text(self, text: str | None) -> None:
        self._document._mark_dirty()
        for node in list(self._r):
            if node.tag != qn("w:rPr"):
                self._r.remove(node)
        if text is None:
            return
        for piece in _SPLIT_TEXT.split(str(text)):
            if not piece:
                continue
            if piece == "\t":
                self._r.append(element("w:tab"))
            elif piece in {"\n", "\r", "\r\n"}:
                self._r.append(element("w:br"))
            else:
                text_node = element("w:t")
                text_node.text = piece
                if piece[:1].isspace() or piece[-1:].isspace():
                    text_node.set(
                        "{http://www.w3.org/XML/1998/namespace}space", "preserve"
                    )
                self._r.append(text_node)

    @property
    def bold(self) -> bool | None:
        return on_off(self._rPr, "w:b")

    @bold.setter
    def bold(self, value: bool | None) -> None:
        self._document._mark_dirty()
        set_on_off(self._rPr, "w:b", value)

    @property
    def italic(self) -> bool | None:
        return on_off(self._rPr, "w:i")

    @italic.setter
    def italic(self, value: bool | None) -> None:
        self._document._mark_dirty()
        set_on_off(self._rPr, "w:i", value)

    @property
    def underline(self) -> bool | None:
        node = self._rPr.find(qn("w:u"))
        if node is None:
            return None
        return val(node, "single") not in {"0", "false", "none", "off"}

    @underline.setter
    def underline(self, value: bool | None) -> None:
        self._document._mark_dirty()
        rpr = self._rPr
        node = rpr.find(qn("w:u"))
        if value is None:
            if node is not None:
                rpr.remove(node)
            return
        if node is None:
            node = ET.SubElement(rpr, qn("w:u"))
        node.set(qn("w:val"), "single" if value else "none")

    @property
    def style(self):
        node = self._rPr.find(qn("w:rStyle"))
        style_id = val(node)
        return None if style_id is None else self._document.styles[style_id]

    @style.setter
    def style(self, value) -> None:
        self._document._mark_dirty()
        rpr = self._rPr
        node = rpr.find(qn("w:rStyle"))
        if value is None:
            if node is not None:
                rpr.remove(node)
            return
        style = self._document.styles.resolve(value)
        if node is None:
            node = ET.SubElement(rpr, qn("w:rStyle"))
        node.set(qn("w:val"), style.style_id)

    def add_break(self, break_type: WD_BREAK | None = None) -> None:
        self._document._mark_dirty()
        node = element("w:br")
        if break_type in {WD_BREAK.PAGE, WD_BREAK.COLUMN}:
            node.set(
                qn("w:type"),
                "page" if break_type == WD_BREAK.PAGE else "column",
            )
        elif break_type in {
            WD_BREAK.LINE_CLEAR_LEFT,
            WD_BREAK.LINE_CLEAR_RIGHT,
            WD_BREAK.LINE_CLEAR_ALL,
        }:
            clear = {
                WD_BREAK.LINE_CLEAR_LEFT: "left",
                WD_BREAK.LINE_CLEAR_RIGHT: "right",
                WD_BREAK.LINE_CLEAR_ALL: "all",
            }[break_type]
            node.set(qn("w:clear"), clear)
        self._r.append(node)

    def add_picture(self, image_path_or_stream, width=None, height=None):
        return self._document._add_picture(
            self, image_path_or_stream, width=width, height=height
        )

    def clear(self) -> "Run":
        self.text = None
        return self
