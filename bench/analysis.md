# mojo-docx ANALYZE phase — measured hotspot map

No algorithm was changed in this phase. `src/` and `tests/` are untouched; this file is the only addition. Every number below comes from a run in this session (official `pixi run bench` plus decomposition probes run with `pixi run python`). Nothing is estimated from source or documentation.

## Machine and data

- Machine (official bench): `x86_64, Linux 6.8.0-147-generic, Python 3.13.14`; CPU `Intel(R) Xeon(R) CPU E5-2697 v4 @ 2.30GHz`, 72 cores.
- Fixture (same as `bench/bench.py`): 20,000 paragraphs, `TEXT = "A & B < C — WordprocessingML text with tabs\tand Unicode 東京. " * 2` (120 chars / 132 UTF-8 bytes per paragraph). `word/document.xml` is 4,849,321 bytes uncompressed (62,149 compressed); whole `.docx` is 65,076 bytes.
- Real caller sizes inside `serialize_xml` for that fixture: 60,009 text strings totalling 2,728,935 UTF-8 bytes (3 per paragraph — the tab in `TEXT` splits each run into two `w:t` nodes plus a `w:tab` — average ~45 bytes) and 20,011 attribute strings totalling 160,039 bytes. The tree has 140,007 nodes (20k `w:p`, 20k `w:r`, 60k `w:t`, 40k `w:tab`, plus body/root). The document XML has 240,011 `<` byte occurrences.
- The bench escape input is `TEXT * 65_536` = 7,864,320 chars = 8,650,752 UTF-8 bytes, with 131,072 `&` and 131,072 `<` specials (262,144 total, ~3% density).
- Mojo SIMD width was verified by compiling a probe with the pinned toolchain (`mojo ==1.2.0.dev2026092605`): `simd_width_of[Float64] = 4`, so `BYTE_W = 32` bytes per vector in `src/docx.mojo`. There are three exported kernels (`mdx_escape_one`, `mdx_escape_batch`, `mdx_analyze_xml`); `src/docx.mojo` contains no `parallelize`/`from max...` import — all task loops in the kernels are plain serial `for` loops.

## Official end-to-end results

`pixi run bench` (flock-wrapped, this session):

| workload | mojo-docx | python-docx 1.2.0 | upstream / Mojo |
| --- | ---: | ---: | ---: |
| Build + save 20k paragraphs | 1127.87 ms | 7326.34 ms | 6.50x |
| Open + read 20k paragraphs | 388.99 ms | 1247.06 ms | 3.21x |
| Round-trip save 20k paragraphs | 35.36 ms | 66.80 ms | 1.89x |
| Build + save 200x20 table | 119.55 ms | 553.56 ms | 4.63x |
| Escape 8 MiB OOXML text | 27.25 ms | 45.79 ms | 1.68x |

All five e2e workloads favour the port. The decomposition below shows this win is **not** uniform: it comes almost entirely from document construction and document reading, while fresh-save serialization is slower than upstream. That row is kept in the table and marked.

## Ranked hotspot table

Time is best-of-repeated warm runs (best-of-5 or best-of-7 unless noted) on the fixture above. "Bytes touched" counts logical read+write traffic. "Flops" counts integer/vector/compare operations as executed — the codebase has **zero floating-point work** (escape/analyze compare and copy bytes only), so FP flops are 0 everywhere; the flop column reports integer-op equivalents with the counting rule stated per row. Memory-bound vs compute-bound is judged from measured throughput versus the copy rate of the same hardware (plain-copy escape attains ~2.1 GB/s; nothing here exceeds that except the no-special copy path itself).

| rank | function (entry point) | input size | time | bytes touched | flops | flops/byte | bound | where time sits | next phase |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `serialize_xml(document element)` — emit recursion + `_display_name`/`_split_name` (Python) | 140,007 nodes, output 4,849,321 B | ~517 ms | read 140k tags + 2.73 MB text + 0.16 MB attrs; write 4.85 MB HTML-escaped XML + 880,098 `pieces` list items | ~1.0M Python calls, 0 FP (compares, string splits, list appends only) | ~0 (Python control, not arithmetic) | memory-bound via allocator/object churn | Python glue (100%; no ctypes, no kernel) | **unroll** (Python: cache `qn`, inline `_split_name`, avoid `pieces.extend` per node) |
| 2 | `serialize_xml` — `escape_batch` glue for texts+attrs (Python wrapper in `_lib.py`) | 60,009 texts (2,728,935 B) + 20,011 attrs (160,039 B) | ~105 ms of row 1's 517 ms | encode read/write 2.89 MB twice (encode + join) + 16.4 MB dst alloc + kernel read 2.89 MB twice + write 3.02 MB + `tobytes` copy 3.02 MB + per-piece decode read 3.02 MB; ~8–9x input logical traffic | 0 FP; kernel int ops ~10M (see row 9) | ~0 in glue | memory-bound (copies) | Python glue ~96 ms, Mojo kernel ~9 ms → **~91% glue, ~9% kernel** | **none** (kernel already fast; wrap changes are Python, not the kernel phases) |
| 3 | `Document.add_paragraph(text)` + `Run.text` setter, x20,000 (`Document()` ctor is 0.26 ms, negligible) | 20,000 paragraphs, 120 chars each | ~267–365 ms (18.3 µs/para best-of-5; 13.6 µs/para steady single-call) | ET objects: 60,000 `element()` calls (0.65 µs/call, 39 ms) + 13.6 MB of text; raw-ET baseline (same nodes, no wrappers/setter) is 52 ms (2.6 µs/para) | 0 FP; `re.split` 2.2 µs/run (43 ms/20k), 320k `qn` calls at 321 ns (103 ms) | ~0 | memory-bound (allocation) | Python glue (100%) | **unroll** (Python: fewer `qn`/`element` calls, cheaper split) |
| 4 | `parse_xml` = `ET.fromstring(document.xml)` in `Document.open` | 4,849,321 B, 240,011 `<`, 140k nodes | ~180 ms | read 4.85 MB, write 140k ET elements + 60k strings (~tens of MB with object overhead) | 0 FP (C parser, integer) | ~0 | memory-bound (allocation) | C stdlib (`xml.etree`), not Python, not Mojo | **none** (upstream lxml is 116 ms — port is **slower**, see §3; ET is C, no Mojo kernel applies) |
| 5 | `Paragraph.text` + `Paragraph.runs` + `Run.text` getters on a loaded doc | 20,000 paragraphs, 20,000 runs | ~143 ms (20k `.paragraphs` list alone 19–21 ms, `.text` adds ~123 ms; single `Paragraph.text` 3.7 µs) | read 60k `w:t` strings (2.73 MB) + join | 0 FP | ~0 | memory-bound | Python glue (100%; `qn` calls 180k at 0.57 µs in `qn` under `cProfile` for open+read) | **unroll** |
| 6 | `write_package` (ZIP deflate) in `save` | 4,855,796 B total parts (doc 4,849,321 B) | ~32 ms | read 4.86 MB, write 65 KB compressed | zlib integer/entropy, 0 FP | ~0 | compute-bound inside zlib (entropy), not fixable here | C stdlib (`zlib`), not Python, not Mojo | **none** |
| 7 | Table build+save: `add_table(200,20)` empty 10.1 ms + 4,000× `cell.text` (4.6 µs, 18 ms) + fresh serialize ~58 ms + zip | 200×20 = 4,000 cells in 20,231 nodes, doc XML 287,359 B | ~103–120 ms e2e | 4,000 small texts (47,845 B total) + 287 KB XML | 0 FP | ~0 | memory-bound | Python glue (~45 ms build) + Python serialize (~58 ms, same emit as row 1) + C zip; kernel ~1 ms | **unroll** |
| 8 | `serialize_xml` — `_namespace_prefixes` | 140,007 nodes | ~95 ms | read tags/attribs, small output dict | 0 FP; 320k `_split_name` calls (391 ns) ≈ 125 ms across serialize | ~0 | memory-bound | Python glue (100%) | **unroll** (cache the prefix map; it is invariant per document) |
| 9 | `escape_batch` real texts — raw `mdx_escape_batch` kernel (2 passes: `escaped_size` + `escape_one` per string) | 2,728,935 B in → 3,008,935 B out, 60,009 strings | 7.7 ms (kernel only, prefilled buffers) | kernel read 2.73 MB twice (5.46 MB) + write 3.01 MB = 8.47 MB → 1.10 GB/s effective | ~13.6M int ops (3 `eq` + 2 `or` + `reduce_or` per 32 B vector, amortised) | ~4–5 / byte (integer, 0 FP) | memory-bound | Mojo kernel (100% of this row; wrapper excluded) | **parallel** (batch loop is serial in Mojo; 60k independent strings; see §GPU note) |
| 10 | `escape_batch` single — raw `mdx_escape_one` kernel, small (<1 MiB, serial path, 1 pass) | 132 B typical paragraph; 65,472 B measured at 412 MB/s | 16 µs at 132 B (fixed overhead dominates); 0.16 ms at 65,472 B | read+write 65 KB | ~3 int ops/B + branch per special | ~3–4 / byte (integer) | memory-bound | Mojo kernel, but per-call fixed cost 15.6 µs/call (raw ctypes 4.7 µs, wrapper 10.6 µs) | **none** (far below any parallel/SIMD threshold at caller sizes) |
| 11 | `escape_batch` single — raw `mdx_escape_one`, large (≥1 MiB, 16 serial tasks, 2 passes) | 8,650,752 B in, 262,144 specials | 12.2 ms raw (369 MB/s through-put-equivalent); plain (no specials) 2.1 GB/s, with specials ~330 MB/s | kernel read 8.65 MB twice + write ~8.9 MB | ~25–40M int ops | ~3–5 / byte (integer, 0 FP) | memory-bound | Mojo kernel (100%) | **parallel** (2 passes × 16 serial tasks; measured scalar tail + `copy_plain`/`put_entity` per special is the limiter; 72 cores idle) |
| 12 | `analyze_xml` raw `mdx_analyze_xml` kernel | 4,849,321 B, 240,011 `<` | 6.8 ms (716 MB/s) | read 4.85 MB, write 48 B counts | ~5–10M compares (1–2 per byte + 6-way tag scan on tag bytes) | ~1–2 / byte (integer, 0 FP) | memory-bound | Mojo kernel (100%); scalar byte loop, no SIMD | **parallel** (counts are a reduction; per-thread histograms make it embarrassingly parallel; not SIMD — the loop is branchy `while`/tag-parse) |
| 13 | `read_package` (ZIP inflate) | whole `.docx` 65,076 B → 4.86 MB parts | 5.4 ms | read 65 KB, write 4.86 MB | zlib integer | ~0 | memory-bound | C stdlib | **none** |
| 14 | `analyze_xml` Python wrapper + `parse_xml` styles/core | 4.8 MB wrapper; styles 3,290 B + core 688 B | 15 µs tiny-call (100 B); styles+core parse 0.17 ms | wrapper view, no copy (`np.frombuffer`); `np.zeros(6)` 48 B | 0 | ~0 | memory-bound | Python glue (wrapper ~11 µs over raw 3.4 µs) | **none** (fixed ~10 µs is irrelevant at 4.8 MB single-call-per-open) |

## Where the time actually goes (reconciliation)

`build_save` (official 1127.87 ms): `add_paragraph` loop ~267 ms + fresh `save` ~577 ms (true save-only measured 576.6 ms best; `serialize_xml` 517 ms + `write_package` 32 ms + glue/zip overhead) + `Document()` 0.26 ms ≈ 845 ms accounted, remainder is `BytesIO`/`zipfile` object churn and run-to-run variance (probe2 best-of-5 range 978–1078 ms). The kernel share of a whole build+save is `escape kernel ~9 ms + analyze 0 ms (no open) = <1%`.

`open_read` (official 388.99 ms): `Document(fixture)` ~201 ms (`read_package` 5.4 + `analyze_xml` 6.9 + `parse_xml` 182 + styles/core 0.17) + `paragraphs` list 19 ms + `.text` sum ~123 ms ≈ 343 ms, remainder is repeated `paragraphs` rebuild per access and `sum` overhead. `analyze_xml` — the only Mojo work on the open path — is 3–7 ms, **~2% of open_read**.

`serialize_xml` 517 ms split (manual replication, best-of-5, probe5): `_namespace_prefixes` 95 ms (18%), `_all_strings` 70 ms (13%), `escape_batch` texts+attrs 105 ms (20%), `emit` recursion 236 ms (46%), `"".join(pieces)` + `.encode` 8 ms. `cProfile` confirms: `emit` (140,129 calls, 0.89 s cumulative under profiler), `_split_name` (320,490 calls, 0.41 s), `_namespace_prefixes`, `escape_batch` (6 calls, 0.29 s under profiler, of which raw kernel is ~9 ms), `_all_strings`, `qn` (160,001 calls, 0.23 s), `element` (140,000 calls, 0.31 s). **The Mojo kernels are <2% of serialization; the Python serializer is the hotspot.**

`table_save` (official 119.55 ms): build 48.9 ms (`add_table` empty 10.1 ms + 4,000× `cell.text` 18 ms) + fresh serialize ~58 ms (287 KB doc, 20,231 nodes — same Python emit, fewer nodes) + zip ~10 ms. Kernel again ~1 ms (47,845 B of text, 4,009 strings).

## Per-call allocations and copies (measured)

- **No Python-level loop re-enters ctypes per element.** Verified by call counting: each `serialize_xml` makes exactly 2 `escape_batch` calls (texts, then attrs), regardless of whether the list has 1 or 60,009 entries; `Document.open` makes exactly 1 `analyze_xml` call per document. `add_paragraph`, `cell.text`, `Paragraph.text` make **zero** ctypes calls. The batch loop over strings lives inside Mojo (`mdx_escape_batch`). What Python does per element is adjacent glue, not FFI re-entry:
  - `[value.encode("utf-8") for value in values]` — 60,009 iterations, 9.6 ms; `b"".join(...)` adds a second full copy (2.73 MB read + 2.73 MB write).
  - Offsets/lengths loop `offsets[index] = position` over 60,009 chunks — 17.7 ms, plus 3× `np.empty(n, int64)` (960 KB total at n=60,009).
  - Result construction `[encoded[boundaries[i]:boundaries[i+1]].decode("utf-8") ...]` — 60,009 slice+decode pairs, 29.3 ms (vs 2.2 ms for a single decode of the whole 3 MB buffer). This per-piece decode is the single largest glue item in the batch path.
  - Attribute path is worse per byte: 20,011 attrs / 160,039 B takes 16.5 ms full vs 1.05 ms raw kernel (**94% glue**) because decode overhead scales with string count, not bytes.
- **Per-call allocations in `escape_batch` (batch path, 2.73 MB in):** `chunks` list-of-bytes (2.73 MB) + joined `bytes` (2.73 MB) + `offsets`/`lengths`/`output_offsets` (~1 MB) + `destination` `6× input` = 16,373,610 B + `tobytes()` copy (3.01 MB) + 60,009 Python `str` results (tracemalloc peak 34.3 MB for a 20k-string batch; 80.6 MB peak for the single 8.65 MB string, i.e. ~9× input size live at once). `np.empty` itself is cheap (1.5 µs at 16 MB — pages fault on write) but the 6× sizing is pure over-provisioning: measured out/in is 1.10× (3,008,935 / 2,728,935), so 5.5× of the destination is never used. The kernel writes only `size` bytes; the rest is allocated address space for nothing.
- **Single-string path** (`len(values) == 1`) avoids the encode+join copies via CPython's borrowed UTF-8 view (`PyUnicode_AsUTF8AndSize`, no intermediate bytes) and decodes once — full 25.1 ms vs raw 12.2 ms (**51% glue**, vs 91% for batch). This is the correct pattern; the batch path should match it, but that is an algorithm decision for a later phase, not this one.
- **Kernel-side double pass.** Both batch and large-single paths scan the input twice: `escaped_size` (to find output offsets) then `escape_one` (to copy). That halves effective throughput: plain-copy segments attain 2.1 GB/s, special-heavy segments fall to ~330 MB/s because each special triggers scalar `copy_plain` + `put_entity` byte writes with a lane loop. The 16 "tasks" for the large path run in a plain serial `for` (`ESCAPE_TASKS`), so `count < PARALLEL_ESCAPE_BYTES` (1 MiB) gates a parallel path that never runs — measured: at 1,048,576 B plain is 2,105 MB/s vs specials 334 MB/s, i.e. the current code is single-core at all sizes.
- **`analyze_xml` wrapper** is clean: `np.frombuffer` view (no copy), 48 B counts array, 1 ctypes call. Wrapper overhead ~11 µs (15.2 µs tiny vs 3.4 µs raw) is noise at the only caller size (4.8 MB per `Document.open`).

## Baselines (same data, this session)

- **Upstream python-docx 1.2.0, per entry point** (run via the pixi env python with `PYTHONPATH` stripped, so the installed 1.2.0 package is used; native `bench/bench.py --upstream` returns the same e2e numbers as §Official): `add_loop` 7,891 ms (vs port 267–365 ms), single `add_paragraph` 134 µs (vs port 13.6 µs), `Document(path)` ctor 120 ms (vs port 201 ms), `paragraphs`+`.text` 1,077 ms (vs port 143 ms), fresh `save` 83–91 ms (vs port 577 ms), lxml `etree.tostring` on the 8.65 MB escape node 48.6 ms (vs port full `escape_batch` [same data] 25.1 ms). See §3 for the two slower rows.
- **Numpy/Python baselines for escape (8.65 MB input):** numpy-mask + Python-join-over-specials (262,144 specials) 178 ms; `str.translate` (C, `&<>` map only) 1,072 ms; pure-Python per-char loop extrapolated from 12,000 chars (1.13 ms → 740 ms at 7.86M chars); `bytes.translate` with a wrong-length map (speed reference only, not a correct baseline) 9.7 ms. Correct baselines are 178–740 ms, so the Mojo kernel (12.2 ms raw, 25.1 ms with wrapper) wins by 7–30×. The `bytes.translate` number is **not** used as a baseline because its output is wrong.
- **Baseline for `analyze_xml`:** `bytes.count(b"<w:p")` alone is 2.8 ms (1,704 MB/s, single pattern, 5× less work), 5× `bytes.count` is 16.2 ms (5 passes). ET `.iter()` count over 240k nodes is 7.4 ms. `analyze_xml` (6.8 ms, 716 MB/s, full 5-tag classification in 1 pass) is competitive and is not a hotspot anyway (~2% of open).

## §3 Slower-than-upstream rows (kept, not dropped)

1. **Fresh-save serialization — SLOWER than upstream.** Port fresh save-only is 577 ms (serialize 517 ms + zip 32 ms). Upstream fresh save is 83–91 ms (lxml C serialization + zip). The port's `serialize_xml` (Python `emit` recursion + `_namespace_prefixes` 95 ms + `_all_strings` 70 ms + glue 105 ms) is ~6× slower than upstream's `lxml` save for the same 20k-paragraph document. The e2e `build_save` win (6.50×) comes from construction (upstream add-loop 7.9 s vs port 0.27 s), not from save. Any next phase that optimises save must beat 83–91 ms, not 577 ms.
2. **`parse_xml` (ET) — SLOWER than upstream lxml.** Port `ET.fromstring` on the 4.8 MB document is 180 ms best-of-5 (185 ms mean). Upstream lxml `fromstring` on the same bytes is 116 ms. The port pays ~1.5× on parsing of every open. E2E `open_read` still wins 3.21× because upstream's Python object layer (`paragraphs`+`.text` 1,077 ms vs 143 ms) dominates their open.

No other e2e row is slower. `escape_batch` full-path (25.1 ms single, 82–87 ms batch for 2.73 MB) beats both the upstream lxml escape (48.6 ms) and every correct numpy/Python baseline (178–740 ms).

## GPU verdict (`none` for every kernel)

Flops-per-byte, measured rather than assumed:

- `mdx_escape_one` / `mdx_escape_batch`: **3–5 integer ops per byte, 0 FP** (three `values.eq` + two `or` + `reduce_or` per 32-byte vector amortised; special handling adds byte copies but no arithmetic). Measured copy rate 2.1 GB/s plain, ~330 MB/s with specials — pure streaming.
- `mdx_analyze_xml`: **~1–2 compares per byte, 0 FP** (one `<` test per byte, six-way delimiter scan only on tag-name bytes). 716 MB/s, streaming reads.

Both kernels are at **0 FP flops/byte and well under ~2 arithmetic ops per byte** — three orders of magnitude below any GPU crossover. A GPU would need to copy 2.7–8.7 MB in and ~3–9 MB out over PCIe to save a kernel that already streams at 0.3–2.1 GB/s on one CPU core; the transfer alone would cost more than the kernel does. Verdict: **GPU `none` for all hotspots**, justified by the flops-per-byte figures above, not by host-API availability (the `max.gpu` path noted in `MOJO_NOTES.md` is available but pointless here).

## Next-phase mapping (ranked)

Use the phases `unroll / simd / parallel / gpu / none` literally:

| hotspot (rank) | phase | evidence |
| --- | --- | --- |
| Row 1 `emit` recursion | **unroll** | 46% of serialize, 100% Python (140k recursive calls, 880k `pieces` extensions, 320k `_split_name` at 391 ns, 160k `qn` at 321 ns). No kernel to vectorise; the next phase should cache `qn` strings and `URI_TO_PREFIX`, and avoid per-node concatenation. |
| Row 2 `escape_batch` glue | **none** | Kernel is 9% of the 105 ms; 91% is encode/join/offsets-loop/per-piece-decode Python. The fix is a Python-side wrapper change (borrowed-buffer single path, one decode), not a Mojo kernel phase. Listed as `none` so the kernel phases do not chase it. |
| Row 3 `add_paragraph`/`Run.text` | **unroll** | 100% Python; 7× over a raw-ET baseline (18.3 vs 2.6 µs/para) from `element()`+`qn`+`_SPLIT_TEXT.split`+wrappers. No SIMD/parallel possible on object construction. |
| Row 4 `parse_xml` ET | **none** | Already C; the gap to upstream lxml (64 ms) is a library choice, not a Mojo phase. |
| Row 5 `Paragraph.text`/`runs` | **unroll** | 100% Python getter chain (`qn` per access); cache with row 1. |
| Row 6 `write_package` zlib | **none** | C zlib is 30 ms of the 32 ms; nothing to do. |
| Row 7 table build/save | **unroll** | Same Python `emit`/`cell.text` setters as rows 1/3. |
| Row 8 `_namespace_prefixes` | **unroll** | 95 ms per serialize for a document-invariant map; cache it. |
| Row 9 `mdx_escape_batch` raw | **parallel** | Serial 60k-string loop, 1.1 GB/s effective over 8.5 MB touched; strings are independent; case `<1 MiB` per string gives no intra-string parallelism, so parallelism must be over strings (or tasks shared with row 11). SIMD is already used (`BYTE_W=32`) and is not the limiter — the double pass + scalar special path is. |
| Row 10 `mdx_escape_one` small | **none** | 132 B typical call, 16 µs/call fixed (4.7 µs ctypes + 10.6 µs wrapper) — overhead-bound, not math-bound. |
| Row 11 `mdx_escape_one` large | **parallel** | 16 tasks run serially, 2 passes, specials fall back to scalar 330 MB/s. Largest single-call Mojo win available; `PARALLEL_ESCAPE_BYTES` gating shows intent that was never wired to `parallelize`. |
| Row 12 `mdx_analyze_xml` | **parallel** | Scalar 716 MB/s single-core; 4.8 MB collapses with threaded histograms. Not SIMD (tag parser is branchy). |
| Rows 13–14 zip/read/wrappers | **none** | C stdlib or negligible fixed cost. |

No row is assigned `simd` or `gpu`: escape already vectorises (`BYTE_W=32` SIMD compares + bulk copies) and its flops/byte (0 FP, ~3–5 int ops) cannot justify a GPU; `analyze_xml`'s scalar state machine does not vectorise profitably. The only kernel work that remains is **parallelising the two serial task loops** (batch strings, large-single 16 tasks, analyze scan).

## Notes on measurement honesty

- Timing is best-of-5 (or best-of-7 where labelled); means are quoted alongside where spread was wide. Machine noise on this shared host is visible (e.g. probe2 `open_read` runs 371–876 ms; official bench is the authoritative e2e). All decomposition numbers are single-session bests on the same fixture, so cross-probe ratios hold even where absolutes wobble by ±10%.
- One early fresh-save probe mislabelled a timing wrapper that enclosed build+serialize; it was caught and re-measured (true save-only fresh 577 ms). The slower-than-upstream save conclusion uses the corrected figure and is robust at either 517 or 577 ms against upstream's 83–91 ms.
- `bytes touched` for Python rows counts object/alloc traffic, not cache lines; kernel rows count logical buffer read+write. Flop counting for Python rows is reported as ~0 with call counts instead, because there is no arithmetic to count. Recorded probe scripts were kept out of the repo (`/tmp/probe*.py`); the only committed file is this one.
