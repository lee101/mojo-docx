from __future__ import annotations

from dataclasses import dataclass
import os
import struct

from .shared import Length


@dataclass(frozen=True)
class ImageInfo:
    data: bytes
    extension: str
    content_type: str
    width_px: int
    height_px: int
    dpi_x: float = 72.0
    dpi_y: float = 72.0

    @property
    def native_width(self) -> Length:
        return Length(round(self.width_px * 914400 / self.dpi_x))

    @property
    def native_height(self) -> Length:
        return Length(round(self.height_px * 914400 / self.dpi_y))


def _png(data: bytes) -> ImageInfo:
    if len(data) < 24:
        raise ValueError("truncated PNG image")
    width, height = struct.unpack(">II", data[16:24])
    dpi_x = dpi_y = 72.0
    position = 8
    while position + 12 <= len(data):
        size = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        payload = data[position + 8 : position + 8 + size]
        if kind == b"pHYs" and len(payload) == 9 and payload[8] == 1:
            xppm, yppm = struct.unpack(">II", payload[:8])
            dpi_x = xppm * 0.0254 or 72.0
            dpi_y = yppm * 0.0254 or 72.0
        position += size + 12
    return ImageInfo(data, "png", "image/png", width, height, dpi_x, dpi_y)


def _jpeg(data: bytes) -> ImageInfo:
    position = 2
    dpi_x = dpi_y = 72.0
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        marker = data[position + 1]
        position += 2
        if marker in {0xD8, 0xD9}:
            continue
        if position + 2 > len(data):
            break
        size = struct.unpack(">H", data[position : position + 2])[0]
        segment = data[position + 2 : position + size]
        if marker == 0xE0 and segment.startswith(b"JFIF\0") and len(segment) >= 12:
            unit = segment[7]
            xdensity, ydensity = struct.unpack(">HH", segment[8:12])
            if unit == 1:
                dpi_x, dpi_y = xdensity or 72.0, ydensity or 72.0
            elif unit == 2:
                dpi_x, dpi_y = (xdensity or 28.35) * 2.54, (ydensity or 28.35) * 2.54
        if marker in {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        } and len(segment) >= 5:
            height, width = struct.unpack(">HH", segment[1:5])
            return ImageInfo(data, "jpg", "image/jpeg", width, height, dpi_x, dpi_y)
        position += size
    raise ValueError("JPEG image has no size marker")


def _gif(data: bytes) -> ImageInfo:
    if len(data) < 10:
        raise ValueError("truncated GIF image")
    width, height = struct.unpack("<HH", data[6:10])
    return ImageInfo(data, "gif", "image/gif", width, height)


def read_image(image_file) -> ImageInfo:
    if hasattr(image_file, "read"):
        data = image_file.read()
    else:
        with open(os.fspath(image_file), "rb") as stream:
            data = stream.read()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _png(data)
    if data.startswith(b"\xff\xd8"):
        return _jpeg(data)
    if data.startswith((b"GIF87a", b"GIF89a")):
        return _gif(data)
    raise ValueError("unsupported image format; PNG, JPEG, and GIF are supported")
