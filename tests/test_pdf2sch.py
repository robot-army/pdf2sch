import unittest

from pdf2sch import DetectionOutput, DetectedSymbol, DetectedWire, PDF2SchPipeline


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


if __name__ == "__main__":
    unittest.main()
