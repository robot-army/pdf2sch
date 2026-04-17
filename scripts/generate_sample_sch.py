#!/usr/bin/env python3
"""
Generate a .kicad_sch from a PDF schematic (or a built-in sample).

Used by CI to produce a schematic that kicad-cli can then export to SVG for
the screenshot artefact.

Usage::

    # Convert a real PDF
    python scripts/generate_sample_sch.py path/to/schematic.pdf output.kicad_sch

    # Generate a synthetic sample (no PDF needed)
    python scripts/generate_sample_sch.py output.kicad_sch
"""

from __future__ import annotations

import os
import sys

# Ensure the repo root is on sys.path when the script is invoked directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_PLUGIN_DIR = os.path.join(_REPO_ROOT, "kicad_plugin", "plugins")
for _p in (_REPO_ROOT, _PLUGIN_DIR):
    if _p not in sys.path:
        sys.path.append(_p)  # append so repo-root pdf2sch.py takes precedence over plugin

from pdf2sch import PDF2SchPipeline  # noqa: E402

# Load the KiCad writer module directly to avoid the name collision between
# the root-level pdf2sch.py module and the kicad_plugin/plugins/pdf2sch/ package.
import importlib.util as _ilu  # noqa: E402

_writer_spec = _ilu.spec_from_file_location(
    "_pdf2sch_writer",
    os.path.join(_PLUGIN_DIR, "pdf2sch", "writer.py"),
)
_writer_mod = _ilu.module_from_spec(_writer_spec)  # type: ignore[arg-type]
_writer_spec.loader.exec_module(_writer_mod)  # type: ignore[union-attr]
write_kicad_schematic = _writer_mod.write_kicad_schematic


def main(pdf_source: str | None = None, output_path: str | None = None) -> None:
    # Argument parsing: if only one arg is given, treat it as the output path
    # (synthetic sample mode) unless it ends with .pdf.
    if pdf_source is not None and output_path is None:
        if pdf_source.lower().endswith(".pdf"):
            # pdf_source is actually the PDF path; generate output alongside it
            output_path = os.path.splitext(pdf_source)[0] + ".kicad_sch"
        else:
            # Only an output path was passed; use synthetic detector
            output_path = pdf_source
            pdf_source = None

    if output_path is None:
        output_path = os.path.join(
            _REPO_ROOT, "tests", "fixtures", "sample.kicad_sch"
        )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if pdf_source is not None:
        # Real PDF → use the pymupdf-based detector
        try:
            from pdf_detector import PDFDetector  # noqa: F401
            pipeline = PDF2SchPipeline(detector=PDFDetector())
        except ImportError:
            print(
                "WARNING: pdf_detector not available (install pymupdf); "
                "falling back to synthetic sample.",
                file=sys.stderr,
            )
            pipeline = PDF2SchPipeline()
            pdf_source = "cn0359"
        detection = pipeline.detect(pdf_source)
    else:
        # Synthetic sample using the built-in cn0359 fixture detector
        pipeline = PDF2SchPipeline()
        detection = pipeline.detect("cn0359")

    model = pipeline.build_model(detection)
    # Auto-accept all review questions so the script is non-interactive.
    model = pipeline.review_model(model, input_fn=lambda _: "y")

    write_kicad_schematic(model, output_path)
    print(f"Schematic written to: {output_path}")
    print(f"  Components: {len(model.components)}")
    print(f"  Nets:       {len(model.nets)}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 2:
        main(pdf_source=args[0], output_path=args[1])
    elif len(args) == 1:
        main(pdf_source=args[0])
    else:
        main()
