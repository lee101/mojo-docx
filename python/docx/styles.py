from __future__ import annotations

import xml.etree.ElementTree as ET
import re

from .oxml.ns import qn


class _Style:
    def __init__(self, element: ET.Element | None, name: str, style_id: str):
        self._element = element
        self.name = name
        self.style_id = style_id

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"<docx.styles._Style {self.name!r}>"


class Styles:
    def __init__(self, root: ET.Element):
        self._root = root

    def __iter__(self):
        for node in self._root.findall(qn("w:style")):
            yield self._from_element(node)

    def __len__(self) -> int:
        return len(self._root.findall(qn("w:style")))

    def __getitem__(self, key: str) -> _Style:
        for style in self:
            if style.name == key or style.style_id == key:
                return style
        raise KeyError(f"no style with name {key!r}")

    @staticmethod
    def _from_element(node: ET.Element) -> _Style:
        style_id = node.get(qn("w:styleId"), "")
        name_node = node.find(qn("w:name"))
        name = name_node.get(qn("w:val"), style_id) if name_node is not None else style_id
        heading = re.fullmatch(r"heading ([1-9])", name)
        if heading:
            name = f"Heading {heading.group(1)}"
        return _Style(node, name, style_id)

    def resolve(self, value: str | _Style | None) -> _Style | None:
        if value is None:
            return None
        if isinstance(value, _Style):
            return value
        return self[value]
