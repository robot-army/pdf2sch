#!/usr/bin/env python3
"""
Generate a sample .kicad_sch from the built-in CN0359 fixture.

Used by CI to produce a schematic that kicad-cli can then export to SVG for
the screenshot artefact.  Outputs to ``tests/fixtures/sample.kicad_sch`` by
default (path can be overridden with the first positional argument).

Usage::

    python scripts/generate_sample_sch.py [output_path]
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
        sys.path.insert(0, _p)

from pdf2sch import PDF2SchPipeline  # noqa: E402
from pdf2sch.writer import write_kicad_schematic  # noqa: E402


def main(output_path: str | None = None) -> None:
    if output_path is None:
        output_path = os.path.join(
            _REPO_ROOT, "tests", "fixtures", "sample.kicad_sch"
        )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # The built-in detector recognises "cn0359" in the source string and returns
    # a realistic sample detection.
    pipeline = PDF2SchPipeline()
    detection = pipeline.detect("cn0359")
    model = pipeline.build_model(detection)
    # Auto-accept all review questions so the script is non-interactive.
    model = pipeline.review_model(model, input_fn=lambda _: "y")

    write_kicad_schematic(model, output_path)
    print(f"Sample schematic written to: {output_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
