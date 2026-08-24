# mojo-docx

`mojo-docx` is a standalone, open-source port of the useful document-package
subset of [python-docx](https://python-docx.readthedocs.io/). It reads, edits,
and writes `.docx` files using the familiar `from docx import Document` API.
Bulk WordprocessingML escaping and structural scanning run in compiled Mojo;
ZIP compression remains in Python's C-backed standard library.

This is not a wrapper around python-docx. The upstream package is installed in
the development environment only for parity tests and benchmarks.

## Covered API

- `Document()` and `Document(path_or_stream)`, `save(path_or_stream)`
- paragraphs, runs, headings, tabs, line breaks, and page breaks
- run bold, italic, underline, style, font name, size, and RGB color
- paragraph styles, alignment, indentation, and before/after spacing
- tables, rows, columns, cells, nested cell content, growth, widths, and styles
- page sections, orientation, size, and margins
- core document properties, including W3CDTF timestamps
- PNG, JPEG, and GIF inline pictures with native or requested dimensions
- `docx.shared`, `docx.enum.text`, `docx.enum.section`, `docx.oxml.ns.qn`, and
  the basic `docx.opc.package.OpcPackage` import paths
- preservation of untouched OPC parts, relationships, media, and ordinary
  unmodeled elements and attributes in `word/document.xml`

The tests compare behavior with python-docx 1.2.0 and also make upstream open
files written by this implementation.

## Not covered

There are no specialized APIs yet for headers and footers, footnotes,
comments, tracked changes, hyperlinks, fields, charts, equations, numbering
definitions, merged cells, or arbitrary style creation. Macro-enabled,
encrypted, and legacy binary `.doc` files are out of scope. Unmodeled OOXML is
generally retained during a round trip, but XML comments, processing
instructions, original namespace prefixes, whitespace layout, and ZIP metadata
are not byte-preserved.

## Install

```bash
pixi install
pixi run build
pixi run test
```

The Mojo toolchain is pinned in `pixi.toml`. `pixi` also sets `PYTHONPATH` so
this repository's `docx` package takes precedence over the upstream parity
dependency.

## Usage

```python
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

document = Document()
document.add_heading("Quarterly report", level=1)

paragraph = document.add_paragraph("Revenue: ")
run = paragraph.add_run("$1.2M")
run.bold = True
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x18, 0x4E, 0x77)
paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

table = document.add_table(rows=2, cols=2, style="Table Grid")
table.cell(0, 0).text = "Region"
table.cell(0, 1).text = "Revenue"
table.cell(1, 0).text = "North"
table.cell(1, 1).text = "$1.2M"

document.save("report.docx")
assert Document("report.docx").paragraphs[0].text == "Quarterly report"
```

Run it inside the environment with `pixi run python your_script.py`.

## Benchmarks

Measured with `pixi run bench` on x86_64, Linux 6.8.0-136-generic, Python
3.13.14. Each row uses the same data; timings are the best of repeated warm
runs. A ratio above 1 means this port was faster.

| workload | mojo-docx | python-docx 1.2.0 | upstream / Mojo |
| --- | ---: | ---: | ---: |
| Build + save 20k paragraphs | 992.70 ms | 7543.35 ms | 7.60x |
| Open + read 20k paragraphs | 448.73 ms | 1229.50 ms | 2.74x |
| Round-trip save 20k paragraphs | 36.72 ms | 62.67 ms | 1.71x |
| Build + save 200x20 table | 119.96 ms | 476.28 ms | 3.97x |
| Escape 8 MiB OOXML text | 32.91 ms | 44.49 ms | 1.35x |

An unchanged loaded XML part is retained as its original bytes and reused on
save. Public document mutations invalidate that cache, and the freshly
serialized bytes become the next baseline. Escaping scans and copies full SIMD
blocks with a scalar tail. A single borrowed UTF-8 string crosses the FFI
boundary without an intermediate Python bytes object. Large inputs are split
across independent CPU tasks.

XML escaping performs no floating-point work and only comparisons and copies
per byte, putting its arithmetic intensity well below roughly 2 FLOPs per byte.
It is memory-bound, so there is no GPU path.

## How it works

A document is an OPC ZIP package. Python's `zipfile` and zlib handle the
container because those mature C implementations are already fast and
portable. Supported WordprocessingML objects are lightweight views over
`xml.etree.ElementTree` nodes, which allows edits without flattening the rest
of the main document. Untouched package parts remain as their original bytes.

Serialization of a modified XML part first gathers every text and attribute
value. The Python binding packs multi-string batches into one contiguous NumPy
`uint8` buffer and passes its address to Mojo as an `Int`, alongside `int64`
offset and length arrays. A single string uses CPython's borrowed UTF-8 view
directly. Mojo escapes into a caller-owned output buffer and returns output
offsets. The structural scanner uses the same borrowed-buffer convention. No
allocation crosses the C ABI, Python retains ownership for each synchronous
call, and there are no parametric exported functions.

The complete Mojo code is one compilation unit and builds to
`dist/libmojo-docx.so`.

MIT licensed.
