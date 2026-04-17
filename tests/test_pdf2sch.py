import unittest

from pdf2sch import (
    DetectionOutput,
    DetectedSymbol,
    DetectedWire,
    PDF2SchPipeline,
    PipelineConfig,
    SchematicModel,
)


class TestPDF2SchPipeline(unittest.TestCase):
    def test_filters_sheet_border_text(self):
        pipeline = PDF2SchPipeline(
            detector=lambda _: DetectionOutput(
                symbols=[],
                wires=[],
                text_items=["Sheet 1 of 2", "REV A", "Signal Out"],
            )
        )

        detection = pipeline.detect("ignored.pdf")

        self.assertEqual(detection.text_items, ["Signal Out"])

    def test_review_marks_rejected_uncertain_nets(self):
        pipeline = PDF2SchPipeline(
            detector=lambda _: DetectionOutput(
                symbols=[DetectedSymbol("R1", "10k")],
                wires=[DetectedWire("SIG", ["R1.1", "R1.2"], confidence=0.6)],
                text_items=[],
            )
        )

        model = pipeline.build_model(pipeline.detect("a.pdf"))
        reviewed = pipeline.review_model(model, input_fn=lambda _: "n")

        self.assertEqual(reviewed.nets[0].name, "REVIEW_REQUIRED_SIG")

    def test_review_targets_correct_net_when_only_some_are_uncertain(self):
        pipeline = PDF2SchPipeline(
            detector=lambda _: DetectionOutput(
                symbols=[DetectedSymbol("R1", "10k")],
                wires=[
                    DetectedWire("HIGH_CONF", ["R1.1"], confidence=0.95),
                    DetectedWire("LOW_CONF", ["R1.2"], confidence=0.5),
                ],
                text_items=[],
            )
        )

        model = pipeline.build_model(pipeline.detect("a.pdf"))
        reviewed = pipeline.review_model(model, input_fn=lambda _: "n")

        self.assertEqual(reviewed.nets[0].name, "HIGH_CONF")
        self.assertEqual(reviewed.nets[1].name, "REVIEW_REQUIRED_LOW_CONF")

    def test_generates_kicad_content_with_pages_and_hierarchy(self):
        pipeline = PDF2SchPipeline(
            detector=lambda _: DetectionOutput(
                symbols=[DetectedSymbol("U1", "ADuCM350", "QFN-56")],
                wires=[DetectedWire("VDD", ["U1.1"])],
                text_items=[],
                pages=3,
                hierarchical_blocks=["Power"],
            )
        )

        output = pipeline.convert("a.pdf", input_fn=lambda _: "y")

        self.assertIn("(pages 3)", output)
        self.assertIn("(sheet (name \"Power\"))", output)
        self.assertIn("(ref U1)", output)
        self.assertIn("(net (name \"VDD\")", output)

    def test_uconfig_style_overrides_are_applied(self):
        pipeline = PDF2SchPipeline(
            detector=lambda _: DetectionOutput(
                symbols=[DetectedSymbol("X1", "AD8606")],
                wires=[DetectedWire("SIG", ["X1.1"], confidence=0.6)],
                text_items=[],
            ),
            config=PipelineConfig(
                low_confidence_threshold=0.9,
                review_required_prefix="CHECK_",
                value_symbol_prefix_rules=(("AD", "Custom:ADI"),),
            ),
        )

        model = pipeline.build_model(pipeline.detect("a.pdf"))
        reviewed = pipeline.review_model(model, input_fn=lambda _: "n")

        self.assertEqual(reviewed.components[0].symbol, "Custom:ADI")
        self.assertEqual(reviewed.nets[0].name, "CHECK_SIG")

    def test_reference_designator_improves_symbol_mapping(self):
        pipeline = PDF2SchPipeline(
            detector=lambda _: DetectionOutput(
                symbols=[DetectedSymbol("L1", "10u")],
                wires=[],
                text_items=[],
            )
        )

        model = pipeline.build_model(pipeline.detect("a.pdf"))

        self.assertEqual(model.components[0].symbol, "Device:L")

    def test_missing_footprint_hint_falls_back_to_empty(self):
        """Footprint field must be empty – footprint assignment is out of scope."""
        pipeline = PDF2SchPipeline(
            detector=lambda _: DetectionOutput(
                symbols=[DetectedSymbol("R1", "10k")],
                wires=[],
                text_items=[],
            )
        )

        model = pipeline.build_model(pipeline.detect("a.pdf"))

        self.assertEqual(model.components[0].footprint, "")

    def test_review_model_raises_on_mismatched_review_metadata(self):
        pipeline = PDF2SchPipeline()
        model = SchematicModel(
            components=[],
            nets=[],
            pages=1,
            review_questions=["q1"],
            review_net_indices=[],
        )

        with self.assertRaises(ValueError):
            pipeline.review_model(model, input_fn=lambda _: "y")


if __name__ == "__main__":
    unittest.main()
