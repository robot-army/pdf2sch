# pdf2sch

Convert PDF schematics into KiCad schematics with a human-in-the-loop review loop.

## Current MVP

This repository now includes a minimal executable pipeline in `/home/runner/work/pdf2sch/pdf2sch/pdf2sch.py` that:

- Detects symbols/wires/text from a PDF source via a pluggable detector interface (placeholder for CV + OCR + ML)
- Filters likely sheet border/title block text
- Builds a structured component list + netlist
- Maps components to KiCad library symbols/footprint hints
- Prioritizes netlist correctness by asking review questions for low-confidence nets
- Generates KiCad schematic text output
- Preserves multi-page and hierarchical-sheet metadata in the generated schematic
- Uses a `PipelineConfig` object (uconfig-style declarative configuration) so detection/review/mapping rules can be tuned without changing core pipeline flow

## Run

```bash
cd /home/runner/work/pdf2sch/pdf2sch
python pdf2sch.py
```

Enter a PDF path or URL when prompted (for example the CN0359 PDF URL from the issue statement).

## Test

```bash
cd /home/runner/work/pdf2sch/pdf2sch
python -m unittest discover -s tests -v
```
