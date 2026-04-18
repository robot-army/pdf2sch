# Agent Notes — pdf2sch development log

> **Purpose:** Continuity document for AI coding agents (or the repo owner) so
> work can be picked up from exactly this point without re-reading history.
> Last updated by: Copilot agent, 2026-04-18.

---

## What the project does

`pdf2sch` converts a PDF schematic (e.g. from KiCad, Altium, PADS) into a
`.kicad_sch` file that KiCad 9 can open.  It does **not** use OCR or ML in the
current codebase — it uses pure geometric heuristics on the PDF drawing
primitives (lines, text spans) extracted by `pymupdf`.

---

## Repository layout

```
pdf2sch.py              Core pipeline dataclasses + PDF2SchPipeline
pdf_detector.py         pymupdf-based geometry detector (main intelligence)
kicad_plugin/
  plugins/pdf2sch/
    writer.py           Writes SchematicModel → .kicad_sch S-expression
    pipeline.py         KiCad plugin entry point
    dialog.py           GUI dialog (for KiCad's pcbnew plugin manager)
    review_dialog.py    Low-confidence net review dialog
    overlay.py          PDF overlay rendering helper
scripts/
  generate_sample_sch.py  CLI: PDF → .kicad_sch + .kicad_pro (used by CI)
tests/                  pytest unit tests
test-data/              Real PDFs + ground-truth .kicad_sch for three circuits:
  realsmall-pdf2sch/    Minimal: 1 LED (D1), 1 resistor (R1), +5V, GND
  stickhub-pdf2sch/     Medium KiCad-exported schematic
  cn0359-AnalogDevices-pdf2sch/  Large Analog Devices eval-board, multi-page
.github/workflows/
  ci.yml                Unit tests on Python 3.11 and 3.12
  kicad_integration.yml Full integration: generate .kicad_sch → kicad-cli SVG
                        → PNG → embed base64 in job summary (mobile viewable)
```

---

## Current status (as of last agent session)

### What works
- **Detection pipeline** (`pdf_detector.py`):
  - Extracts text spans, deduplicates KiCad's double-rendering quirk.
  - Classifies spans as component refs, values, or net labels using heuristics.
  - Extracts axis-aligned wire segments from PDF drawing paths.
  - Filters noisy segments via BFS from anchor points (components + net labels).
  - Union-Find connectivity (Phase A: power nets, Phase B: labelled wire
    clusters, Phase C: unnamed multi-component clusters).
  - Infers component centres from nearby wire-endpoint midpoints.
  - Infers pin axis (H/V) from bounding box of surrounding wire endpoints.
  - Annotates net labels with the nearest wire endpoint + rotation angle.

- **Pipeline** (`pdf2sch.py`):
  - Converts `DetectedSymbol` → `Component` with PDF-space position (snapped
    to KiCad 50-mil grid) and rotation angle derived from pin axis.
  - Passes `wire_segments` (list of mm 4-tuples) through to `SchematicModel`.
  - Low-confidence net review loop (interactive or auto-accept via lambda).

- **Writer** (`kicad_plugin/plugins/pdf2sch/writer.py`):
  - Embeds minimal Device:* symbol library directly in the .kicad_sch (no
    external library lookup needed — kicad-cli works without KiCad installed).
  - Places components at their detected PDF-position; falls back to a grid
    when position is unknown.
  - Emits `(wire ...)` S-expressions for all detected wire segments.
  - Places net labels at detected wire endpoints with correct rotation, or
    falls back to a grid-offset position.

- **CI**:
  - `kicad_integration.yml` installs KiCad 9 from PPA, generates three test
    schematics (realsmall, stickhub, cn0359), exports SVGs via `kicad-cli`,
    converts to PNG (1200 px wide max), and **embeds PNGs as base64 data URIs
    in `$GITHUB_STEP_SUMMARY`** so they render inline in Chrome on Android
    without downloading a zip.  Artifacts are also uploaded as a fallback.

### Known gaps / next priorities

1. **Layout fidelity** — components are placed at their raw PDF coordinates
   converted to mm, but the PDF coordinate system (Y-axis down, origin
   top-left at 72 dpi) is not yet normalised to KiCad's coordinate system
   (Y-axis also down, but origin can be arbitrary).  The result is structurally
   correct but often spatially shifted or mirrored versus the original schematic.
   **Fix:** subtract the bounding-box origin of detected components before
   converting, and add a small page margin offset.

2. **Wire routing** — wires are emitted verbatim from the PDF.  If the PDF
   coordinates land off-grid (not a multiple of 1.27 mm) KiCad will display
   DRC warnings.  **Fix:** snap each wire endpoint to the nearest 1.27 mm grid
   after converting from points to mm.

3. **Net label placement** — labels are placed at wire endpoints but the angle
   logic sometimes produces labels that point inward into the wire rather than
   outward.  Needs a sign-flip check against the wire direction vector.

4. **Multi-pin components** (ICs with many pins) — currently all ICs use
   `Device:U` which has no explicit pins.  Connecting nets to specific IC pins
   requires inferring pin positions from the PDF, which is the hardest part of
   the whole problem.

5. **Ground-truth comparison** — the `realsmall` test-data directory contains
   the reference `.kicad_sch`.  A pytest fixture that runs the detector on
   `realsmall.pdf` and compares component positions / net assignments against
   the reference would give rapid regression feedback without needing kicad-cli.

---

## Local development on Ubuntu with KiCad 9

This is the **recommended next step**: run the full pipeline locally so you
can iterate quickly with immediate visual feedback in KiCad.

### Prerequisites

```bash
# Python dependencies (pymupdf + pytest)
pip install -r requirements.txt

# KiCad 9 (provides kicad-cli)
sudo add-apt-repository --yes ppa:kicad/kicad-9.0-releases
sudo apt-get update
sudo apt-get install -y --no-install-recommends kicad
```

### Convert a PDF schematic

```bash
# Convert → generates /tmp/mysch.kicad_sch + /tmp/mysch.kicad_pro
python scripts/generate_sample_sch.py path/to/schematic.pdf /tmp/mysch.kicad_sch

# Open in KiCad GUI
kicad /tmp/mysch.kicad_pro

# Or export SVG headlessly and view in a browser
kicad-cli sch export svg --output /tmp/ /tmp/mysch.kicad_sch
xdg-open /tmp/mysch.svg
```

### Test against the realsmall ground truth

```bash
python scripts/generate_sample_sch.py \
  test-data/realsmall-pdf2sch/realsmall/realsmall.pdf \
  /tmp/realsmall_generated.kicad_sch

# Compare side-by-side in KiCad, or diff the S-expression text:
diff test-data/realsmall-pdf2sch/realsmall/realsmall.kicad_sch \
     /tmp/realsmall_generated.kicad_sch | head -100
```

### Run the unit tests

```bash
python -m pytest tests/ -v --tb=short
```

### Typical debug loop

1. Edit `pdf_detector.py` (detection heuristics) or `writer.py` (output format).
2. Run `python scripts/generate_sample_sch.py test-data/realsmall-pdf2sch/realsmall/realsmall.pdf /tmp/out.kicad_sch`.
3. Open `/tmp/out.kicad_sch` in KiCad **or** `kicad-cli sch export svg --output /tmp/ /tmp/out.kicad_sch && xdg-open /tmp/out.svg`.
4. Repeat.

The CI job does exactly the same thing; local iteration is faster because you
skip the ~10-minute KiCad install step.

---

## Key design decisions (for the next agent)

- **No external library at runtime** — `writer.py` embeds trimmed Device:*
  symbol definitions directly in the generated `.kicad_sch`.  This is
  intentional: it means the file can be opened on any machine without having
  KiCad's library path configured.

- **PDF coordinates → mm** — conversion factor is `25.4 / 72` (1 PDF point =
  1/72 inch).  The Y-axis in PDF is top-down (origin top-left), same as KiCad,
  so no axis flip is needed — but **the origin offset must be subtracted** when
  placing components (gap #1 above).

- **1.27 mm grid** — all KiCad coordinates must be multiples of 1.27 mm
  (50 mil) for pins to connect cleanly.  `_snap_mm()` in `pdf2sch.py` does this.

- **Inline symbol library** — the `lib_symbols` block at the top of the
  `.kicad_sch` lists only the symbols actually used in this schematic, so the
  file is self-contained.

---

## Files NOT to break

- `tests/test_pdf2sch.py` — covers pipeline dataclasses, component dedup,
  review loop, and KiCad text generation.
- `tests/test_pdf_detector.py` — covers individual detector helpers
  (`_is_ref`, `_is_net_name`, `_infer_component_centers_and_axes`, etc.).
- `tests/test_plugin_writer.py` — covers the writer's S-expression output.
- `tests/test_plugin_action.py` — covers the KiCad plugin action entry point.

All four suites must pass before any PR is merged (enforced by `ci.yml`).
