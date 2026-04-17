"""
KiCad 9 .kicad_sch writer.

Pure Python – no KiCad installation required.  Converts a SchematicModel into
a valid KiCad 9 S-expression schematic file that can be opened directly in the
schematic editor or processed by kicad-cli.
"""

from __future__ import annotations

import os
import sys
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pdf2sch import Component, Net, SchematicModel


# ---------------------------------------------------------------------------
# Format constants
# ---------------------------------------------------------------------------

_FORMAT_VERSION = 20250114  # KiCad 9 native format
_GENERATOR = "pdf2sch"
_GENERATOR_VERSION = "0.1.0"

# Component placement grid (millimetres, KiCad 9 uses mm in .kicad_sch)
_GRID_COLS = 6
_COL_SPACING_MM = 25.4   # 1 inch
_ROW_SPACING_MM = 30.0
_ORIGIN_X_MM = 25.4
_ORIGIN_Y_MM = 38.1

# The mm value used for "standard" pin length in net labels
_LABEL_OFFSET_MM = 5.08


# ---------------------------------------------------------------------------
# Minimal embedded symbol library definitions
# These are the canonical KiCad 9 Device:* definitions trimmed to the minimum
# needed for kicad-cli to render them without an external library lookup.
# ---------------------------------------------------------------------------

_LIB_R = """\
    (symbol "Device:R"
      (pin_numbers (hide yes))
      (pin_names (offset 0))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "R" (at 2.032 0 90) (effects (font (size 1.27 1.27))))
      (property "Value" "R" (at 0 0 90) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at -1.778 0 90) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "Resistor" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "R_0_1"
        (rectangle (start -1.016 -2.54) (end 1.016 2.54)
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
      )
      (symbol "R_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 0 -3.81 90) (length 1.27)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )"""

_LIB_C = """\
    (symbol "Device:C"
      (pin_names (offset 0.254))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "C" (at 1.016 -0.254 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Value" "C" (at 1.016 -2.032 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Footprint" "" (at 0.9652 -3.81 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "C_0_1"
        (polyline
          (pts (xy -2.032 -0.762) (xy 2.032 -0.762))
          (stroke (width 0.508) (type default))
          (fill (type none))
        )
        (polyline
          (pts (xy -2.032 0.762) (xy 2.032 0.762))
          (stroke (width 0.508) (type default))
          (fill (type none))
        )
      )
      (symbol "C_1_1"
        (pin passive line (at 0 3.81 270) (length 2.794)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 0 -3.81 90) (length 2.794)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )"""

_LIB_L = """\
    (symbol "Device:L"
      (pin_names (offset 1.016))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "L" (at 3.048 0 90) (effects (font (size 1.27 1.27))))
      (property "Value" "L" (at -3.048 0 90) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "L_0_1"
        (arc (start 0 -2.54) (mid -1.2573 -1.905) (end 0 -1.27)
          (stroke (width 0) (type default))
          (fill (type none))
        )
        (arc (start 0 -1.27) (mid -1.2573 -0.635) (end 0 0)
          (stroke (width 0) (type default))
          (fill (type none))
        )
        (arc (start 0 0) (mid -1.2573 0.635) (end 0 1.27)
          (stroke (width 0) (type default))
          (fill (type none))
        )
        (arc (start 0 1.27) (mid -1.2573 1.905) (end 0 2.54)
          (stroke (width 0) (type default))
          (fill (type none))
        )
      )
      (symbol "L_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 0 -3.81 90) (length 1.27)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )"""

_LIB_U = """\
    (symbol "Device:U"
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "U" (at 0 0 0) (effects (font (size 1.27 1.27))))
      (property "Value" "U" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "U_0_1"
        (rectangle (start -5.08 5.08) (end 5.08 -5.08)
          (stroke (width 0.254) (type default))
          (fill (type background))
        )
      )
      (embedded_fonts no)
    )"""

# LED diode – full Device:LED definition from KiCad 9 standard library.
_LIB_LED = """\
    (symbol "Device:LED"
      (pin_numbers (hide yes))
      (pin_names (offset 1.016) (hide yes))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "D" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
      (property "Value" "LED" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "Light emitting diode" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "LED_0_1"
        (polyline
          (pts (xy -3.048 -0.762) (xy -4.572 -2.286) (xy -3.81 -2.286) (xy -4.572 -2.286) (xy -4.572 -1.524))
          (stroke (width 0) (type default))
          (fill (type none))
        )
        (polyline
          (pts (xy -1.778 -0.762) (xy -3.302 -2.286) (xy -2.54 -2.286) (xy -3.302 -2.286) (xy -3.302 -1.524))
          (stroke (width 0) (type default))
          (fill (type none))
        )
        (polyline
          (pts (xy -1.27 0) (xy 1.27 0))
          (stroke (width 0) (type default))
          (fill (type none))
        )
        (polyline
          (pts (xy -1.27 -1.27) (xy -1.27 1.27))
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
        (polyline
          (pts (xy 1.27 -1.27) (xy 1.27 1.27) (xy -1.27 0) (xy 1.27 -1.27))
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
      )
      (symbol "LED_1_1"
        (pin passive line (at -3.81 0 0) (length 2.54)
          (name "K" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 3.81 0 180) (length 2.54)
          (name "A" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )"""

# Generic diode (no light rays) – Device:D.
_LIB_D = """\
    (symbol "Device:D"
      (pin_numbers (hide yes))
      (pin_names (offset 1.016) (hide yes))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "D" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
      (property "Value" "D" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "Diode" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "D_0_1"
        (polyline
          (pts (xy -1.27 0) (xy 1.27 0))
          (stroke (width 0) (type default))
          (fill (type none))
        )
        (polyline
          (pts (xy -1.27 -1.27) (xy -1.27 1.27))
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
        (polyline
          (pts (xy 1.27 -1.27) (xy 1.27 1.27) (xy -1.27 0) (xy 1.27 -1.27))
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
      )
      (symbol "D_1_1"
        (pin passive line (at -3.81 0 0) (length 2.54)
          (name "K" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 3.81 0 180) (length 2.54)
          (name "A" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )"""

# Power symbols – GND and +5V (embedded so kicad-cli needs no external library).
_LIB_GND = """\
    (symbol "power:GND"
      (power)
      (pin_names (offset 0))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "#PWR" (at 0 -6.35 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Value" "GND" (at 0 -3.81 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "Power symbol creates a global label with name \\"GND\\" , ground" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "GND_0_1"
        (polyline
          (pts (xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27) (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27))
          (stroke (width 0) (type default))
          (fill (type none))
        )
      )
      (symbol "GND_1_1"
        (pin power_in line (at 0 0 270) (length 0) (hide yes)
          (name "GND" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )"""

_LIB_PWR_5V = """\
    (symbol "power:+5V"
      (power)
      (pin_names (offset 0))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "#PWR" (at 0 -3.81 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Value" "+5V" (at 0 3.556 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "Power symbol creates a global label with name \\"+5V\\"" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "+5V_0_1"
        (polyline
          (pts (xy -0.762 1.27) (xy 0 2.54))
          (stroke (width 0) (type default))
          (fill (type none))
        )
        (polyline
          (pts (xy 0 2.54) (xy 0.762 1.27))
          (stroke (width 0) (type default))
          (fill (type none))
        )
        (polyline
          (pts (xy 0 0) (xy 0 2.54))
          (stroke (width 0) (type default))
          (fill (type none))
        )
      )
      (symbol "+5V_1_1"
        (pin power_in line (at 0 0 90) (length 0) (hide yes)
          (name "+5V" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )"""

# Map lib_id → embedded definition.
# NOTE: "Device:Unknown" is intentionally *not* listed here so that the
# fallback in _lib_symbols() replaces the symbol name correctly.  Listing it
# here would insert _LIB_U verbatim (name = "Device:U"), creating a mismatch
# with the (lib_id "Device:Unknown") in every symbol instance.
_LIB_DEFS: dict[str, str] = {
    "Device:R": _LIB_R,
    "Device:C": _LIB_C,
    "Device:L": _LIB_L,
    "Device:LED": _LIB_LED,
    "Device:D": _LIB_D,
    "Device:U": _LIB_U,
    "power:GND": _LIB_GND,
    "power:+5V": _LIB_PWR_5V,
}

# ---------------------------------------------------------------------------
# TODOs
# ---------------------------------------------------------------------------
#
# TODO: Symbol library lookup
#   Instead of embedding a small static set of lib definitions, query KiCad's
#   installed standard library (kicad-symbols, typically at
#   /usr/share/kicad/symbols/*.kicad_sym) when available, then fall back to
#   community libraries, then to AI-assisted generation.  The dialog should let
#   the user confirm or override the chosen symbol before the schematic is
#   written.  Pin counts, pin names, and graphical shape will then always be
#   authoritative rather than approximated.
#
# TODO: Plugin dialog screenshots in CI
#   End-to-end testing of the KiCad plugin UI (the wx dialog, file picker,
#   confidence slider, etc.) is currently not covered by CI.  A future task
#   should set up a headless X server (Xvfb) on the CI runner, launch KiCad
#   with the plugin pre-installed, drive it via xdotool or a KiCad scripting
#   hook, and capture screenshots as build artefacts so regressions in the
#   user-facing flow are caught automatically.
#
# TODO: Extend KiCad's schematic plugin scripting API
#   The eeschema Python API exposed to plugins is currently too thin to drive
#   the full plugin flow programmatically (e.g. triggering Run(), reading the
#   resulting schematic, asserting on its content).  A future task should
#   upstream a small addition to KiCad's scripting bridge – or maintain a
#   local patch – so that plugin authors can write proper integration tests
#   without resorting to fragile GUI automation.


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_kicad_schematic(
    model: "SchematicModel",
    output_path: str,
    *,
    overlay_pdf: str | None = None,
) -> None:
    """Write *model* to a KiCad 9 .kicad_sch file at *output_path*.

    If *overlay_pdf* is given the overlay module is called to rasterise and
    embed the first page as a background bitmap (requires pypdfium2).
    """
    content = render_kicad_schematic(model, overlay_pdf=overlay_pdf)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)


def render_kicad_schematic(
    model: "SchematicModel",
    *,
    overlay_pdf: str | None = None,
) -> str:
    """Return the .kicad_sch text for *model* without writing to disk."""
    sheet_uuid = _uid()
    lines: list[str] = []
    _header(lines, model.pages, sheet_uuid)
    lib_defs = _lib_symbols(lines, model)
    _symbol_instances(lines, model, sheet_uuid, lib_defs)
    _net_labels(lines, model)
    if overlay_pdf is not None:
        _bitmap_overlay(lines, overlay_pdf)
    _sheet_instances(lines, model.pages)
    lines.append("  (embedded_fonts no)")
    lines.append(")")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Internal rendering helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _mm(val: float) -> str:
    """Format a millimetre value as KiCad expects (up to 4 decimal places)."""
    return f"{val:.4f}".rstrip("0").rstrip(".")


def _extract_pin_numbers(lib_def: str) -> list[str]:
    """Return the ordered list of pin numbers declared in a lib symbol string.

    Scans for ``(number "N" ...)`` tokens that appear inside a ``(pin ...)``
    block.  This is intentionally simple: it does not parse a full S-expression
    tree, it just looks for the pattern that KiCad always emits.  The result is
    used to populate per-instance ``(pin "N" (uuid "..."))`` entries which
    KiCad 9 requires for connectivity.

    Because pin numbers are extracted from the *same* definition string that
    gets embedded in the schematic file, the count is always consistent with
    the actual symbol regardless of how many pins it has.
    """
    import re
    # Find every (number "...") that is a child of a (pin ...) clause.
    # KiCad always writes: (pin TYPE STYLE (at ...) ... (number "N" ...) ...)
    # so we search for (number "<digits_or_text>" within a context that
    # starts with "(pin ".
    seen: dict[str, int] = {}   # preserve order, deduplicate
    for m in re.finditer(r'\(number\s+"([^"]+)"', lib_def):
        n = m.group(1)
        if n not in seen:
            seen[n] = len(seen)
    return list(seen)


def _header(lines: list[str], pages: int, sheet_uuid: str) -> None:
    lines += [
        "(kicad_sch",
        f"  (version {_FORMAT_VERSION})",
        f'  (generator "{_GENERATOR}")',
        f'  (generator_version "{_GENERATOR_VERSION}")',
        f'  (uuid "{sheet_uuid}")',
        '  (paper "A4")',
    ]


def _lib_symbols(lines: list[str], model: "SchematicModel") -> dict[str, str]:
    """Emit the (lib_symbols ...) block and return a mapping lib_id → definition string.

    The returned map is used by _symbol_instances so it can call
    _extract_pin_numbers() on the actual definition rather than a separate
    hardcoded pin-count table.
    """
    lines.append("  (lib_symbols")
    seen: dict[str, str] = {}
    for comp in model.components:
        lib_id = comp.symbol
        if lib_id in seen:
            continue
        if lib_id in _LIB_DEFS:
            defn = _LIB_DEFS[lib_id]
        elif lib_id.startswith("power:"):
            # Generic power symbol: derive from the +5V template.
            pwr_name = lib_id[len("power:"):]
            safe = pwr_name.replace("+", "").replace("-", "").replace(".", "_")
            defn = (
                _LIB_PWR_5V
                .replace('"power:+5V"', f'"{lib_id}"')
                .replace('"+5V"', f'"{pwr_name}"')
                .replace('"+5V_0_1"', f'"{safe}_0_1"')
                .replace('"+5V_1_1"', f'"{safe}_1_1"')
            )
        else:
            # Build a generic box using _LIB_U as a template.  We must update
            # both the outer symbol name AND the inner sub-symbol names, because
            # KiCad requires sub-symbols to be named "<base>_<demorgan>_<unit>"
            # where <base> is the part of the lib_id after the colon.
            base_name = lib_id.split(":", 1)[-1]
            defn = (
                _LIB_U
                .replace('"Device:U"', f'"{lib_id}"')
                .replace('"U_0_1"', f'"{base_name}_0_1"')
            )
        seen[lib_id] = defn
        lines.append(defn)
    lines.append("  )")
    return seen


def _grid_position(index: int) -> tuple[float, float]:
    col = index % _GRID_COLS
    row = index // _GRID_COLS
    x = _ORIGIN_X_MM + col * _COL_SPACING_MM
    y = _ORIGIN_Y_MM + row * _ROW_SPACING_MM
    return x, y


def _symbol_instances(
    lines: list[str],
    model: "SchematicModel",
    sheet_uuid: str,
    lib_defs: dict[str, str],
) -> None:
    for idx, comp in enumerate(model.components):
        x, y = _grid_position(idx)
        sym_uuid = _uid()
        lines += [
            "  (symbol",
            f'    (lib_id "{comp.symbol}")',
            f"    (at {_mm(x)} {_mm(y)} 0)",
            "    (unit 1)",
            "    (exclude_from_sim no)",
            "    (in_bom yes)",
            "    (on_board yes)",
            "    (dnp no)",
            "    (fields_autoplaced yes)",
            f'    (uuid "{sym_uuid}")',
            f'    (property "Reference" "{comp.ref}"',
            f"      (at {_mm(x + 1.27)} {_mm(y - 1.27)} 0)",
            "      (effects (font (size 1.27 1.27)))",
            "    )",
            f'    (property "Value" "{comp.value}"',
            f"      (at {_mm(x + 1.27)} {_mm(y + 1.27)} 0)",
            "      (effects (font (size 1.27 1.27)))",
            "    )",
            f'    (property "Footprint" "{comp.footprint}"',
            f"      (at {_mm(x)} {_mm(y)} 0)",
            "      (effects (font (size 1.27 1.27)) (hide yes))",
            "    )",
            '    (property "Datasheet" "~"',
            f"      (at {_mm(x)} {_mm(y)} 0)",
            "      (effects (font (size 1.27 1.27)) (hide yes))",
            "    )",
            '    (property "Description" ""',
            f"      (at {_mm(x)} {_mm(y)} 0)",
            "      (effects (font (size 1.27 1.27)) (hide yes))",
            "    )",
        ]
        # KiCad 9 requires a (pin "N" (uuid "...")) entry for every pin in the
        # symbol so it can build the connectivity model.  Extract pin numbers
        # from the *actual* lib definition we embedded – this stays correct
        # regardless of how many pins the symbol has.
        lib_def_text = lib_defs.get(comp.symbol, "")
        pin_numbers = _extract_pin_numbers(lib_def_text)
        if not pin_numbers:
            # Fallback: collect any pin numbers referenced in nets.
            pin_set: set[str] = set()
            for net in model.nets:
                for node in net.nodes:
                    if "." in node:
                        ref, pin = node.rsplit(".", 1)
                        if ref == comp.ref:
                            pin_set.add(pin)
            pin_numbers = sorted(pin_set)
        for pnum in pin_numbers:
            lines.append(f'    (pin "{pnum}" (uuid "{_uid()}"))')
        lines += [
            "    (instances",
            '      (project ""',
            f'        (path "/{sheet_uuid}"',
            f'          (reference "{comp.ref}")',
            "          (unit 1)",
            "        )",
            "      )",
            "    )",
            "  )",
        ]


def _net_labels(lines: list[str], model: "SchematicModel") -> None:
    """Place a global net label near every component that appears in a net."""
    # Build a mapping: ref → list[(net_name, pin_number)]
    ref_pins: dict[str, list[tuple[str, str]]] = {}
    for net in model.nets:
        for node in net.nodes:
            if "." in node:
                ref, pin = node.rsplit(".", 1)
            else:
                ref, pin = node, "1"
            ref_pins.setdefault(ref, []).append((net.name, pin))

    # Index components by ref
    comp_idx: dict[str, int] = {c.ref: i for i, c in enumerate(model.components)}

    placed: set[str] = set()  # avoid duplicate labels at the same position
    for ref, pin_entries in ref_pins.items():
        idx = comp_idx.get(ref)
        if idx is None:
            continue
        x, y = _grid_position(idx)
        for pin_offset, (net_name, _pin) in enumerate(pin_entries):
            label_x = x + _LABEL_OFFSET_MM
            label_y = y - _LABEL_OFFSET_MM + pin_offset * 2.54
            key = f"{net_name}@{_mm(label_x)},{_mm(label_y)}"
            if key in placed:
                continue
            placed.add(key)
            lines += [
                "  (global_label",
                f'    (text "{net_name}")',
                "    (shape bidirectional)",
                f"    (at {_mm(label_x)} {_mm(label_y)} 0)",
                "    (fields_autoplaced yes)",
                "    (effects (font (size 1.27 1.27)) (justify left))",
                f'    (uuid "{_uid()}")',
                '    (property "Intersheet References" ""',
                "      (at 0 0 0)",
                "      (effects (font (size 1.27 1.27)) (hide yes))",
                "    )",
                "  )",
            ]


def _bitmap_overlay(lines: list[str], pdf_path: str) -> None:
    """Rasterise the first page of *pdf_path* and embed as SCH_BITMAP."""
    try:
        from pdf2sch_plugin_overlay import rasterise_first_page  # type: ignore[import]
    except ImportError:
        # overlay module not available (e.g. pypdfium2 not installed) – skip silently
        return

    png_path = rasterise_first_page(pdf_path)
    if not png_path or not os.path.exists(png_path):
        return

    lines += [
        "  (image",
        f"    (at {_mm(_ORIGIN_X_MM)} {_mm(_ORIGIN_Y_MM)})",
        "    (scale 1)",
        f'    (uuid "{_uid()}")',
        '    (data',
    ]
    import base64
    with open(png_path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode()
    # KiCad stores base64 in 76-char chunks
    for i in range(0, len(encoded), 76):
        lines.append(f"      {encoded[i:i+76]}")
    lines.append("    )")
    lines.append("  )")


def _sheet_instances(lines: list[str], pages: int) -> None:
    lines.append("  (sheet_instances")
    for page_num in range(1, pages + 1):
        path = "/" if page_num == 1 else f"/page{page_num}"
        lines.append(f'    (path "{path}" (page "{page_num}"))')
    lines.append("  )")
