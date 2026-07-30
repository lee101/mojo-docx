from __future__ import annotations

import xml.etree.ElementTree as ET

from ._xml import child, direct_children, element, val
from .oxml.ns import qn
from .shared import Length
from .text.paragraph import Paragraph


class _Cell:
    def __init__(self, element: ET.Element, table: "Table"):
        self._element = self._tc = element
        self._parent = table
        self._document = table._document

    @property
    def paragraphs(self) -> list[Paragraph]:
        return [
            Paragraph(node, self)
            for node in direct_children(self._tc, "w:p")
        ]

    @property
    def tables(self) -> list["Table"]:
        return [
            Table(node, self)
            for node in direct_children(self._tc, "w:tbl")
        ]

    @property
    def text(self) -> str:
        return "\n".join(paragraph.text for paragraph in self.paragraphs)

    @text.setter
    def text(self, value: str) -> None:
        self._document._mark_dirty()
        for node in list(self._tc):
            if node.tag in {qn("w:p"), qn("w:tbl")}:
                self._tc.remove(node)
        paragraph = Paragraph(element("w:p"), self)
        self._tc.append(paragraph._p)
        paragraph.add_run(value)

    def add_paragraph(self, text: str = "", style=None) -> Paragraph:
        self._document._mark_dirty()
        node = element("w:p")
        self._tc.append(node)
        paragraph = Paragraph(node, self)
        if text:
            paragraph.add_run(text)
        if style is not None:
            paragraph.style = style
        return paragraph

    def add_table(self, rows: int, cols: int) -> "Table":
        self._document._mark_dirty()
        table = Table._new(self._document, rows, cols, parent=self)
        self._tc.append(table._tbl)
        self._tc.append(element("w:p"))
        return table

    @property
    def width(self) -> Length | None:
        width = child(self._tc, "w:tcPr", first=True).find(qn("w:tcW"))
        raw = None if width is None else width.get(qn("w:w"))
        return None if raw is None else Length(int(raw) * 635)

    @width.setter
    def width(self, value: Length) -> None:
        self._document._mark_dirty()
        tcpr = child(self._tc, "w:tcPr", first=True)
        width = tcpr.find(qn("w:tcW"))
        if width is None:
            width = ET.SubElement(tcpr, qn("w:tcW"))
        width.set(qn("w:w"), str(Length(value).twips))
        width.set(qn("w:type"), "dxa")


class _Row:
    def __init__(self, element: ET.Element, table: "Table"):
        self._element = self._tr = element
        self._parent = table
        self._document = table._document

    @property
    def cells(self) -> tuple[_Cell, ...]:
        return tuple(
            _Cell(node, self._parent)
            for node in direct_children(self._tr, "w:tc")
        )

    @property
    def height(self) -> Length | None:
        trpr = self._tr.find(qn("w:trPr"))
        height = None if trpr is None else trpr.find(qn("w:trHeight"))
        raw = None if height is None else height.get(qn("w:val"))
        return None if raw is None else Length(int(raw) * 635)

    @height.setter
    def height(self, value: Length | None) -> None:
        self._document._mark_dirty()
        trpr = child(self._tr, "w:trPr", first=True)
        height = trpr.find(qn("w:trHeight"))
        if value is None:
            if height is not None:
                trpr.remove(height)
            return
        if height is None:
            height = ET.SubElement(trpr, qn("w:trHeight"))
        height.set(qn("w:val"), str(Length(value).twips))


class _Column:
    def __init__(self, table: "Table", index: int):
        self._table = table
        self._index = index

    @property
    def cells(self) -> tuple[_Cell, ...]:
        return tuple(row.cells[self._index] for row in self._table.rows)

    @property
    def width(self) -> Length | None:
        cells = self.cells
        return cells[0].width if cells else None

    @width.setter
    def width(self, value: Length) -> None:
        for cell in self.cells:
            cell.width = value


class Table:
    def __init__(self, element: ET.Element, parent):
        self._element = self._tbl = element
        self._parent = parent
        self._document = parent._document if hasattr(parent, "_document") else parent

    @classmethod
    def _new(cls, document, rows: int, cols: int, parent=None) -> "Table":
        if rows < 0 or cols < 0:
            raise ValueError("rows and cols must be non-negative")
        table = element("w:tbl")
        properties = ET.SubElement(table, qn("w:tblPr"))
        width = ET.SubElement(properties, qn("w:tblW"))
        width.set(qn("w:w"), "0")
        width.set(qn("w:type"), "auto")
        grid = ET.SubElement(table, qn("w:tblGrid"))
        for _ in range(cols):
            column = ET.SubElement(grid, qn("w:gridCol"))
            column.set(qn("w:w"), "4320")
        wrapper = cls(table, parent or document)
        for _ in range(rows):
            wrapper.add_row()
        return wrapper

    @property
    def rows(self) -> list[_Row]:
        return [
            _Row(node, self)
            for node in direct_children(self._tbl, "w:tr")
        ]

    @property
    def columns(self) -> list[_Column]:
        count = max((len(row.cells) for row in self.rows), default=0)
        return [_Column(self, index) for index in range(count)]

    def cell(self, row_idx: int, col_idx: int) -> _Cell:
        return self.rows[row_idx].cells[col_idx]

    def add_row(self) -> _Row:
        self._document._mark_dirty()
        grid = self._tbl.find(qn("w:tblGrid"))
        count = len(grid) if grid is not None else len(self.columns)
        row_node = element("w:tr")
        for _ in range(count):
            cell_node = element("w:tc")
            cell_node.append(element("w:tcPr"))
            cell_node.append(element("w:p"))
            row_node.append(cell_node)
        self._tbl.append(row_node)
        return _Row(row_node, self)

    def add_column(self, width: Length) -> _Column:
        self._document._mark_dirty()
        grid = self._tbl.find(qn("w:tblGrid"))
        if grid is None:
            grid = element("w:tblGrid")
            self._tbl.insert(1, grid)
        column = element("w:gridCol")
        column.set(qn("w:w"), str(Length(width).twips))
        grid.append(column)
        for row in self.rows:
            cell = element("w:tc")
            cell.append(element("w:tcPr"))
            cell.append(element("w:p"))
            row._tr.append(cell)
            _Cell(cell, self).width = width
        return self.columns[-1]

    @property
    def style(self):
        style_id = val(child(self._tbl, "w:tblPr", first=True).find(qn("w:tblStyle")))
        if style_id is None:
            return None
        try:
            return self._document.styles[style_id]
        except KeyError:
            return None

    @style.setter
    def style(self, value) -> None:
        self._document._mark_dirty()
        properties = child(self._tbl, "w:tblPr", first=True)
        style_node = properties.find(qn("w:tblStyle"))
        if value is None:
            if style_node is not None:
                properties.remove(style_node)
            return
        style = self._document.styles.resolve(value)
        if style_node is None:
            style_node = ET.SubElement(properties, qn("w:tblStyle"))
        style_node.set(qn("w:val"), style.style_id)

    @property
    def autofit(self) -> bool:
        layout = child(self._tbl, "w:tblPr", first=True).find(qn("w:tblLayout"))
        return layout is None or layout.get(qn("w:type")) != "fixed"

    @autofit.setter
    def autofit(self, value: bool) -> None:
        self._document._mark_dirty()
        properties = child(self._tbl, "w:tblPr", first=True)
        layout = properties.find(qn("w:tblLayout"))
        if layout is None:
            layout = ET.SubElement(properties, qn("w:tblLayout"))
        layout.set(qn("w:type"), "autofit" if value else "fixed")
