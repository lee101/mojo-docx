"""Namespace helpers compatible with the commonly used python-docx surface."""

from __future__ import annotations

NSMAP = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcmitype": "http://purl.org/dc/dcmitype/",
    "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


def qn(tag: str) -> str:
    if tag.startswith("{"):
        return tag
    prefix, local = tag.split(":", 1)
    try:
        return f"{{{NSMAP[prefix]}}}{local}"
    except KeyError as error:
        raise KeyError(f"unknown namespace prefix: {prefix}") from error


def nsdecls(*prefixes: str) -> str:
    return " ".join(f'xmlns:{prefix}="{NSMAP[prefix]}"' for prefix in prefixes)
