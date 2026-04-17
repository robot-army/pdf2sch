from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable


@dataclass
class PipelineConfig:
    border_text_markers: tuple[str, ...] = (
        "sheet",
        "rev",
        "title",
        "page",
        "size",
        "drawn by",
    )
    low_confidence_threshold: float = 0.8
    review_required_prefix: str = "REVIEW_REQUIRED_"
    review_question_template: str = (
        "Net '{net_name}' has low confidence ({confidence:.2f}). Keep detected nodes {nodes}? (y/n)"
    )
    value_symbol_prefix_rules: tuple[tuple[str, str], ...] = (
        ("AD", "Amplifier_Operational:ADI_Generic"),
        ("LM", "Device:U"),
        ("TL", "Device:U"),
        ("AT", "Device:U"),
    )


@dataclass
class DetectedSymbol:
    ref: str
    value: str
    footprint_hint: str | None = None


@dataclass
class DetectedWire:
    net_name: str
    nodes: list[str]
    confidence: float = 1.0


@dataclass
class DetectionOutput:
    symbols: list[DetectedSymbol]
    wires: list[DetectedWire]
    text_items: list[str]
    pages: int = 1
    hierarchical_blocks: list[str] = field(default_factory=list)


@dataclass
class Component:
    ref: str
    value: str
    symbol: str
    footprint: str


@dataclass
class Net:
    name: str
    nodes: list[str]


@dataclass
class SchematicModel:
    components: list[Component]
    nets: list[Net]
    pages: int
    hierarchical_blocks: list[str] = field(default_factory=list)
    review_questions: list[str] = field(default_factory=list)
    review_net_indices: list[int] = field(default_factory=list)


class PDF2SchPipeline:
    """Minimal pipeline scaffold: detect -> structure -> map -> review -> KiCad text."""

    def __init__(
        self,
        detector: Callable[[str], DetectionOutput] | None = None,
        config: PipelineConfig | None = None,
    ) -> None:
        self.detector = detector or self._default_detector
        self.config = config or PipelineConfig()

    def _default_detector(self, pdf_source: str) -> DetectionOutput:
        # Delegate to the real pymupdf-based detector for PDF files.
        try:
            from pdf_detector import detect as _pdf_detect  # type: ignore[import]
            return _pdf_detect(pdf_source)
        except ImportError:
            pass
        # Fallback: empty output when pymupdf is not installed.
        return DetectionOutput(symbols=[], wires=[], text_items=[], pages=1)

    def detect(self, pdf_source: str) -> DetectionOutput:
        result = self.detector(pdf_source)
        result.text_items = self._filter_border_text(result.text_items)
        return result

    def _filter_border_text(self, text_items: Iterable[str]) -> list[str]:
        filtered: list[str] = []
        for item in text_items:
            lowered = item.strip().lower()
            if any(marker in lowered for marker in self.config.border_text_markers):
                continue
            filtered.append(item)
        return filtered

    def build_model(self, detection: DetectionOutput) -> SchematicModel:
        components = [
            Component(
                ref=s.ref,
                value=s.value,
                symbol=self._guess_symbol(s.ref, s.value),
                footprint="",  # footprint assignment out of scope for PDF import
            )
            for s in detection.symbols
        ]
        nets = [Net(name=w.net_name, nodes=w.nodes[:]) for w in detection.wires]
        review_questions: list[str] = []
        review_net_indices: list[int] = []
        for net_idx, w in enumerate(detection.wires):
            if w.confidence < self.config.low_confidence_threshold:
                review_questions.append(
                    self.config.review_question_template.format(
                        net_name=w.net_name, confidence=w.confidence, nodes=w.nodes
                    )
                )
                review_net_indices.append(net_idx)
        return SchematicModel(
            components=components,
            nets=nets,
            pages=detection.pages,
            hierarchical_blocks=detection.hierarchical_blocks,
            review_questions=review_questions,
            review_net_indices=review_net_indices,
        )

    def _guess_symbol(self, ref: str, value: str) -> str:
        ref_upper = ref.upper()
        if ref_upper.startswith("R"):
            return "Device:R"
        if ref_upper.startswith("C"):
            return "Device:C"
        if ref_upper.startswith("L"):
            return "Device:L"
        if ref_upper.startswith("U"):
            return "Device:U"
        upper = value.upper()
        for prefix, symbol in self.config.value_symbol_prefix_rules:
            if upper.startswith(prefix.upper()):
                return symbol
        if upper.endswith("K") or upper.endswith("M"):
            return "Device:R"
        if upper.endswith("N") or upper.endswith("U"):
            return "Device:C"
        return "Device:Unknown"

    def review_model(
        self,
        model: SchematicModel,
        input_fn: Callable[[str], str] = input,
    ) -> SchematicModel:
        # Netlist accuracy is prioritized: uncertain nets require explicit confirmation.
        if len(model.review_questions) != len(model.review_net_indices):
            raise ValueError("review_questions and review_net_indices must have equal length")
        for question, net_idx in zip(model.review_questions, model.review_net_indices):
            answer = input_fn(question + " ").strip().lower()
            if answer in {"n", "no"}:
                model.nets[net_idx].name = f"{self.config.review_required_prefix}{model.nets[net_idx].name}"
        return model

    def generate_kicad_schematic(self, model: SchematicModel) -> str:
        lines = ["(kicad_sch (version 20231120) (generator pdf2sch))"]
        lines.append(f"  (pages {model.pages})")
        for block in model.hierarchical_blocks:
            lines.append(f"  (sheet (name \"{block}\"))")
        for c in model.components:
            lines.append(
                "  "
                + f"(symbol (ref {c.ref}) (value \"{c.value}\") (lib_id \"{c.symbol}\") (footprint \"{c.footprint}\"))"
            )
        for n in model.nets:
            nodes = " ".join(f"\"{node}\"" for node in n.nodes)
            lines.append(f"  (net (name \"{n.name}\") (nodes {nodes}))")
        lines.append(")")
        return "\n".join(lines) + "\n"

    def convert(
        self,
        pdf_source: str,
        input_fn: Callable[[str], str] = input,
    ) -> str:
        detection = self.detect(pdf_source)
        model = self.build_model(detection)
        reviewed = self.review_model(model, input_fn=input_fn)
        return self.generate_kicad_schematic(reviewed)


def convert_pdf_to_kicad(
    pdf_source: str,
    input_fn: Callable[[str], str] = input,
) -> str:
    return PDF2SchPipeline().convert(pdf_source=pdf_source, input_fn=input_fn)


if __name__ == "__main__":
    source = input("PDF path or URL: ").strip()
    sch = convert_pdf_to_kicad(source)
    print("\nGenerated KiCad schematic:\n")
    print(sch)
