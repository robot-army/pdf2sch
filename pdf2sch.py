from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

# PDF points to mm: 1 pt = 1/72 inch = 25.4/72 mm
_PTS_TO_MM: float = 25.4 / 72.0

# KiCad schematic grid: 50 mil = 1.27 mm
_GRID_MM: float = 1.27


def _snap_mm(v: float) -> float:
    """Round *v* (mm) to the nearest KiCad 50-mil grid point."""
    return round(v / _GRID_MM) * _GRID_MM


# Symbols whose default pin axis is **vertical** (pins at ±y from centre).
# All others are assumed horizontal (pins at ±x from centre).
_VERT_PIN_SYMBOLS: frozenset[str] = frozenset({
    "Device:R",
    "Device:C",
    "Device:L",
    "Device:Ferrite_Bead",
    "Device:Fuse",
    "Device:Crystal",
})


def _comp_angle(lib_id: str, pin_axis: str) -> float:
    """Return the KiCad CCW rotation angle (0 or 90) for a component.

    *pin_axis* is ``"H"`` when the detected wires connect left/right to the
    component (horizontal wire axis) and ``"V"`` when they connect top/bottom.
    The returned angle makes the symbol's default pin axis line up with the
    wire axis.
    """
    sym_vert = lib_id in _VERT_PIN_SYMBOLS   # True → default pins at ±y
    wire_horiz = pin_axis == "H"              # True → wires run left/right
    # Mismatch → need 90° CCW rotation so pins align with the wire direction.
    return 90.0 if sym_vert == wire_horiz else 0.0


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
    # PDF-space position of the component centre (points at 72 dpi).
    # 0.0 means unknown / not detected.
    x_pts: float = 0.0
    y_pts: float = 0.0
    # Inferred pin axis: "H" = horizontal pins (LED/D style),
    # "V" = vertical pins (R/C/L style), "" = unknown.
    pin_axis: str = ""


@dataclass
class DetectedWire:
    net_name: str
    nodes: list[str]
    confidence: float = 1.0
    # Wire-endpoint (PDF points) where a net label should be placed.
    # 0.0/0.0 means unknown; use name-only global label fallback.
    label_x_pts: float = 0.0
    label_y_pts: float = 0.0
    # Rotation angle (degrees, CCW) for the net label.
    label_angle: int = 0


@dataclass
class DetectionOutput:
    symbols: list[DetectedSymbol]
    wires: list[DetectedWire]
    text_items: list[str]
    pages: int = 1
    hierarchical_blocks: list[str] = field(default_factory=list)
    # Wire geometry in mm (x0, y0, x1, y1) — emitted as KiCad wire elements.
    wire_segments: list[tuple[float, float, float, float]] = field(default_factory=list)


@dataclass
class Component:
    ref: str
    value: str
    symbol: str
    footprint: str
    # Schematic placement coordinates in mm.  0/0 falls back to grid placement.
    x_mm: float = 0.0
    y_mm: float = 0.0
    # KiCad rotation angle in degrees (CCW).
    angle: float = 0.0


@dataclass
class Net:
    name: str
    nodes: list[str]
    # Where to place the net label in the schematic (mm).  0/0 = use fallback.
    label_x_mm: float = 0.0
    label_y_mm: float = 0.0
    # KiCad rotation angle (degrees, CCW) for the label element.
    label_angle: int = 0


@dataclass
class SchematicModel:
    components: list[Component]
    nets: list[Net]
    pages: int
    hierarchical_blocks: list[str] = field(default_factory=list)
    review_questions: list[str] = field(default_factory=list)
    review_net_indices: list[int] = field(default_factory=list)
    # Wire geometry from the PDF (mm) — emitted verbatim as KiCad wire elements.
    wire_segments: list[tuple[float, float, float, float]] = field(default_factory=list)


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
        # Deduplicate refs: a multi-page PDF often shows the same component
        # reference on every page it is connected to.  Keep the first occurrence
        # but upgrade its value if a later occurrence has a longer (more
        # informative) value string.
        deduped: dict[str, "DetectedSymbol"] = {}
        for sym in detection.symbols:
            if sym.ref not in deduped:
                deduped[sym.ref] = sym
            else:
                prev = deduped[sym.ref]
                if len(sym.value.strip()) > len(prev.value.strip()):
                    # Replace but keep insertion order by updating in-place.
                    deduped[sym.ref] = sym
        components = [
            self._make_component(s)
            for s in deduped.values()
        ]
        nets = [
            Net(
                name=w.net_name,
                nodes=w.nodes[:],
                label_x_mm=w.label_x_pts * _PTS_TO_MM,
                label_y_mm=w.label_y_pts * _PTS_TO_MM,
                label_angle=w.label_angle,
            )
            for w in detection.wires
        ]
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
            wire_segments=list(detection.wire_segments),
        )

    def _make_component(self, sym: "DetectedSymbol") -> "Component":
        """Construct a Component, computing position and rotation from detection data."""
        lib_id = self._guess_symbol(sym.ref, sym.value)
        x_mm = _snap_mm(sym.x_pts * _PTS_TO_MM) if sym.x_pts else 0.0
        y_mm = _snap_mm(sym.y_pts * _PTS_TO_MM) if sym.y_pts else 0.0
        angle = _comp_angle(lib_id, sym.pin_axis) if sym.pin_axis else 0.0
        return Component(
            ref=sym.ref,
            value=sym.value,
            symbol=lib_id,
            footprint="",
            x_mm=x_mm,
            y_mm=y_mm,
            angle=angle,
        )


    def _guess_symbol(self, ref: str, value: str) -> str:
        import re as _re
        # Extract the alphabetic prefix (strip trailing digits, e.g. "R12" → "R").
        m = _re.match(r'^([A-Za-z]+)', ref)
        pfx = m.group(1).upper() if m else ref.upper()
        val_upper = value.upper()

        # Passives
        if pfx in {"R", "RN", "RP", "VR"}:
            return "Device:R"
        if pfx in {"C", "CP", "CAP"}:
            return "Device:C"
        if pfx in {"L", "FL"}:
            return "Device:L"
        if pfx in {"FB"}:
            return "Device:Ferrite_Bead"
        if pfx in {"F", "FU"}:
            return "Device:Fuse"

        # Semiconductors
        if pfx in {"D", "DS", "DZ", "VD", "CR"}:
            if "LED" in val_upper:
                return "Device:LED"
            return "Device:D"
        if pfx in {"Q", "T", "TR"}:
            if "PNP" in val_upper:
                return "Device:Q_PNP"
            return "Device:Q_NPN"
        if pfx in {"U", "IC", "A"}:
            return "Device:U"

        # Connectors / headers
        if pfx in {"J", "JP", "P", "CN", "H", "E"}:
            return "Connector_Generic:Conn_01x01"

        # Crystals / oscillators
        if pfx in {"Y", "XTAL"}:
            return "Device:Crystal"

        # Electromechanical
        if pfx in {"K", "RLY"}:
            return "Device:Relay_SPDT"
        if pfx in {"SW", "S", "PB", "BTN"}:
            return "Switch:SW_Push"
        if pfx in {"M", "MOT"}:
            return "Device:Motor"

        # Miscellaneous
        if pfx in {"TP"}:
            return "Device:TestPoint"
        if pfx in {"BT", "BAT", "G"}:
            return "Device:Battery_Cell"
        if pfx in {"MH"}:
            return "MountingHole:MountingHole"

        # Value-based fallbacks (when ref prefix is unrecognised)
        for vprefix, symbol in self.config.value_symbol_prefix_rules:
            if val_upper.startswith(vprefix.upper()):
                return symbol
        if val_upper.endswith("K") or val_upper.endswith("M"):
            return "Device:R"
        if val_upper.endswith("N") or val_upper.endswith("U"):
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
