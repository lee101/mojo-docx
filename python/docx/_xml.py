"""OOXML element helpers and a Mojo-assisted UTF-8 serializer."""

from __future__ import annotations

from collections.abc import Iterator
import xml.etree.ElementTree as ET

from ._lib import escape_batch
from .oxml.ns import NSMAP, qn

XML_NS = "http://www.w3.org/XML/1998/namespace"
URI_TO_PREFIX = {uri: prefix for prefix, uri in NSMAP.items()}


def element(tag: str, attrs: dict[str, object] | None = None) -> ET.Element:
    node = ET.Element(qn(tag))
    if attrs:
        for key, value in attrs.items():
            node.set(qn(key) if ":" in key else key, str(value))
    return node


def child(parent: ET.Element, tag: str, first: bool = False) -> ET.Element:
    found = parent.find(qn(tag))
    if found is not None:
        return found
    node = element(tag)
    parent.insert(0 if first else len(parent), node)
    return node


def remove_children(parent: ET.Element, *tags: str) -> None:
    names = {qn(tag) for tag in tags}
    for node in list(parent):
        if node.tag in names:
            parent.remove(node)


def val(node: ET.Element | None, default: str | None = None) -> str | None:
    if node is None:
        return default
    return node.get(qn("w:val"), default)


def on_off(parent: ET.Element, tag: str) -> bool | None:
    node = parent.find(qn(tag))
    if node is None:
        return None
    return val(node, "true") not in {"0", "false", "off"}


def set_on_off(parent: ET.Element, tag: str, value: bool | None) -> None:
    node = parent.find(qn(tag))
    if value is None:
        if node is not None:
            parent.remove(node)
        return
    if node is None:
        node = ET.SubElement(parent, qn(tag))
    if value:
        node.attrib.pop(qn("w:val"), None)
    else:
        node.set(qn("w:val"), "0")


def parse_xml(data: bytes) -> ET.Element:
    return ET.fromstring(data)


def _split_name(name: str) -> tuple[str | None, str]:
    if not name.startswith("{"):
        return None, name
    uri, local = name[1:].split("}", 1)
    return uri, local


def _namespace_prefixes(root: ET.Element) -> dict[str, str]:
    uris: list[str] = []
    for node in root.iter():
        if isinstance(node.tag, str):
            uri, _ = _split_name(node.tag)
            if uri and uri not in uris:
                uris.append(uri)
        for name in node.attrib:
            uri, _ = _split_name(name)
            if uri and uri != XML_NS and uri not in uris:
                uris.append(uri)
    prefixes: dict[str, str] = {}
    used: set[str] = set()
    generated = 0
    for uri in uris:
        prefix = URI_TO_PREFIX.get(uri)
        if prefix is None or prefix in used:
            while f"ns{generated}" in used:
                generated += 1
            prefix = f"ns{generated}"
            generated += 1
        prefixes[uri] = prefix
        used.add(prefix)
    return prefixes


def _display_name(name: str, prefixes: dict[str, str]) -> str:
    uri, local = _split_name(name)
    if uri is None:
        return local
    if uri == XML_NS:
        return f"xml:{local}"
    return f"{prefixes[uri]}:{local}"


def _all_strings(root: ET.Element) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    attributes: list[str] = []

    def collect(node: ET.Element) -> None:
        attributes.extend(node.attrib.values())
        if node.text:
            texts.append(node.text)
        for nested in node:
            collect(nested)
        if node.tail:
            texts.append(node.tail)

    collect(root)
    return texts, attributes


def serialize_xml(root: ET.Element, declaration: bool = True) -> bytes:
    prefixes = _namespace_prefixes(root)
    texts, attributes = _all_strings(root)
    escaped_text = iter(escape_batch(texts))
    escaped_attrs = iter(escape_batch(attributes, attribute=True))
    pieces: list[str] = []
    if declaration:
        pieces.append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')

    def emit(node: ET.Element, is_root: bool = False) -> None:
        name = _display_name(node.tag, prefixes)
        pieces.extend(("<", name))
        if is_root:
            for uri, prefix in prefixes.items():
                pieces.extend((f' xmlns:{prefix}="', uri, '"'))
        for key in node.attrib:
            pieces.extend(
                (" ", _display_name(key, prefixes), '="', next(escaped_attrs), '"')
            )
        if len(node) == 0 and node.text is None:
            pieces.append("/>")
        else:
            pieces.append(">")
            if node.text:
                pieces.append(next(escaped_text))
            for nested in node:
                emit(nested)
            pieces.extend(("</", name, ">"))
        if node.tail:
            pieces.append(next(escaped_text))

    emit(root, True)
    return "".join(pieces).encode("utf-8")


def direct_children(parent: ET.Element, tag: str) -> Iterator[ET.Element]:
    qualified = qn(tag)
    return (node for node in parent if node.tag == qualified)
