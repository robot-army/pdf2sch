"""
Unit tests for kicad_plugin/plugins/pdf2sch/writer.py.

No KiCad installation required – the writer is pure Python.

We load ``pipeline.py`` and ``writer.py`` by absolute path via
``importlib.util.spec_from_file_location`` so the module is imported without
triggering the plugin package's ``__init__.py`` (which needs pcbnew) and
without clashing with the root ``pdf2sch.py`` module.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest

# ---------------------------------------------------------------------------
# Load plugin submodules by file path to sidestep the pdf2sch name collision
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PLUGIN_PKG = os.path.join(_REPO_ROOT, "kicad_plugin", "plugins", "pdf2sch")


def _load(module_name: str, rel_path: str):
    path = os.path.join(_PLUGIN_PKG, rel_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# pipeline.py must be loaded first so _pdf2sch_core ends up in sys.modules
_pipeline = _load("_test_pipeline", "pipeline.py")
_writer = _load("_test_writer", "writer.py")

render_kicad_schematic = _writer.render_kicad_schematic
write_kicad_schematic = _writer.write_kicad_schematic

Component = _pipeline.Component
Net = _pipeline.Net
SchematicModel = _pipeline.SchematicModel
PDF2SchPipeline = _pipeline.PDF2SchPipeline
DetectedSymbol = _pipeline.DetectedSymbol
DetectedWire = _pipeline.DetectedWire
DetectionOutput = _pipeline.DetectionOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_model() -> SchematicModel:
    return SchematicModel(
        components=[
            Component("R1", "10k", "Device:R", "Resistor_SMD:R_0603_1608Metric"),
            Component("C1", "100n", "Device:C", "Capacitor_SMD:C_0603_1608Metric"),
            Component("U1", "ADuCM350", "Device:U", "QFN-56"),
        ],
        nets=[
            Net("VDD", ["R1.1", "U1.1"]),
            Net("GND", ["C1.2", "U1.2"]),
            Net("SENSE", ["R1.2", "C1.1", "U1.12"]),
        ],
        pages=1,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWriterOutput(unittest.TestCase):
    def test_output_starts_with_kicad_sch(self):
        out = render_kicad_schematic(_simple_model())
        self.assertTrue(out.strip().startswith("(kicad_sch"))

    def test_output_ends_with_closing_paren(self):
        out = render_kicad_schematic(_simple_model())
        self.assertTrue(out.strip().endswith(")"))

    def test_format_version_present(self):
        out = render_kicad_schematic(_simple_model())
        self.assertIn("(version 20231120)", out)

    def test_generator_tag_present(self):
        out = render_kicad_schematic(_simple_model())
        self.assertIn('(generator "pdf2sch")', out)

    def test_all_component_references_present(self):
        model = _simple_model()
        out = render_kicad_schematic(model)
        for comp in model.components:
            self.assertIn(f'"Reference" "{comp.ref}"', out)

    def test_all_component_values_present(self):
        model = _simple_model()
        out = render_kicad_schematic(model)
        for comp in model.components:
            self.assertIn(f'"Value" "{comp.value}"', out)

    def test_lib_ids_present(self):
        model = _simple_model()
        out = render_kicad_schematic(model)
        for comp in model.components:
            self.assertIn(f'(lib_id "{comp.symbol}")', out)

    def test_net_labels_present(self):
        model = _simple_model()
        out = render_kicad_schematic(model)
        for net in model.nets:
            self.assertIn(f'(text "{net.name}")', out)

    def test_lib_symbols_section_present(self):
        out = render_kicad_schematic(_simple_model())
        self.assertIn("(lib_symbols", out)

    def test_sheet_instances_present(self):
        out = render_kicad_schematic(_simple_model())
        self.assertIn("(sheet_instances", out)

    def test_multi_page_sheet_instances(self):
        model = SchematicModel(
            components=[Component("R1", "10k", "Device:R", "Unknown")],
            nets=[],
            pages=3,
        )
        out = render_kicad_schematic(model)
        self.assertIn('(page "1")', out)
        self.assertIn('(page "2")', out)
        self.assertIn('(page "3")', out)

    def test_duplicate_lib_ids_only_defined_once(self):
        model = SchematicModel(
            components=[
                Component("R1", "10k", "Device:R", "Unknown"),
                Component("R2", "22k", "Device:R", "Unknown"),
            ],
            nets=[],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertEqual(out.count('(symbol "Device:R"'), 1)

    def test_unknown_lib_id_falls_back_to_generic_box(self):
        model = SchematicModel(
            components=[Component("X1", "MyIC", "Vendor:CustomIC", "Unknown")],
            nets=[],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertIn("(lib_symbols", out)
        self.assertIn('"Vendor:CustomIC"', out)

    def test_write_to_file(self):
        model = _simple_model()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.kicad_sch")
            write_kicad_schematic(model, path)
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("(kicad_sch", content)

    def test_review_required_net_name_appears_in_labels(self):
        model = SchematicModel(
            components=[Component("R1", "10k", "Device:R", "Unknown")],
            nets=[Net("REVIEW_REQUIRED_SENSE", ["R1.1"])],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertIn("REVIEW_REQUIRED_SENSE", out)

    def test_pipeline_output_round_trips_through_writer(self):
        """Pipeline output should be consumable by the writer without errors."""
        pipeline = PDF2SchPipeline(
            detector=lambda _: DetectionOutput(
                symbols=[
                    DetectedSymbol("U1", "ADuCM350", "QFN-56"),
                    DetectedSymbol("R1", "10k", "0603"),
                ],
                wires=[
                    DetectedWire("VDD", ["U1.1", "R1.1"], confidence=0.99),
                    DetectedWire("SENSE", ["U1.12", "R1.2"], confidence=0.55),
                ],
                text_items=[],
                pages=2,
            )
        )
        detection = pipeline.detect("dummy.pdf")
        model = pipeline.build_model(detection)
        model = pipeline.review_model(model, input_fn=lambda _: "y")
        out = render_kicad_schematic(model)
        self.assertIn("(kicad_sch", out)
        self.assertIn("U1", out)
        self.assertIn("R1", out)
        self.assertIn("VDD", out)


if __name__ == "__main__":
    unittest.main()
