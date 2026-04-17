"""
PDF schematic detector using pymupdf (fitz).

Optimised for KiCAD 9-exported PDFs (test case: stickhub).  KiCAD renders
each word of a property string as a separate text span and duplicates every
span; both quirks are handled explicitly.

Public surface:
    detect(pdf_path: str) -> DetectionOutput
    PDFDetector()           callable wrapper for use as pipeline.detector
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterator

try:
    import fitz  # type: ignore[import]   # pymupdf
    _FITZ_AVAILABLE = True
except ImportError:  # pragma: no cover
    _FITZ_AVAILABLE = False

from pdf2sch import DetectedSymbol, DetectedWire, DetectionOutput

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

# Known component-reference prefixes (single or double letter)
_COMP_PREFIXES: frozenset[str] = frozenset({
    "C", "R", "L", "D", "U", "J", "Q", "Y", "X", "H", "S", "T", "F", "K",
    "M", "P", "E", "V", "BT",
    "JP", "SW", "FB", "TP", "VR", "CR", "DS",
})

_REF_RE = re.compile(r"^([A-Z]{1,3})(\d+)$")

# Text in these sets is always treated as a net / power label, never as a
# component reference or value.
_POWER_NAMES: frozenset[str] = frozenset({
    "GND", "AGND", "DGND", "PGND", "EARTH",
    "VCC", "VDD", "VSS", "VIN", "VOUT", "PWR",
})

# Wire stroke width accepted as schematic wires (PDF points)
_WIRE_WIDTH_MIN = 0.35
_WIRE_WIDTH_MAX = 0.55

# Endpoint snap grid for union-find (PDF points)
_SNAP_PT = 1.0

# Greedy value-assignment search radius (PDF points, ≈ 14 mm at A3)

# Radius to match a net label to a wire endpoint
_MAX_LABEL_DIST_PT = 15.0

# Radius to match a component ref to a wire endpoint
_MAX_COMP_DIST_PT = 28.0

# Title-block is the bottom 8 % and border is the outer 4 % of each page
_TITLE_FRAC = 0.92
_BORDER_FRAC = 0.04

# Title-block keyword fragments (lower-case)
_TITLE_KEYS: frozenset[str] = frozenset({
    "sheet", "rev", "title", "size", "date", "drawn", "file", "company",
    "project", "kicad", "e.d.a.", "eeschema", "altium", "pads",
    "checked", "released", "scale", "schematic",
})


# ──────────────────────────────────────────────────────────────────────────────
# Internal data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class _Span:
    text: str
    x: float
    y: float
    size: float


@dataclass
class _Component:
    """Detected component with spatial position (internal use only)."""
    ref: str
    value: str
    x: float    # PDF points
    y: float


@dataclass
class _WireSeg:
    x0: float
    y0: float
    x1: float
    y1: float


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def detect(pdf_path: str) -> DetectionOutput:
    """Detect schematic elements from *pdf_path*."""
    if not _FITZ_AVAILABLE:
        raise ImportError(
            "pymupdf is required for PDF detection.  "
            "Install it with: pip install pymupdf"
        )

    import fitz  # noqa: PLC0415 – conditional import

    doc = fitz.open(pdf_path)

    all_components: list[_Component] = []
    all_net_label_positions: list[tuple[str, float, float]] = []
    all_wire_segs: list[tuple[_WireSeg, int]] = []  # (seg, page_idx)

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pw, ph = page.rect.width, page.rect.height

        spans = _dedup(_extract_spans(page))
        spans = _filter_border(spans, pw, ph)

        comps, net_labels = _detect_components(spans)
        all_components.extend(comps)
        all_net_label_positions.extend(net_labels)

        for seg in _extract_wire_segs(page, pw, ph):
            all_wire_segs.append((seg, page_idx))

    symbols = [DetectedSymbol(ref=c.ref, value=c.value) for c in all_components]

    wires = _build_connectivity(
        all_components,
        all_wire_segs,
        all_net_label_positions,
    )

    return DetectionOutput(
        symbols=symbols,
        wires=wires,
        text_items=sorted({name for name, *_ in all_net_label_positions}),
        pages=len(doc),
    )


class PDFDetector:
    """Callable wrapper; use as ``PDF2SchPipeline(detector=PDFDetector())``."""

    def __call__(self, source: str) -> DetectionOutput:
        return detect(source)


# ──────────────────────────────────────────────────────────────────────────────
# Text extraction
# ──────────────────────────────────────────────────────────────────────────────

def _extract_spans(page) -> list[_Span]:
    spans: list[_Span] = []
    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type") != 0:
            continue
        for line in blk.get("lines", []):
            for sp in line.get("spans", []):
                t = sp["text"].strip()
                if t:
                    spans.append(_Span(
                        text=t,
                        x=sp["origin"][0],
                        y=sp["origin"][1],
                        size=round(sp["size"], 1),
                    ))
    return spans


def _dedup(spans: list[_Span]) -> list[_Span]:
    """Remove spans duplicated at the same position (KiCad renders each twice)."""
    seen: set[tuple] = set()
    result: list[_Span] = []
    for s in spans:
        key = (s.text, round(s.x), round(s.y))
        if key not in seen:
            seen.add(key)
            result.append(s)
    return result


def _filter_border(spans: list[_Span], pw: float, ph: float) -> list[_Span]:
    """Remove title-block and sheet-border text."""
    result: list[_Span] = []
    title_y = ph * _TITLE_FRAC
    left_x = pw * _BORDER_FRAC
    right_x = pw * (1 - _BORDER_FRAC)
    top_y = ph * _BORDER_FRAC

    for s in spans:
        if s.y > title_y:
            continue
        if s.x < left_x or s.x > right_x:
            continue
        if s.y < top_y:
            continue
        if s.text.strip().lower() in _TITLE_KEYS:
            continue
        result.append(s)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Component detection
# ──────────────────────────────────────────────────────────────────────────────

def _detect_components(
    spans: list[_Span],
) -> tuple[list[_Component], list[tuple[str, float, float]]]:
    """
    Return (components, net_label_positions).

    net_label_positions is a list of (text, x, y) for spans that look like
    net names (power symbols, signal labels).

    Value assignment uses a Voronoi-like rule:
      - Each value-candidate span is assigned to the *nearest* ref within
        FAR_DIST.  Within TIGHT_DIST the assignment is unconditional; between
        TIGHT_DIST and FAR_DIST we skip spans whose text looks like a net name,
        so that net labels near (but not owned by) a component stay available.
    """
    _TIGHT = 15.0   # pt – always treat as value
    _FAR = 40.0     # pt – never treat as value

    # Split spans: refs vs value candidates (size-filtered to exclude symbol decorations)
    ref_spans: list[_Span] = []
    value_cands: list[_Span] = []
    for s in spans:
        if _is_ref(s.text):
            ref_spans.append(s)
        elif s.size >= 2.2:
            # Exclude obvious power names early – they stay as net labels
            if _could_be_value(s.text):
                value_cands.append(s)
            else:
                # Will be picked up in net-label scan at the end
                pass

    # Voronoi: assign each value span to its nearest ref
    ref_buckets: dict[int, list[_Span]] = defaultdict(list)
    unclaimed: list[_Span] = []

    for vs in value_cands:
        best_id: int | None = None
        best_d = _FAR
        for rs in ref_spans:
            d = _dist(rs.x, rs.y, vs.x, vs.y)
            if d < best_d:
                best_d = d
                best_id = id(rs)

        if best_id is None:
            unclaimed.append(vs)
        elif best_d <= _TIGHT:
            # Close enough to be unconditionally a value
            ref_buckets[best_id].append(vs)
        elif not _is_net_name(vs.text):
            # Medium distance – only assign if it does not look like a net label
            ref_buckets[best_id].append(vs)
        else:
            unclaimed.append(vs)

    # Build Component objects: join assigned spans sorted by (y, x)
    components: list[_Component] = []
    for rs in ref_spans:
        bucket = sorted(ref_buckets.get(id(rs), []), key=lambda s: (round(s.y), s.x))
        value = " ".join(s.text for s in bucket)
        components.append(_Component(ref=rs.text, value=value, x=rs.x, y=rs.y))

    # Net labels from power names (always) + unclaimed spans that look like net names
    net_label_positions: list[tuple[str, float, float]] = []

    # Power-name spans bypassed by _could_be_value
    for s in spans:
        if not _is_ref(s.text) and s.size >= 2.2 and not _could_be_value(s.text):
            if _is_net_name(s.text):
                net_label_positions.append((s.text, s.x, s.y))

    # Unclaimed value candidates that look like net names
    for vs in unclaimed:
        if _is_net_name(vs.text):
            net_label_positions.append((vs.text, vs.x, vs.y))

    return components, net_label_positions


def _is_ref(text: str) -> bool:
    m = _REF_RE.match(text)
    if not m:
        return False
    # The full prefix must be in the known-component set.
    # Do NOT fall back to prefix[0] – that would mis-classify net names such
    # as "LED2" (→ L=inductor?) or "VCC33" (→ V=varistor?).
    return m.group(1) in _COMP_PREFIXES


def _is_net_name(text: str) -> bool:
    """Heuristic: does this text look like a schematic net name?"""
    if not text or len(text) > 20:
        return False
    # Power symbols
    if text.upper() in _POWER_NAMES:
        return True
    if text[0] in ("+", "-") and len(text) > 1:
        return True
    # Signal net: short, no spaces, not a pure number, not a component value
    if " " in text:
        return False
    if re.match(r"^\d+[\.\d]*[pnuUmMkKM]?[FfHhΩ]?$", text):
        return False  # looks like a component value (e.g. 470, 100n, 22uF)
    if re.match(r"^[A-Z][A-Z0-9_+/\-]*$", text) and len(text) <= 15:
        return True
    return False


def _could_be_value(text: str) -> bool:
    """Reject texts that are definitely net names, not component values."""
    if text.upper() in _POWER_NAMES:
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Wire extraction
# ──────────────────────────────────────────────────────────────────────────────

def _extract_wire_segs(page, pw: float, ph: float) -> list[_WireSeg]:
    """Return axis-aligned line segments that look like schematic wires."""
    title_y = ph * _TITLE_FRAC
    max_len = pw * 0.60  # longer than this → border line

    segs: list[_WireSeg] = []
    for path in page.get_drawings():
        w = path.get("width") or 0.0
        if not (_WIRE_WIDTH_MIN <= w <= _WIRE_WIDTH_MAX):
            continue

        for item in path["items"]:
            if item[0] != "l":
                continue
            p0, p1 = item[1], item[2]
            x0, y0, x1, y1 = p0.x, p0.y, p1.x, p1.y

            # Axis-aligned only (horizontal or vertical within 0.5 pt tolerance)
            is_h = abs(y0 - y1) < 0.5
            is_v = abs(x0 - x1) < 0.5
            if not (is_h or is_v):
                continue

            # Normalise direction
            if x0 > x1 or (x0 == x1 and y0 > y1):
                x0, y0, x1, y1 = x1, y1, x0, y0

            length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            if length < 2.0:
                continue
            if length > max_len:
                continue
            if y0 > title_y and y1 > title_y:
                continue

            segs.append(_WireSeg(x0=x0, y0=y0, x1=x1, y1=y1))

    return segs


# ──────────────────────────────────────────────────────────────────────────────
# Connectivity: Union-Find over wire endpoint clusters
# ──────────────────────────────────────────────────────────────────────────────

class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[tuple[int, int], tuple[int, int]] = {}

    def _root(self, x: tuple[int, int]) -> tuple[int, int]:
        self._parent.setdefault(x, x)
        if self._parent[x] != x:
            self._parent[x] = self._root(self._parent[x])
        return self._parent[x]

    def union(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        ra, rb = self._root(a), self._root(b)
        if ra != rb:
            self._parent[ra] = rb

    def groups(self) -> dict[tuple[int, int], list[tuple[float, float]]]:
        """Return root → list-of-raw-points mapping (populated by add_point)."""
        return self._groups

    def begin(self) -> None:
        self._raw: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
        self._groups: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def add_point(self, x: float, y: float) -> None:
        key = _snap(x, y)
        self._parent.setdefault(key, key)
        self._raw[key].append((x, y))

    def finalise(self) -> None:
        """Merge raw-point lists under their root keys."""
        merged: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
        for key, pts in self._raw.items():
            merged[self._root(key)].extend(pts)
        self._groups = dict(merged)


def _snap(x: float, y: float) -> tuple[int, int]:
    return (round(x / _SNAP_PT), round(y / _SNAP_PT))


def _build_connectivity(
    components: list[_Component],
    wire_segs: list[tuple[_WireSeg, int]],
    net_label_positions: list[tuple[str, float, float]],
) -> list[DetectedWire]:
    """
    Phase A – power nets: same power-name text at multiple positions → one net.
    Phase B – signal nets: wire-connected cluster with a nearby net label.
    """
    wires: list[DetectedWire] = []

    # ── Phase A: power nets ────────────────────────────────────────────────────
    power_by_name: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for name, x, y in net_label_positions:
        if name.upper() in _POWER_NAMES or (len(name) > 1 and name[0] in ("+", "-")):
            power_by_name[name].append((x, y))

    comp_positions = [(c.ref, c.x, c.y) for c in components]

    for net_name, positions in power_by_name.items():
        nodes: list[str] = []
        for ref, rx, ry in comp_positions:
            for px, py in positions:
                if _dist(rx, ry, px, py) < _MAX_COMP_DIST_PT:
                    nodes.append(ref)
                    break
        if nodes:
            wires.append(DetectedWire(net_name=net_name, nodes=sorted(set(nodes)), confidence=0.95))

    # ── Phase B: signal nets via wire topology ─────────────────────────────────
    if not wire_segs:
        return wires

    uf = _UnionFind()
    uf.begin()

    for seg, _ in wire_segs:
        uf.add_point(seg.x0, seg.y0)
        uf.add_point(seg.x1, seg.y1)
        uf.union(_snap(seg.x0, seg.y0), _snap(seg.x1, seg.y1))

    uf.finalise()

    # Signal net labels: anything not already used as a power label
    power_names_lc = {n.lower() for n in power_by_name}
    signal_labels = [
        (name, x, y)
        for name, x, y in net_label_positions
        if name.lower() not in power_names_lc
    ]

    seen_net_names: set[str] = set()

    for root, points in uf.groups().items():
        net_name = _nearest_label(points, signal_labels, _MAX_LABEL_DIST_PT)
        if net_name is None:
            continue
        if net_name in seen_net_names:
            # Merge into existing wire's nodes
            for w in wires:
                if w.net_name == net_name:
                    extra = _comps_near_points(comp_positions, points)
                    w.nodes = sorted(set(w.nodes) | extra)
            continue
        seen_net_names.add(net_name)

        nodes = sorted(_comps_near_points(comp_positions, points))
        wires.append(DetectedWire(net_name=net_name, nodes=nodes, confidence=0.85))

    return wires


def _nearest_label(
    points: list[tuple[float, float]],
    labels: list[tuple[str, float, float]],
    max_dist: float,
) -> str | None:
    best_name: str | None = None
    best_d = max_dist
    for px, py in points:
        for name, lx, ly in labels:
            d = _dist(px, py, lx, ly)
            if d < best_d:
                best_d = d
                best_name = name
    return best_name


def _comps_near_points(
    comp_positions: list[tuple[str, float, float]],
    points: list[tuple[float, float]],
) -> set[str]:
    result: set[str] = set()
    for ref, rx, ry in comp_positions:
        for px, py in points:
            if _dist(rx, ry, px, py) < _MAX_COMP_DIST_PT:
                result.add(ref)
                break
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────

def _dist(x0: float, y0: float, x1: float, y1: float) -> float:
    dx, dy = x0 - x1, y0 - y1
    return (dx * dx + dy * dy) ** 0.5
