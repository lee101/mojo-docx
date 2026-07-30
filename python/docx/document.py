from __future__ import annotations

from copy import deepcopy
import xml.etree.ElementTree as ET

from ._lib import analyze_xml
from ._templates import CORE, STYLES
from ._xml import element, parse_xml, serialize_xml
from .enum.section import WD_SECTION_START
from .enum.text import WD_BREAK
from .image import read_image
from .opc.coreprops import CoreProperties
from .opc.package import OpcPackage
from .oxml.ns import qn
from .package import Part, read_package, write_package
from .section import Section
from .shape import InlineShape, InlineShapeCollection
from .styles import Styles
from .table import Table
from .text.paragraph import Paragraph


class DocumentPart:
    partname = "/word/document.xml"
    content_type = (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document.main+xml"
    )

    def __init__(self, document: "Document"):
        self.document = document
        self.package = OpcPackage(document)

    @property
    def blob(self) -> bytes:
        return self.document._serialized_parts()["word/document.xml"]

    @property
    def core_properties(self) -> CoreProperties:
        return self.document.core_properties


class Document:
    """Element-backed representation of a WordprocessingML document."""

    def __init__(
        self,
        root: ET.Element,
        parts: dict[str, bytes],
        styles_root: ET.Element,
        core_root: ET.Element,
        source_stats: dict[str, int],
    ):
        self._element = root
        self._body = root.find(qn("w:body"))
        if self._body is None:
            raise ValueError("word/document.xml has no w:body element")
        self._container_element = self._body
        self._document = self
        self._parts_data = parts
        self._styles_root = styles_root
        self._core_root = core_root
        self._source_stats = source_stats
        self._dirty = False
        self.styles = Styles(styles_root)
        self.core_properties = CoreProperties(core_root, self)
        self.part = DocumentPart(self)
        self.inline_shapes = InlineShapeCollection(self)

    @classmethod
    def open(cls, source=None) -> "Document":
        parts = read_package(source)
        document_xml = parts["word/document.xml"]
        stats = analyze_xml(document_xml)
        try:
            root = parse_xml(document_xml)
            styles_root = parse_xml(parts.get("word/styles.xml", STYLES))
            core_root = parse_xml(parts.get("docProps/core.xml", CORE))
        except ET.ParseError as error:
            raise ValueError(f"invalid OOXML part: {error}") from error
        return cls(root, parts, styles_root, core_root, stats)

    @property
    def element(self) -> ET.Element:
        self._mark_dirty()
        return self._element

    def _mark_dirty(self) -> None:
        self._dirty = True

    @property
    def paragraphs(self) -> list[Paragraph]:
        return [
            Paragraph(node, self)
            for node in self._body
            if node.tag == qn("w:p")
        ]

    @property
    def tables(self) -> list[Table]:
        return [
            Table(node, self)
            for node in self._body
            if node.tag == qn("w:tbl")
        ]

    @property
    def sections(self) -> list[Section]:
        return [
            Section(node, self)
            for node in self._element.iter(qn("w:sectPr"))
        ]

    def iter_inner_content(self):
        for node in self._body:
            if node.tag == qn("w:p"):
                yield Paragraph(node, self)
            elif node.tag == qn("w:tbl"):
                yield Table(node, self)

    def _insert_before_sectpr(self, node: ET.Element) -> None:
        if len(self._body) and self._body[-1].tag == qn("w:sectPr"):
            self._body.insert(len(self._body) - 1, node)
            return
        self._body.append(node)

    def add_paragraph(self, text: str = "", style=None) -> Paragraph:
        self._mark_dirty()
        node = element("w:p")
        self._insert_before_sectpr(node)
        paragraph = Paragraph(node, self)
        if text:
            paragraph.add_run(text)
        if style is not None:
            paragraph.style = style
        return paragraph

    def add_heading(self, text: str = "", level: int = 1) -> Paragraph:
        if not 0 <= level <= 9:
            raise ValueError("level must be in range 0..9")
        style = "Title" if level == 0 else f"Heading {level}"
        return self.add_paragraph(text, style)

    def add_table(self, rows: int, cols: int, style=None) -> Table:
        self._mark_dirty()
        table = Table._new(self, rows, cols)
        self._insert_before_sectpr(table._tbl)
        if style is not None:
            table.style = style
        return table

    def add_page_break(self) -> Paragraph:
        paragraph = self.add_paragraph()
        paragraph.add_run().add_break(WD_BREAK.PAGE)
        return paragraph

    def add_picture(self, image_path_or_stream, width=None, height=None):
        return self.add_paragraph().add_run().add_picture(
            image_path_or_stream, width=width, height=height
        )

    def _add_picture(self, run, image_path_or_stream, width=None, height=None):
        self._mark_dirty()
        image = read_image(image_path_or_stream)
        if width is None and height is None:
            width, height = image.native_width, image.native_height
        elif width is None:
            width = round(height * image.width_px / image.height_px)
        elif height is None:
            height = round(width * image.height_px / image.width_px)
        index = 1
        while f"word/media/image{index}.{image.extension}" in self._parts_data:
            index += 1
        filename = f"image{index}.{image.extension}"
        self._parts_data[f"word/media/{filename}"] = image.data
        relationship_id = self._add_image_relationship(filename)
        self._add_image_content_type(image.extension, image.content_type)
        inline = self._inline_picture(
            relationship_id, filename, int(width), int(height), index
        )
        drawing = element("w:drawing")
        drawing.append(inline)
        run._r.append(drawing)
        return InlineShape(inline, self)

    def _add_image_relationship(self, filename: str) -> str:
        path = "word/_rels/document.xml.rels"
        namespace = "http://schemas.openxmlformats.org/package/2006/relationships"
        root = parse_xml(
            self._parts_data.get(
                path,
                f'<Relationships xmlns="{namespace}"/>'.encode(),
            )
        )
        used = {node.get("Id") for node in root}
        number = 1
        while f"rId{number}" in used:
            number += 1
        relationship_id = f"rId{number}"
        node = ET.SubElement(root, f"{{{namespace}}}Relationship")
        node.set("Id", relationship_id)
        node.set(
            "Type",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
        )
        node.set("Target", f"media/{filename}")
        self._parts_data[path] = serialize_xml(root)
        return relationship_id

    def _add_image_content_type(self, extension: str, content_type: str) -> None:
        path = "[Content_Types].xml"
        namespace = "http://schemas.openxmlformats.org/package/2006/content-types"
        root = parse_xml(self._parts_data[path])
        for node in root:
            if node.get("Extension", "").lower() == extension.lower():
                return
        node = ET.SubElement(root, f"{{{namespace}}}Default")
        node.set("Extension", extension)
        node.set("ContentType", content_type)
        self._parts_data[path] = serialize_xml(root)

    @staticmethod
    def _inline_picture(
        relationship_id: str,
        filename: str,
        width: int,
        height: int,
        shape_id: int,
    ) -> ET.Element:
        inline = element("wp:inline")
        inline.set("distT", "0")
        inline.set("distB", "0")
        inline.set("distL", "0")
        inline.set("distR", "0")
        extent = ET.SubElement(inline, qn("wp:extent"))
        extent.set("cx", str(width))
        extent.set("cy", str(height))
        effect = ET.SubElement(inline, qn("wp:effectExtent"))
        for key in ("l", "t", "r", "b"):
            effect.set(key, "0")
        doc_pr = ET.SubElement(inline, qn("wp:docPr"))
        doc_pr.set("id", str(shape_id))
        doc_pr.set("name", f"Picture {shape_id}")
        ET.SubElement(inline, qn("wp:cNvGraphicFramePr"))
        graphic = ET.SubElement(inline, qn("a:graphic"))
        graphic_data = ET.SubElement(graphic, qn("a:graphicData"))
        graphic_data.set(
            "uri", "http://schemas.openxmlformats.org/drawingml/2006/picture"
        )
        picture = ET.SubElement(graphic_data, qn("pic:pic"))
        nv = ET.SubElement(picture, qn("pic:nvPicPr"))
        cnv = ET.SubElement(nv, qn("pic:cNvPr"))
        cnv.set("id", "0")
        cnv.set("name", filename)
        ET.SubElement(nv, qn("pic:cNvPicPr"))
        fill = ET.SubElement(picture, qn("pic:blipFill"))
        blip = ET.SubElement(fill, qn("a:blip"))
        blip.set(qn("r:embed"), relationship_id)
        stretch = ET.SubElement(fill, qn("a:stretch"))
        ET.SubElement(stretch, qn("a:fillRect"))
        shape = ET.SubElement(picture, qn("pic:spPr"))
        transform = ET.SubElement(shape, qn("a:xfrm"))
        offset = ET.SubElement(transform, qn("a:off"))
        offset.set("x", "0")
        offset.set("y", "0")
        size = ET.SubElement(transform, qn("a:ext"))
        size.set("cx", str(width))
        size.set("cy", str(height))
        geometry = ET.SubElement(shape, qn("a:prstGeom"))
        geometry.set("prst", "rect")
        ET.SubElement(geometry, qn("a:avLst"))
        return inline

    def add_section(
        self, start_type: WD_SECTION_START = WD_SECTION_START.NEW_PAGE
    ) -> Section:
        self._mark_dirty()
        current = self.sections[-1]._sectPr if self.sections else element("w:sectPr")
        next_section = deepcopy(current)
        paragraph = self.add_paragraph()
        paragraph._pPr.append(current)
        section_type = next_section.find(qn("w:type"))
        if section_type is None:
            section_type = ET.SubElement(next_section, qn("w:type"))
        section_type.set(
            qn("w:val"),
            {
                WD_SECTION_START.CONTINUOUS: "continuous",
                WD_SECTION_START.NEW_COLUMN: "nextColumn",
                WD_SECTION_START.NEW_PAGE: "nextPage",
                WD_SECTION_START.EVEN_PAGE: "evenPage",
                WD_SECTION_START.ODD_PAGE: "oddPage",
            }[WD_SECTION_START(start_type)],
        )
        old_body_section = self._body.find(qn("w:sectPr"))
        if old_body_section is not None:
            self._body.remove(old_body_section)
        self._body.append(next_section)
        return Section(next_section, self)

    @property
    def _parts(self) -> list[Part]:
        current = self._serialized_parts()
        return [Part("/" + name, blob) for name, blob in current.items()]

    def _serialized_parts(self) -> dict[str, bytes]:
        if self._dirty:
            self._parts_data["word/document.xml"] = serialize_xml(self._element)
            self._parts_data["word/styles.xml"] = serialize_xml(self._styles_root)
            self._parts_data["docProps/core.xml"] = serialize_xml(self._core_root)
            self._dirty = False
        return dict(self._parts_data)

    def save(self, path_or_stream) -> None:
        write_package(path_or_stream, self._serialized_parts())

    def __len__(self) -> int:
        return len(self.paragraphs) + len(self.tables)
