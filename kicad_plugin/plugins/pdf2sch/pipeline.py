"""
Re-export the pdf2sch pipeline classes so the plugin package is self-contained
when running inside KiCad's Python environment.

KiCad adds ``<pcm_install>/plugins/`` to ``sys.path``, so this package is
importable as ``pdf2sch``.  The root ``pdf2sch.py`` module has the *same* name
as this package, so a plain ``import pdf2sch`` would resolve to the already-
loaded package rather than the root file.  We therefore load the root module by
file path using ``importlib.util`` and register it under the private name
``_pdf2sch_core`` so both can coexist in ``sys.modules``.
"""

from __future__ import annotations

import importlib.util
import os
import sys

_MODULE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "pdf2sch.py")
)
_CORE_NAME = "_pdf2sch_core"

if _CORE_NAME not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_CORE_NAME, _MODULE_PATH)
    _core = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
    sys.modules[_CORE_NAME] = _core
    _spec.loader.exec_module(_core)  # type: ignore[union-attr]

_core = sys.modules[_CORE_NAME]

# Re-export so callers can do: from pdf2sch.pipeline import PDF2SchPipeline
PDF2SchPipeline = _core.PDF2SchPipeline
PipelineConfig = _core.PipelineConfig
DetectionOutput = _core.DetectionOutput
DetectedSymbol = _core.DetectedSymbol
DetectedWire = _core.DetectedWire
SchematicModel = _core.SchematicModel
Component = _core.Component
Net = _core.Net
convert_pdf_to_kicad = _core.convert_pdf_to_kicad
