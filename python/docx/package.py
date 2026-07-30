from __future__ import annotations

from dataclasses import dataclass
import zipfile

from ._templates import default_parts

MAX_PART_SIZE = 256 * 1024 * 1024
MAX_TOTAL_SIZE = 1024 * 1024 * 1024


@dataclass(frozen=True)
class Part:
    partname: str
    blob: bytes

    @property
    def content_type(self) -> str:
        return "application/xml" if self.partname.endswith(".xml") else "application/octet-stream"


def read_package(source) -> dict[str, bytes]:
    if source is None:
        return default_parts()
    try:
        archive = zipfile.ZipFile(source, "r")
    except (zipfile.BadZipFile, OSError, TypeError) as error:
        raise ValueError(f"not a valid Word document package: {error}") from error
    with archive:
        total = 0
        parts: dict[str, bytes] = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            if info.file_size > MAX_PART_SIZE:
                raise ValueError(f"package part too large: {info.filename}")
            total += info.file_size
            if total > MAX_TOTAL_SIZE:
                raise ValueError("uncompressed package is too large")
            parts[info.filename] = archive.read(info)
    if "word/document.xml" not in parts:
        raise ValueError("package has no word/document.xml part")
    return parts


def write_package(target, parts: dict[str, bytes]) -> None:
    with zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for name, data in parts.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)
