"""
Tests for pdf_detector.py using the real stickhub-pdf2sch test data.

Ground truth is derived from test-data/stickhub-pdf2sch/stickhub-pdf2sch.kicad_sch.
Tests are skipped when pymupdf is not installed or the test-data is absent.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
_STICKHUB_PDF = os.path.join(
    _REPO_ROOT, "test-data", "stickhub-pdf2sch", "stickhub-pdf2sch.pdf"
)
_STICKHUB_SCH = os.path.join(
    _REPO_ROOT, "test-data", "stickhub-pdf2sch", "stickhub-pdf2sch.kicad_sch"
)

_pymupdf_available = False
try:
    import fitz  # type: ignore[import]
    _pymupdf_available = True
except ImportError:
    pass

_test_data_available = os.path.isfile(_STICKHUB_PDF) and os.path.isfile(_STICKHUB_SCH)

_skip_reason = (
    "pymupdf not installed" if not _pymupdf_available else
    "stickhub test-data not found"
)
needs_stickhub = pytest.mark.skipif(
    not (_pymupdf_available and _test_data_available),
    reason=_skip_reason,
)

# ──────────────────────────────────────────────────────────────────────────────
# Ground-truth helpers (parse the reference .kicad_sch)
# ──────────────────────────────────────────────────────────────────────────────

_COMP_REF_PAT = re.compile(r'^\s*\(property "Reference" "([^"#][^"]*)"', re.MULTILINE)


def _ground_truth_refs() -> set[str]:
    """Return all non-power, non-logo component refs from the reference schematic."""
    with open(_STICKHUB_SCH, encoding="utf-8") as f:
        text = f.read()
    all_refs = set(_COMP_REF_PAT.findall(text))
    # Keep only numbered refs (C1, R1, U1 etc.) – exclude bare letters, LOGO, #xxx
    return {
        r for r in all_refs
        if re.match(r"^[A-Z]{1,3}\d+$", r)
        and not r.startswith("LOGO")
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

@needs_stickhub
def test_detect_returns_detection_output():
    from pdf_detector import detect
    result = detect(_STICKHUB_PDF)
    # Basic structural checks
    assert result.pages == 1
    assert len(result.symbols) > 0
    assert isinstance(result.wires, list)
    assert isinstance(result.text_items, list)


@needs_stickhub
def test_component_count_plausible():
    """Should find at least 80 component references (actual ground truth ≈ 90)."""
    from pdf_detector import detect
    result = detect(_STICKHUB_PDF)
    assert len(result.symbols) >= 80, (
        f"Expected ≥80 components, got {len(result.symbols)}"
    )


@needs_stickhub
def test_known_refs_present():
    """Specific references known to exist in the schematic must be detected."""
    from pdf_detector import detect
    result = detect(_STICKHUB_PDF)
    detected_refs = {s.ref for s in result.symbols}

    must_have = {"C1", "R1", "U1", "U2", "Y1", "J1", "D1", "JP1", "H1"}
    missing = must_have - detected_refs
    assert not missing, f"Missing expected refs: {missing}"


@needs_stickhub
def test_known_values():
    """Key ref→value pairings that can be verified from the reference schematic."""
    from pdf_detector import detect
    result = detect(_STICKHUB_PDF)
    by_ref = {s.ref: s.value for s in result.symbols}

    # R8 value is "470" (a single-word inline value at the same y as the ref)
    assert "R8" in by_ref, "R8 not detected"
    assert "470" in by_ref["R8"], f"R8 value mismatch: {by_ref['R8']!r}"

    # C34 value is "22uF 10V" (two PDF words on the row below the ref)
    assert "C34" in by_ref, "C34 not detected"
    assert "22uF" in by_ref["C34"], f"C34 value missing '22uF': {by_ref['C34']!r}"


@needs_stickhub
def test_recall_against_ground_truth():
    """At least 85 % of the ground-truth numbered refs should be detected."""
    from pdf_detector import detect
    result = detect(_STICKHUB_PDF)
    detected_refs = {s.ref for s in result.symbols}
    truth = _ground_truth_refs()

    found = truth & detected_refs
    recall = len(found) / len(truth)
    missing = truth - detected_refs

    assert recall >= 0.85, (
        f"Recall {recall:.1%} < 85 %.\n"
        f"Ground truth: {len(truth)}, detected: {len(detected_refs)}, "
        f"matched: {len(found)}.\n"
        f"Missing: {sorted(missing)}"
    )


@needs_stickhub
def test_net_labels_include_power():
    """GND and +5V should be in text_items (both appear in the stickhub schematic)."""
    from pdf_detector import detect
    result = detect(_STICKHUB_PDF)
    text_set = set(result.text_items)
    assert "GND" in text_set, f"GND not in text_items: {text_set}"
    assert "+5V" in text_set, f"+5V not in text_items: {text_set}"


@needs_stickhub
def test_net_labels_include_signals():
    """Signal net labels present in the exported PDF must be found."""
    from pdf_detector import detect
    result = detect(_STICKHUB_PDF)
    text_set = set(result.text_items)
    # USB D+/D- host-side labels – both exist in the stickhub PDF
    missing = {"D+", "D-"} - text_set
    assert not missing, f"Signal net labels missing: {missing}\nFound: {sorted(text_set)}"


@needs_stickhub
def test_no_border_text_in_output():
    """Title-block keywords must not appear as components or net labels."""
    from pdf_detector import detect
    result = detect(_STICKHUB_PDF)
    detected_refs = {s.ref for s in result.symbols}
    all_text = set(result.text_items) | detected_refs

    forbidden_fragments = {"Sheet", "Rev", "KiCad", "File", "Title"}
    leaks = {t for t in all_text if any(f.lower() in t.lower() for f in forbidden_fragments)}
    assert not leaks, f"Border/title text leaked into output: {leaks}"


@needs_stickhub
def test_no_duplicate_refs():
    """Each reference designator should appear at most once."""
    from pdf_detector import detect
    result = detect(_STICKHUB_PDF)
    refs = [s.ref for s in result.symbols]
    from collections import Counter
    dupes = {r: n for r, n in Counter(refs).items() if n > 1}
    assert not dupes, f"Duplicate refs detected: {dupes}"


@needs_stickhub
def test_gnd_net_has_component_nodes():
    """The GND net should list at least a few components."""
    from pdf_detector import detect
    result = detect(_STICKHUB_PDF)
    gnd_wires = [w for w in result.wires if w.net_name == "GND"]
    assert gnd_wires, "No GND wire found"
    total_nodes = sum(len(w.nodes) for w in gnd_wires)
    assert total_nodes >= 5, f"GND net has only {total_nodes} nodes, expected ≥5"


@needs_stickhub
def test_pipeline_integration():
    """Full pipeline: detect → build_model → generate_kicad_schematic."""
    import sys
    sys.path.insert(0, _REPO_ROOT)
    from pdf2sch import PDF2SchPipeline
    from pdf_detector import PDFDetector

    pipeline = PDF2SchPipeline(detector=PDFDetector())
    detection = pipeline.detect(_STICKHUB_PDF)
    model = pipeline.build_model(detection)

    assert len(model.components) >= 80
    # No footprint should be set (user requirement: no footprints)
    for comp in model.components:
        assert comp.footprint == "", (
            f"Unexpected footprint on {comp.ref}: {comp.footprint!r}"
        )

    sch_text = pipeline.generate_kicad_schematic(model)
    assert "(kicad_sch" in sch_text
    assert "C1" in sch_text or "R1" in sch_text  # at least one component rendered


@needs_stickhub
def test_writer_produces_valid_kicad_sch():
    """writer.py must produce a parseable KiCad 9 schematic from stickhub."""
    import sys
    sys.path.insert(0, _REPO_ROOT)
    sys.path.insert(0, os.path.join(_REPO_ROOT, "kicad_plugin", "plugins"))
    from pdf2sch import PDF2SchPipeline
    from pdf_detector import PDFDetector

    try:
        from pdf2sch.writer import write_kicad_schematic
    except ModuleNotFoundError:
        pytest.skip("kicad_plugin writer not importable in this env")

    import tempfile
    pipeline = PDF2SchPipeline(detector=PDFDetector())
    detection = pipeline.detect(_STICKHUB_PDF)
    model = pipeline.build_model(detection)

    with tempfile.NamedTemporaryFile(suffix=".kicad_sch", delete=False) as f:
        tmp = f.name

    try:
        write_kicad_schematic(model, tmp)
        with open(tmp, encoding="utf-8") as f:
            content = f.read()
        assert "(kicad_sch" in content
        assert "(version" in content
        # No footprint property should contain "Unknown"
        assert '"Unknown"' not in content
    finally:
        os.unlink(tmp)
