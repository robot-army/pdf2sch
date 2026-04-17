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
        self.assertIn("(version 20250114)", out)

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

    # ------------------------------------------------------------------
    # New symbol stubs
    # ------------------------------------------------------------------

    def test_crystal_stub_has_two_pins(self):
        model = SchematicModel(
            components=[Component("Y1", "16MHz", "Device:Crystal", "")],
            nets=[],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertIn('"Device:Crystal"', out)
        self.assertEqual(out.count('(number "1"'), 1)
        self.assertEqual(out.count('(number "2"'), 1)

    def test_q_npn_stub_has_three_pins(self):
        model = SchematicModel(
            components=[Component("Q1", "2N3904", "Device:Q_NPN", "")],
            nets=[],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertIn('"Device:Q_NPN"', out)
        # Pins 1 (B), 2 (C), 3 (E)
        self.assertEqual(out.count('(number "1"'), 1)
        self.assertEqual(out.count('(number "2"'), 1)
        self.assertEqual(out.count('(number "3"'), 1)

    def test_connector_stub_has_one_pin(self):
        model = SchematicModel(
            components=[Component("J1", "Conn", "Connector_Generic:Conn_01x01", "")],
            nets=[],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertIn('"Connector_Generic:Conn_01x01"', out)
        self.assertEqual(out.count('(number "1"'), 1)

    def test_fuse_stub_has_two_pins(self):
        model = SchematicModel(
            components=[Component("F1", "1A", "Device:Fuse", "")],
            nets=[],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertIn('"Device:Fuse"', out)

    def test_ferrite_bead_stub_has_two_pins(self):
        model = SchematicModel(
            components=[Component("FB1", "BLM18", "Device:Ferrite_Bead", "")],
            nets=[],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertIn('"Device:Ferrite_Bead"', out)

    # ------------------------------------------------------------------
    # Adaptive paper / grid
    # ------------------------------------------------------------------

    def test_small_design_uses_a4(self):
        model = SchematicModel(
            components=[Component(f"R{i}", "10k", "Device:R", "") for i in range(5)],
            nets=[],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertIn('(paper "A4")', out)

    def test_medium_design_uses_a3(self):
        model = SchematicModel(
            components=[Component(f"R{i}", "10k", "Device:R", "") for i in range(50)],
            nets=[],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertIn('(paper "A3")', out)

    def test_large_design_uses_a2(self):
        model = SchematicModel(
            components=[Component(f"R{i}", "10k", "Device:R", "") for i in range(100)],
            nets=[],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertIn('(paper "A2")', out)

    def test_extra_large_design_uses_a1(self):
        model = SchematicModel(
            components=[Component(f"R{i}", "10k", "Device:R", "") for i in range(200)],
            nets=[],
            pages=1,
        )
        out = render_kicad_schematic(model)
        self.assertIn('(paper "A1")', out)

    # ------------------------------------------------------------------
    # .kicad_sym library reader
    # ------------------------------------------------------------------

    def test_load_kicad_sym_file_parses_symbols(self):
        """_load_kicad_sym_file must return a dict keyed by symbol name."""
        import tempfile, os
        _load_kicad_sym_file = _writer._load_kicad_sym_file
        content = """\
(kicad_symbol_lib
  (version 20241209)
  (generator "test")
  (symbol "MyPart"
    (in_bom yes)
    (on_board yes)
    (symbol "MyPart_1_1"
      (pin passive line (at 0 0 0) (length 2.54)
        (name "A" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27))))
      )
    )
  )
  (symbol "OtherPart"
    (in_bom no)
    (on_board yes)
  )
)
"""
        with tempfile.NamedTemporaryFile(
            suffix=".kicad_sym", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            fname = f.name
        try:
            result = _load_kicad_sym_file(fname)
            self.assertIn("MyPart", result)
            self.assertIn("OtherPart", result)
            self.assertIn('(number "1"', result["MyPart"])
        finally:
            os.unlink(fname)

    def test_find_symbol_in_libs_returns_prefixed_definition(self):
        """_find_symbol_in_libs must prefix the outer symbol name."""
        import tempfile, os
        _find_symbol_in_libs = _writer._find_symbol_in_libs
        content = """\
(kicad_symbol_lib
  (version 20241209)
  (generator "test")
  (symbol "WidgetA"
    (in_bom yes)
    (on_board yes)
    (symbol "WidgetA_1_1"
      (pin passive line (at 0 0 0) (length 2.54)
        (name "~" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27))))
      )
    )
  )
)
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sym_file = os.path.join(tmpdir, "VendorLib.kicad_sym")
            with open(sym_file, "w", encoding="utf-8") as f:
                f.write(content)
            result = _find_symbol_in_libs("VendorLib:WidgetA", [tmpdir])
        self.assertIsNotNone(result)
        # Outer name must be prefixed
        self.assertIn('(symbol "VendorLib:WidgetA"', result)
        # Inner sub-symbol name must NOT be prefixed
        self.assertIn('"WidgetA_1_1"', result)

    def test_find_symbol_in_libs_missing_lib_returns_none(self):
        _find_symbol_in_libs = _writer._find_symbol_in_libs
        result = _find_symbol_in_libs("NonExistent:Part", ["/tmp"])
        self.assertIsNone(result)

    def test_sym_lib_paths_used_for_unknown_symbols(self):
        """Symbols found via sym_lib_paths are embedded instead of generic box."""
        import tempfile, os
        content = """\
(kicad_symbol_lib
  (version 20241209)
  (generator "test")
  (symbol "MySensor"
    (in_bom yes)
    (on_board yes)
    (symbol "MySensor_1_1"
      (pin passive line (at 0 0 0) (length 2.54)
        (name "OUT" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27))))
      )
    )
  )
)
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sym_file = os.path.join(tmpdir, "SensorLib.kicad_sym")
            with open(sym_file, "w", encoding="utf-8") as f:
                f.write(content)
            model = SchematicModel(
                components=[Component("U5", "MySensor", "SensorLib:MySensor", "")],
                nets=[],
                pages=1,
            )
            out = render_kicad_schematic(model, sym_lib_paths=[tmpdir])
        self.assertIn('(symbol "SensorLib:MySensor"', out)
        # Inner sub-symbol name must be present unchanged
        self.assertIn('"MySensor_1_1"', out)

    # ------------------------------------------------------------------
    # title_block pass-through
    # ------------------------------------------------------------------

    def test_title_block_emitted_when_present(self):
        model = SchematicModel(
            components=[],
            nets=[],
            pages=1,
        )
        model.title_block = {"title": "My Design", "company": "ACME"}
        out = render_kicad_schematic(model)
        self.assertIn("(title_block", out)
        self.assertIn('(title "My Design")', out)
        self.assertIn('(company "ACME")', out)
