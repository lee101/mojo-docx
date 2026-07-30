"""ctypes bindings for the Mojo WordprocessingML kernels."""

from __future__ import annotations

import ctypes
import os
import subprocess

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.environ.get("MOJO_DOCX_LIB") or os.path.join(
    ROOT, "dist", "libmojo-docx.so"
)
SOURCE = os.path.join(ROOT, "src", "docx.mojo")
I = ctypes.c_int64
I64_MAX = np.iinfo(np.int64).max
INTP_MAX = np.iinfo(np.intp).max
PARALLEL_ESCAPE_BYTES = 1_048_576
ESCAPE_TASKS = 16

_unicode_as_utf8 = ctypes.pythonapi.PyUnicode_AsUTF8AndSize
_unicode_as_utf8.argtypes = [ctypes.py_object, ctypes.POINTER(ctypes.c_ssize_t)]
_unicode_as_utf8.restype = ctypes.c_void_p
_unicode_decode_utf8 = ctypes.pythonapi.PyUnicode_DecodeUTF8
_unicode_decode_utf8.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ssize_t,
    ctypes.c_char_p,
]
_unicode_decode_utf8.restype = ctypes.py_object


class BuildError(RuntimeError):
    pass


def build(force: bool = False) -> str:
    if os.environ.get("MOJO_DOCX_LIB"):
        if os.path.exists(LIB):
            return LIB
        raise BuildError(f"MOJO_DOCX_LIB does not exist: {LIB}")
    if (
        not force
        and os.path.exists(LIB)
        and os.path.getmtime(LIB) >= os.path.getmtime(SOURCE)
    ):
        return LIB
    process = subprocess.run(
        ["bash", os.path.join(ROOT, "build", "build.sh")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if process.returncode or not os.path.exists(LIB):
        raise BuildError((process.stderr or process.stdout).strip()[:4000])
    return LIB


_handle: ctypes.PyDLL | None = None


def lib() -> ctypes.PyDLL:
    global _handle
    if _handle is None:
        _handle = ctypes.PyDLL(build())
        _handle.mdx_escape_batch.argtypes = [I] * 9
        _handle.mdx_escape_batch.restype = I
        _handle.mdx_escape_one.argtypes = [I] * 6
        _handle.mdx_escape_one.restype = I
        _handle.mdx_analyze_xml.argtypes = [I] * 3
        _handle.mdx_analyze_xml.restype = I
    return _handle


def _addr(array: np.ndarray) -> int:
    if not array.flags.c_contiguous:
        raise ValueError("FFI buffers must be C-contiguous")
    address = int(array.ctypes.data)
    if not address:
        raise ValueError("FFI buffers require non-null storage")
    return address


def escape_batch(values: list[str], attribute: bool = False) -> list[str]:
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise TypeError("values must be a list of strings")
    if not values:
        return []
    if len(values) == 1:
        value = values[0]
        source_size = ctypes.c_ssize_t()
        source_address = _unicode_as_utf8(value, ctypes.byref(source_size))
        if not source_address or source_size.value < 0:
            raise RuntimeError("CPython did not provide a valid UTF-8 buffer")
        if source_size.value > min(I64_MAX // 6, INTP_MAX // 6):
            raise OverflowError("UTF-8 input is too large for the Mojo ABI")
        destination_capacity = max(source_size.value * 6, 1)
        destination = np.empty(destination_capacity, dtype=np.uint8)
        scratch = np.empty(ESCAPE_TASKS + 1, dtype=np.int64)
        size = lib().mdx_escape_one(
            source_address,
            source_size.value,
            _addr(destination),
            destination_capacity,
            int(attribute),
            _addr(scratch),
        )
        if not 0 <= size <= destination_capacity:
            raise RuntimeError("Mojo XML escaping failed")
        return [
            _unicode_decode_utf8(
                _addr(destination), size, ctypes.c_char_p(b"strict")
            )
        ]
    chunks = [value.encode("utf-8") for value in values]
    position = sum(map(len, chunks))
    if len(chunks) > INTP_MAX or position > min(I64_MAX // 6, INTP_MAX // 6):
        raise OverflowError("UTF-8 batch is too large for the Mojo ABI")
    offsets = np.empty(len(chunks), dtype=np.int64)
    lengths = np.empty(len(chunks), dtype=np.int64)
    position = 0
    for index, chunk in enumerate(chunks):
        offsets[index] = position
        lengths[index] = len(chunk)
        position += len(chunk)
    source = np.frombuffer(b"".join(chunks) or b"\0", dtype=np.uint8)
    destination_capacity = max(position * 6, 1)
    destination = np.empty(destination_capacity, dtype=np.uint8)
    output_offsets = np.empty(len(chunks) + 1, dtype=np.int64)
    size = lib().mdx_escape_batch(
        _addr(source),
        position,
        _addr(offsets),
        _addr(lengths),
        len(chunks),
        _addr(destination),
        destination_capacity,
        _addr(output_offsets),
        int(attribute),
    )
    if not 0 <= size <= destination_capacity:
        raise RuntimeError("Mojo XML batch escaping failed")
    boundaries = output_offsets.tolist()
    if boundaries[0] != 0 or boundaries[-1] != size or any(
        left > right for left, right in zip(boundaries, boundaries[1:])
    ):
        raise RuntimeError("Mojo XML batch returned invalid output offsets")
    encoded = destination[:size].tobytes()
    return [
        encoded[boundaries[i] : boundaries[i + 1]].decode("utf-8")
        for i in range(len(chunks))
    ]


def analyze_xml(data: bytes) -> dict[str, int]:
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    if len(data) > I64_MAX:
        raise OverflowError("XML input is too large for the Mojo ABI")
    source = np.frombuffer(data or b"\0", dtype=np.uint8)
    counts = np.zeros(6, dtype=np.int64)
    result = lib().mdx_analyze_xml(_addr(source), len(data), _addr(counts))
    if result < 0 or result != counts[0] or np.any(counts < 0):
        raise RuntimeError("Mojo XML analysis failed")
    return dict(zip(("elements", "paragraphs", "runs", "texts", "tables", "rows"), map(int, counts)))
