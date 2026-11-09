# VERIFY phase — benchmark and parity verification

No production code was changed in this phase (no failing test was found).
Only `README.md` figures and this file were added/changed.

## Method

All runs in this session, in order:

1. `pixi run build && pixi run test` → build OK, **46 passed in 2.73s**, exit 0.
2. `pixi run bench` ×4 (official, flock-wrapped, this session). Machine:
   `x86_64, Linux 6.8.0-147-generic, Python 3.13.14`, CPU
   `Intel(R) Xeon(R) CPU E5-2697 v4 @ 2.30GHz` (72 cores). README previously
   claimed `Linux 6.8.0-136-generic` on the same host type.
3. Decomposition probes with `pixi run python` (scripts in `/tmp/verify-*.log`
   style, transcribed below) to check same-input / no-skip-work per row.
4. `git log -p -- tests/` and per-commit `git log --stat` for removed
   assertions / loosened tolerances.

## Official bench — four runs this session

```
Run 1                                    Run 2
Build + save 20k paragraphs  1120.04 / 7693.19  6.87x    1014.00 / 7808.94  7.70x
Open + read 20k paragraphs    391.17 / 1168.69  2.99x     386.96 / 1218.92  3.15x
Round-trip save 20k paragr.    36.70 /   65.12  1.77x      38.64 /   65.60  1.70x
Build + save 200x20 table     141.82 /  497.12  3.51x     116.36 /  534.01  4.59x
Escape 8 MiB OOXML text        24.84 /   43.80  1.76x      28.82 /   45.70  1.59x

Run 3                                    Run 4
Build + save 20k paragraphs  1056.76 / 7579.64  7.17x    1074.60 / 7234.27  6.73x
Open + read 20k paragraphs    372.30 / 1394.20  3.74x     384.33 / 1113.79  2.90x
Round-trip save 20k paragr.    35.74 /   69.71  1.95x      37.56 /   62.32  1.66x
Build + save 200x20 table     112.98 /  567.59  5.02x     120.54 /  507.55  4.21x
Escape 8 MiB OOXML text        23.71 /   45.66  1.93x      26.02 /   46.27  1.78x
```

(Format: mojo-docx ms / python-docx 1.2.0 ms / ratio. Full `pixi run bench`
output captured in session logs `/tmp/verify-bench-{1..4}.log`.)

README values are **medians of these four runs**. Ratio is
`median(upstream) / median(mojo)` recomputed from the median ms values
(arithmetic verified; e.g. build-save `7493.14 / 1065.68 = 7.03`).

| workload | mojo median | upstream median | ratio | README before |
| --- | ---: | ---: | ---: | ---: |
| Build + save 20k paragraphs | 1065.68 ms | 7493.14 ms | 7.03x | 992.70 / 7543.35 / 7.60x |
| Open + read 20k paragraphs | 386.15 ms | 1194.20 ms | 3.09x | 448.73 / 1229.50 / 2.74x |
| Round-trip save 20k paragraphs | 37.13 ms | 65.36 ms | 1.76x | 36.72 / 62.67 / 1.71x |
| Build + save 200x20 table | 118.45 ms | 515.78 ms | 4.35x | 119.96 / 476.28 / 3.97x |
| Escape 8 MiB OOXML text | 25.43 ms | 45.68 ms | 1.80x | 32.91 / 44.49 / 1.35x |

## Reproduction within 20%

Checked each README figure against each of the four runs (±20% window).

- **Build + save 20k paragraphs** — all 4 runs within 20% on all three
  columns (mojo +2.1%…+12.8%, upstream +0.5%…+3.5%, ratio −9.6%…+1.3%).
  Reproduces.
- **Open + read 20k paragraphs** — mojo and upstream within 20% all runs;
  ratio outside 20% in run 3 only (+36.5%, driven by upstream 1394.20 ms
  outlier). Reproduces except that one ratio outlier; median ratio (3.09x)
  replaces it.
- **Round-trip save 20k paragraphs** — all 4 runs within 20% on all columns.
  Reproduces.
- **Build + save 200x20 table** — mojo within 20% all runs; upstream within
  20% all runs (+4.4%…+19.2%); ratio outside 20% in run 3 only (+26.4%,
  upstream outlier). American's median replaces it.
- **Escape 8 MiB OOXML text** — **does not reproduce as stated.**
  Upstream within 20% all runs (−1.6%…+4.0%), but mojo was
  −24.5% / −12.4% / −28.0% / −21.0% vs README 32.91 ms in runs 1–4, and
  ratio was +30.4% / +17.8% / +43.0% / +31.5% vs README 1.35x. The README
  understated this row's speedup; the corrected median figures above
  (25.43 ms / 45.68 ms / 1.80x) are what was measured.

Despite the per-run scatter, the prior README table as a whole could not
be kept: it quoted a single run from `Linux 6.8.0-136` (prior bench) and
at least the Escape row falls outside the 20% window in three of four
fresh runs. Per the task rule ("a number you did not measure in this
session does not go in the README"), all five rows were replaced by
medians of fresh runs. That happens to move four rows by <20% and one row
(Escape) by more — in the direction of a larger speedup, not a smaller
one. No row flipped sign; no row where the port is slower was removed or
reworded (see §3 below).

## Fairness checks (same input / no skipped work)

`bench/bench.py` constructs both sides from the same constants
(`PARAGRAPHS=20000`, same `TEXT`, same fixture file) and passes
`PYTHONPATH` stripped upstream subprocesses against the real
`python-docx 1.2.0` in `.pixi/envs/default/site-packages` (verified:
`docx.version 1.2.0`, `docx.__file__` in site-packages). Mojo side runs
with `PYTHONPATH=python` and `DOCX` shim version `0.1.0`.

Decomposition measured this session (`pixi run python` probes):

- **Build + save 20k paragraphs.** Mojo build-only ~323–339 ms, but a fresh
  first save (serialize+zip) is ~596–604 ms and the replica of the bench
  `build_save` closure is ~994 ms — i.e. the bench always builds a fresh
  `Document` and saves it, so the full `serialize_xml` + ZIP runs every
  repetition. No cache skip. Upstream build-only ~8254 ms. Both produce a
  valid `.docx` with 20,000 paragraphs. Fair, and the port is faster.
  The mojo save-only ~45 ms figure only appears after a first save
  (`_dirty` False); the bench never hits it in this row.
- **Open + read 20k paragraphs.** Open-only: mojo ~184 ms vs upstream
  ~112 ms (port is **slower** at parse — `ET.fromstring` + `analyze_xml`
  vs lxml). Read-only paragraph text: mojo ~173 ms vs upstream ~1093 ms.
  Combined open+read: mojo ~357–391 ms vs upstream ~1169–1394 ms, and both
  return the same checksum `sum(len(p.text)) = 2,528,890` chars over
  20,000 paragraphs. Same fixture input, same read output. Fair. The
  "port is slower at parse, faster at read" split is real but the row's
  total still favours the port; the aggregate row was not split or
  reworded.
- **Round-trip save 20k paragraphs.** This is the asymmetric row, and it
  is **disclosed, not hidden**. `bench.py` loads once and calls `save`
  repeatedly on the same object. Mojo keeps an unmodified loaded part as
  its original bytes (`Document._serialized_parts` returns cached parts
  while `_dirty` is False, and `_dirty` is False after open) so every
  call—including the first—is ZIP-only (~31–39 ms). Upstream has no such
  cache and re-serializes via lxml on every save (~62–70 ms). Verified:
  mojo cached save reuses bytes (fixture 65,076 B = round-trip output
  65,076 B), mutation flips `_dirty` True and forces full
  `serialize_xml` (~546 ms xml-only, ~596–604 ms fresh save) on next save,
  and the existing test
  `test_loaded_document_cache_invalidates_after_each_mutation` covers
  the invalidation. The output (65,076 B mojo vs 98,595 B upstream —
  own serializer, different ZIP/XML formatting) is a valid document in
  both cases. Verdict: same call, same unmodified input, different
  internal work because the cache *is* the implementation's feature
  (and README documents it in the paragraph following the table). It is
  not bench cheating (no measurement without the save, no skipped
  serialization that the API promises), but a caller who mutates before
  saving pays the full serialize cost and is slower in that path — see
  `bench/analysis.md` which already flags fresh-save serialization as
  slower. The row was kept as-is, unreworded, as instructed.
- **Build + save 200x20 table.** Identical construction on both sides
  (`add_table(200,20)`, 4,000 `cell.text` assignments, save to
  `BytesIO`). Mojo output 14,844 B, upstream 48,921 B (compact serializer,
  but same 200×20 cell data; `cell(0,0)='0:0 & data'`,
  `cell(199,19)='199:19 & data'` verified). No caching (fresh
  `Document` per repetition, `_dirty` True). Fair.
- **Escape 8 MiB OOXML text.** Same input `TEXT*65536` (7,864,320 chars =
  8,650,752 UTF-8 bytes) on both sides. Mojo: `escape_batch([input])` —
  single-string path uses CPython borrowed UTF-8 view + `mdx_escape_one`,
  output 8,781,824 chars (131,072 `&amp;`, 131,072 `&lt;`, 0 `&gt;`).
  Upstream: `etree.tostring(OxmlElement('w:t'))` — lxml serialization of
  the element including tags and its default ASCII encoding
  (`&#8212;` etc., 11,403,346 B bytes vs 8,781,906 chars unicode;
  inner escaped text identical counts). Upstream pays tag + ASCII
  entity framing that the mojo kernel doesn't; that is what python-docx's
  serialization does and the bench measures the kernel against it. The
  work is not skipped on either side; the outputs differ in framing as
  they must (kernel vs full serializer). Noted here for transparency.

No benchmark row was found where one side skips work the other performs
in the sense of a bench bug. The round-trip cache and the parse/read
split are the only asymmetries, both explained above and both disclosed
in `bench/analysis.md` and the README cache paragraph.

## Test parity — git history

`git log -p -- tests/` spans two commits that touch tests:

- `85668bc` (initial port): creates `tests/conftest.py` and
  `tests/test_parity.py` wholesale.
- `d93fc55` (accel SIMD/parallel/GPU pass): **only adds** 8 lines
  (`test_mojo_escape_multiple_entities_in_simd_block`). No assertion
  removed, no tolerance loosened.

No later commit touches `tests/` (`git log --stat` for
`13644fb`, `2c4f67f`, `e21ea77`, `859c94f`, `5479504`, `3f5b782` shows
zero `tests/` files changed). Current suite still asserts parity
directly against upstream:

- `test_new_document_defaults_match_upstream`,
  `test_paragraph_text_roundtrip_matches_upstream` (upstream opens
  mojo-written files),
  `test_open_upstream_document_with_runs_and_table` (mojo opens
  upstream-written files),
  `test_run_formatting_is_readable_by_upstream`,
  `test_table_saved_here_matches_upstream_shape`,
  `test_picture_dimensions_and_upstream_readability`,
  `test_page_break_is_preserved_by_upstream` — all via the `upstream`
  fixture (`tests/conftest.py`, strips `PYTHONPATH`, runs real
  python-docx in a subprocess).
- Exact-equality assertions everywhere except `pytest.approx` on unit
  conversions in `test_paragraph_format_lengths_roundtrip` and
  `test_nested_table_content_and_width_roundtrip` (abs=0.001/0.01 on
  inches/cm — same since initial commit, not loosened).

Nothing was removed or loosened, so **nothing to restore**.

`2c4f67f` ("phase test") changes only `python/docx/*.py` (bug fixes:
`__len__` moved, `_reject_negative_extent`, table/section/shape/shared
fixes) — no test weakening, consistent with that history.

## What was changed

- `README.md`: benchmark header kernel note
  (`Linux 6.8.0-147-generic`, "medians of four runs") and all five rows
  replaced with the medians above. Cache/GPU explanatory paragraphs and
  method wording untouched. No row removed, no slower-than-upstream row
  reworded (there is no such row as a whole; the slower sub-paths — parse
  in open+read and fresh/mutated serialize — are recorded in this file
  and in `bench/analysis.md`).
- `bench/verify.md`: this file.
- No Python or Mojo source changed; no test changed.

## Final verification

`pixi run build && pixi run test` — green in this session (first run
46 passed, exit 0; re-run at the end of the phase after the README edit
to confirm still green).
