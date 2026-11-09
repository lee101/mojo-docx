# VERIFY phase — benchmark and parity verification

No production code was changed in this phase (no failing test was found).
Only `bench/verify.md` was rewritten; `README.md` figures reproduce within
20% and were left as-is.

## Method

All runs in this session, in order:

1. `pixi run build && pixi run test` → build OK, **46 passed in 2.85s**, exit 0.
2. `pixi run bench` ×4 (official, flock-wrapped, this session). Machine:
   `x86_64, Linux 6.8.0-147-generic, Python 3.13.14` (same as README header).
3. Decomposition probes with `pixi run python` (transcribed below) to check
   same-input / no-skip-work per row.
4. `git log -p -- tests/` and `git log --stat` for every commit.

## Official bench — four runs this session

```
Run 1                                    Run 2
Build + save 20k paragraphs  1030.64 / 7326.07  7.11x    1251.61 / 7560.20  6.04x
Open + read 20k paragraphs    398.74 / 1256.75  3.15x     358.89 / 1253.21  3.49x
Round-trip save 20k paragr.    37.80 /   66.89  1.77x      35.99 /   62.31  1.73x
Build + save 200x20 table     109.84 /  524.45  4.77x     113.61 /  490.78  4.32x
Escape 8 MiB OOXML text        27.67 /   48.46  1.75x      24.97 /   48.04  1.92x

Run 3                                    Run 4
Build + save 20k paragraphs  1081.26 / 8269.11  7.65x    1052.97 / 7553.69  7.17x
Open + read 20k paragraphs    407.99 / 1245.46  3.05x     399.75 / 1122.56  2.81x
Round-trip save 20k paragr.    36.19 /   68.85  1.90x      34.81 /   65.72  1.89x
Build + save 200x20 table     112.94 /  580.16  5.14x     138.01 /  520.56  3.77x
Escape 8 MiB OOXML text        26.23 /   45.42  1.73x      27.52 /   46.54  1.69x
```

(Format: mojo-docx ms / python-docx 1.2.0 ms / ratio. Full output captured in
session log `/tmp/verify-bench-runs.log`.)

## Reproduction within 20% (README values)

README values are medians of the prior session's four runs; they are not
replaced here because every row reproduces within 20% this session.
Median of this session's four runs, and deviation from README:

| workload | mojo median this session | README | upstream median this session | README | ratio this session | README |
| --- | ---: | --- | ---: | --- | ---: | --- |
| Build + save 20k paragraphs | 1067.12 ms | 1065.68 ms (+0.1%) | 7556.94 ms | 7493.14 ms (+0.9%) | 7.08x | 7.03x (+0.7%) |
| Open + read 20k paragraphs | 399.25 ms | 386.15 ms (+3.4%) | 1249.34 ms | 1194.20 ms (+4.6%) | 3.13x | 3.09x (+1.3%) |
| Round-trip save 20k paragraphs | 36.09 ms | 37.13 ms (−2.8%) | 66.31 ms | 65.36 ms (+1.5%) | 1.84x | 1.76x (+4.4%) |
| Build + save 200x20 table | 113.28 ms | 118.45 ms (−4.4%) | 522.50 ms | 515.78 ms (+1.3%) | 4.61x | 4.35x (+6.0%) |
| Escape 8 MiB OOXML text | 26.88 ms | 25.43 ms (+5.7%) | 47.29 ms | 45.68 ms (+3.5%) | 1.76x | 1.80x (−2.2%) |

Per-run check: all four runs fall within ±20% of the README figure on every
mojo column and every upstream column, and on every ratio column except the
table ratio in run 3 (+18.1% vs README 4.35x, i.e. still inside 20% — the
largest single deviation in the whole set). No figure exceeds 20%, so no
README correction was required. No row was removed or reworded; no row where
the port is slower exists as a whole-row (see sub-paths below).

## Fairness checks (same input / no skipped work)

`bench/bench.py` constructs both sides from the same constants
(`PARAGRAPHS=20000`, same `TEXT`, same fixture file) and passes
`PYTHONPATH` stripped upstream subprocesses against the real
`python-docx 1.2.0` in `.pixi/envs/default/site-packages` (verified:
`docx.__file__` in site-packages, `docx.__version__ 1.2.0`). Mojo side runs
with `PYTHONPATH=python`. Same `best-of-N` timing on both sides with matched
repeat counts (2/3/3/2/3).

Decomposition measured this session (`pixi run python` probes):

- **Build + save 20k paragraphs.** Same construction on both sides. Mojo
  build-only ~519 ms (this session), fresh `serialize_xml` alone ~527 ms,
  bench `build_save` ~1031–1252 ms e2e — i.e. the bench always builds a fresh
  `Document` and saves it, so the full `serialize_xml` + ZIP runs every
  repetition. No cache skip. Upstream build loop is ~7.9 s (analysis.md).
  Both produce a valid `.docx` with 20,000 paragraphs. Fair; port faster.
- **Open + read 20k paragraphs.** Open-only this session: mojo ~196 ms vs
  upstream ~122 ms (port is **slower** at parse — `ET.fromstring` +
  `analyze_xml` vs lxml). Read-only paragraph text: mojo ~141 ms vs upstream
  ~1067 ms. Combined open+read: mojo ~359–408 ms vs upstream ~1123–1257 ms,
  and both return the same checksum `sum(len(p.text)) = 2,528,890` chars over
  20,000 paragraphs. Same fixture input, same read output. Fair. The
  "port is slower at parse, faster at read" split is real but the row's
  total still favours the port; the aggregate row was kept as-is.
- **Round-trip save 20k paragraphs.** This is the asymmetric row, and it
  is **disclosed, not hidden**. `bench.py` loads once and calls `save`
  repeatedly on the same object. Mojo keeps an unmodified loaded part as
  its original bytes (`Document._serialized_parts` returns cached parts
  while `_dirty` is False, and `_dirty` is False after open —
  `python/docx/document.py:323-328`) so every call is ZIP-only (~33–38 ms
  this session). Upstream has no such cache and re-serializes via lxml on
  every save (~62–69 ms). Verified: mojo cached save reuses bytes (fixture
  65,076 B = round-trip output 65,076 B), mutation flips `_dirty` True and
  forces full `serialize_xml` on next save, and the existing test
  `test_loaded_document_cache_invalidates_after_each_mutation` covers the
  invalidation. The output (65,076 B mojo vs 98,595 B upstream —
  own serializer, different ZIP/XML formatting) is a valid document in
  both cases. Verdict: **unfair as a serializer comparison** (ZIP-only vs
  full lxml serialize) and **fair only as a cached-unmodified-save API
  comparison** — the cache *is* the implementation's feature, and README
  documents it in the paragraph following the table. It is not bench
  cheating (no measurement without the save, no skipped serialization that
  the API promises), but a caller who mutates before saving pays the full
  serialize cost and is slower in that path — see `bench/analysis.md` §3
  which already flags fresh-save serialization as slower. The row was kept
  as-is, unreworded, as instructed.
- **Build + save 200x20 table.** Identical construction on both sides
  (`add_table(200,20)`, 4,000 `cell.text` assignments, save to
  `BytesIO`). Mojo output 14,844 B this session (upstream 48,921 B —
  compact serializer, but same 200×20 cell data). No caching (fresh
  `Document` per repetition, `_dirty` True). Fair.
- **Escape 8 MiB OOXML text.** Same input `TEXT*65536` (7,864,320 chars =
  8,650,752 UTF-8 bytes) on both sides. Mojo: `escape_batch([input])` —
  single-string path uses CPython borrowed UTF-8 view + `mdx_escape_one`,
  output 8,781,824 chars (131,072 `&amp;`, 131,072 `&lt;`, verified this
  session). Upstream: `etree.tostring(OxmlElement('w:t'))` — lxml
  serialization of the element including tags and its default ASCII encoding
  (`&#8212;` etc., 11,403,346 B bytes vs 8,781,906 chars unicode; inner
  escaped text identical counts). Upstream pays tag + ASCII entity framing
  that the mojo kernel doesn't; that is what python-docx's serialization
  does and the bench measures the kernel against it. The work is not
  skipped on either side, but the row is **unfair as a kernel-equivalence
  shootout** (text-only UTF-8 escape vs full-element ASCII serialization —
  upstream writes ~2.6 MB extra entity/ASCII bytes plus tags), and fair
  only as "kernel vs python-docx's serialization of the same text".
  Noted here for transparency; row kept as-is per instructions.

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

## What was changed

- `bench/verify.md`: this file (per-run data from this session, medians,
  fairness verdicts, git-history findings).
- `README.md`: **unchanged** — every figure reproduces within 20% this
  session (largest deviation +18.1% on a single ratio in a single run;
  all medians within ±6%).
- No Python or Mojo source changed; no test changed.

## Final verification

`pixi run build && pixi run test` — green in this session (first run
46 passed, exit 0; re-run at the end of the phase to confirm still green).
