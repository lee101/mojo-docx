from __future__ import annotations

from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from .._xml import element
from ..oxml.ns import qn

_TEXT_PROPERTIES = {
    "title": "dc:title",
    "subject": "dc:subject",
    "author": "dc:creator",
    "keywords": "cp:keywords",
    "comments": "dc:description",
    "last_modified_by": "cp:lastModifiedBy",
    "category": "cp:category",
    "content_status": "cp:contentStatus",
    "identifier": "dc:identifier",
    "language": "dc:language",
    "version": "cp:version",
}


class CoreProperties:
    def __init__(self, root: ET.Element, document):
        self._element = root
        self._document = document

    def _get_text(self, tag: str) -> str:
        node = self._element.find(qn(tag))
        return "" if node is None or node.text is None else node.text

    def _set_text(self, tag: str, value: str | None) -> None:
        self._document._mark_dirty()
        node = self._element.find(qn(tag))
        if node is None:
            node = element(tag)
            self._element.append(node)
        node.text = "" if value is None else str(value)[:255]

    def _get_datetime(self, tag: str) -> datetime | None:
        raw = self._get_text(tag)
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=None)

    def _set_datetime(self, tag: str, value: datetime | None) -> None:
        self._document._mark_dirty()
        node = self._element.find(qn(tag))
        if value is None:
            if node is not None:
                self._element.remove(node)
            return
        if node is None:
            node = element(tag)
            self._element.append(node)
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        node.text = value.replace(microsecond=0).isoformat() + "Z"
        node.set(qn("xsi:type"), "dcterms:W3CDTF")

    @property
    def created(self) -> datetime | None:
        return self._get_datetime("dcterms:created")

    @created.setter
    def created(self, value: datetime | None) -> None:
        self._set_datetime("dcterms:created", value)

    @property
    def modified(self) -> datetime | None:
        return self._get_datetime("dcterms:modified")

    @modified.setter
    def modified(self, value: datetime | None) -> None:
        self._set_datetime("dcterms:modified", value)

    @property
    def revision(self) -> int:
        raw = self._get_text("cp:revision")
        try:
            return int(raw)
        except ValueError:
            return 0

    @revision.setter
    def revision(self, value: int) -> None:
        if not isinstance(value, int) or value < 0:
            raise ValueError("revision must be a non-negative integer")
        self._set_text("cp:revision", str(value))


def _text_property(tag: str):
    return property(
        lambda self: self._get_text(tag),
        lambda self, value: self._set_text(tag, value),
    )


for _name, _tag in _TEXT_PROPERTIES.items():
    setattr(CoreProperties, _name, _text_property(_tag))
