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

_LIB_CRYSTAL = """\
    (symbol "Device:Crystal"
      (pin_numbers (hide yes))
      (pin_names (offset 1.016) (hide yes))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "Y" (at 0 3.302 0) (effects (font (size 1.27 1.27))))
      (property "Value" "Crystal" (at 0 -3.302 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "Crystal oscillator" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "Crystal_0_1"
        (rectangle (start -1.016 -2.54) (end 1.016 2.54)
          (stroke (width 0.254) (type default))
          (fill (type background))
        )
      )
      (symbol "Crystal_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27)
          (name "1" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 0 -3.81 90) (length 1.27)
          (name "2" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )"""

_LIB_Q_NPN = """\
    (symbol "Device:Q_NPN"
      (pin_numbers (hide yes))
      (pin_names (offset 1.016))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "Q" (at 5.08 1.27 0) (effects (font (size 1.27 1.27))))
      (property "Value" "Q_NPN" (at 5.08 -1.27 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "NPN bipolar transistor" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "Q_NPN_0_1"
        (rectangle (start -2.54 -3.81) (end 2.54 3.81)
          (stroke (width 0.254) (type default))
          (fill (type background))
        )
      )
      (symbol "Q_NPN_1_1"
        (pin input line (at -5.08 0 0) (length 2.54)
          (name "B" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 0 5.08 270) (length 1.27)
          (name "C" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 0 -5.08 90) (length 1.27)
          (name "E" (effects (font (size 1.27 1.27))))
          (number "3" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )"""

_LIB_Q_PNP = """\
    (symbol "Device:Q_PNP"
      (pin_numbers (hide yes))
      (pin_names (offset 1.016))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "Q" (at 5.08 1.27 0) (effects (font (size 1.27 1.27))))
      (property "Value" "Q_PNP" (at 5.08 -1.27 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "PNP bipolar transistor" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "Q_PNP_0_1"
        (rectangle (start -2.54 -3.81) (end 2.54 3.81)
          (stroke (width 0.254) (type default))
          (fill (type background))
        )
      )
      (symbol "Q_PNP_1_1"
        (pin input line (at -5.08 0 0) (length 2.54)
          (name "B" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 0 -5.08 90) (length 1.27)
          (name "C" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 0 5.08 270) (length 1.27)
          (name "E" (effects (font (size 1.27 1.27))))
          (number "3" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )"""

_LIB_FUSE = """\
    (symbol "Device:Fuse"
      (pin_numbers (hide yes))
      (pin_names (offset 1.016) (hide yes))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "F" (at 2.032 0 90) (effects (font (size 1.27 1.27))))
      (property "Value" "Fuse" (at 0 0 90) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "Fuse" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "Fuse_0_1"
        (arc (start 0 -2.032) (mid -1.016 -1.016) (end 0 0)
          (stroke (width 0) (type default))
          (fill (type none))
        )
        (arc (start 0 0) (mid -1.016 1.016) (end 0 2.032)
          (stroke (width 0) (type default))
          (fill (type none))
        )
        (polyline
          (pts (xy 0 -2.032) (xy 0 2.032))
          (stroke (width 0) (type default))
          (fill (type none))
        )
      )
      (symbol "Fuse_1_1"
        (pin passive line (at 0 3.81 270) (length 1.778)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27))))
        )
        (pin passive line (at 0 -3.81 90) (length 1.778)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27))))
        )
      )
      (embedded_fonts no)
    )"""

_LIB_FERRITE = """\
    (symbol "Device:Ferrite_Bead"
      (pin_numbers (hide yes))
      (pin_names (offset 0) (hide yes))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "FB" (at 2.032 0 90) (effects (font (size 1.27 1.27))))
      (property "Value" "Ferrite_Bead" (at 0 0 90) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "Ferrite bead" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "Ferrite_Bead_0_1"
        (rectangle (start -1.016 -2.54) (end 1.016 2.54)
          (stroke (width 0.254) (type default))
          (fill (type none))
        )
      )
      (symbol "Ferrite_Bead_1_1"
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

_LIB_CONN_1 = """\
    (symbol "Connector_Generic:Conn_01x01"
      (pin_names (offset 1.016) (hide yes))
      (exclude_from_sim no)
      (in_bom yes)
      (on_board yes)
      (property "Reference" "J" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
      (property "Value" "Conn_01x01" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (property "Description" "Generic connector, single row, 01x01" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
      (symbol "Conn_01x01_0_1"
        (rectangle (start -1.016 -1.016) (end 1.016 1.016)
          (stroke (width 0.254) (type default))
          (fill (type background))
        )
      )
      (symbol "Conn_01x01_1_1"
        (pin passive line (at -3.81 0 0) (length 2.794)
          (name "Pin_1" (effects (font (size 1.27 1.27))))
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
    "Device:Crystal": _LIB_CRYSTAL,
    "Device:Q_NPN": _LIB_Q_NPN,
    "Device:Q_PNP": _LIB_Q_PNP,
    "Device:Fuse": _LIB_FUSE,
    "Device:Ferrite_Bead": _LIB_FERRITE,
    "Connector_Generic:Conn_01x01": _LIB_CONN_1,
    "power:GND": _LIB_GND,
    "power:+5V": _LIB_PWR_5V,
}

# ---------------------------------------------------------------------------
# TODOs
# ---------------------------------------------------------------------------
#
# TODO: Symbol library lookup — AI + dialog integration
#   The current built-in stubs cover common passive/active prefixes.  The next
#   step is a three-stage lookup:
#     1. System KiCad library (/usr/share/kicad/symbols/*.kicad_sym) – uses the
#        real graphical shape and pin names.
#     2. Project-local .kicad_sym files (discovered from sym-lib-table or by
#        scanning the PDF's directory).
#     3. AI-assisted generation for anything not found in (1)/(2).
#   The plugin dialog should let the user confirm or correct the guessed symbol
#   before write_kicad_schematic() is called, so mistakes are caught before
#   they propagate into the schematic.
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

# Default locations to search for installed KiCad symbol libraries.
_KICAD_SYM_SEARCH_PATHS: list[str] = [
    "/usr/share/kicad/symbols",
    "/usr/local/share/kicad/symbols",
    os.path.join(
        os.environ.get("APPDATA", ""),
        "kicad", "9.0", "symbols",
    ),
]


def write_kicad_schematic(
    model: "SchematicModel",
    output_path: str,
    *,
    overlay_pdf: str | None = None,
    sym_lib_paths: list[str] | None = None,
) -> None:
    """Write *model* to a KiCad 9 .kicad_sch file at *output_path*.

    Also writes a companion ``.kicad_pro`` project file in the same directory
    (with the same base name) so that ``kicad-cli sch export svg`` can open the
    schematic without a "Failed to load schematic" error.  Without the project
    file KiCad's headless loader returns exit code 3 regardless of whether the
    schematic is otherwise valid.

    If *overlay_pdf* is given the overlay module is called to rasterise and
    embed the first page as a background bitmap (requires pypdfium2).

    *sym_lib_paths* is an optional list of directories that are searched for
    ``.kicad_sym`` library files (before the system-wide defaults).  This lets
    callers include a project-specific library directory alongside the PDF so
    that symbols defined there are embedded verbatim rather than approximated
    by the built-in stubs.
    """
    # Generate the sheet UUID here so it can be shared between the schematic
    # and the project file (which must reference the same root sheet UUID).
    sheet_uuid = _uid()
    project_name = os.path.splitext(os.path.basename(output_path))[0]
    content = render_kicad_schematic(
        model,
        overlay_pdf=overlay_pdf,
        sym_lib_paths=sym_lib_paths,
        sheet_uuid=sheet_uuid,
        project_name=project_name,
    )
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    # Write the companion .kicad_pro file.
    base = os.path.splitext(output_path)[0]
    pro_path = base + ".kicad_pro"
    project_name = os.path.basename(pro_path)
    _write_project_file(pro_path, project_name, sheet_uuid)


def render_kicad_schematic(
    model: "SchematicModel",
    *,
    overlay_pdf: str | None = None,
    sym_lib_paths: list[str] | None = None,
    sheet_uuid: str | None = None,
    project_name: str = "",
) -> str:
    """Return the .kicad_sch text for *model* without writing to disk.

    *sheet_uuid* may be supplied by the caller (e.g. ``write_kicad_schematic``
    shares the UUID with the companion ``.kicad_pro``).  If omitted a fresh
    UUID is generated automatically.

    *project_name* sets the ``(project "name" ...)`` token inside every symbol
    instance's ``(instances ...)`` block.  ``kicad-cli`` requires this to match
    the base name of the companion ``.kicad_pro`` file (without extension).
    ``write_kicad_schematic`` derives the correct name automatically; callers
    of ``render_kicad_schematic`` that intend to write the result to a named
    file should pass the matching project name explicitly.
    """
    n_components = len(model.components)
    paper, n_cols = _paper_and_cols(n_components)
    if sheet_uuid is None:
        sheet_uuid = _uid()
    lines: list[str] = []
    _header(lines, model, sheet_uuid, paper)
    # Build the effective search path: caller-supplied dirs first, then defaults.
    all_sym_paths: list[str] = list(sym_lib_paths or []) + _KICAD_SYM_SEARCH_PATHS
    lib_defs = _lib_symbols(lines, model, all_sym_paths)
    _symbol_instances(lines, model, sheet_uuid, lib_defs, n_cols, project_name)
    _wire_segments(lines, model)
    _net_labels(lines, model, n_cols)
    if overlay_pdf is not None:
        _bitmap_overlay(lines, overlay_pdf)
    _sheet_instances(lines, model.pages)
    lines.append("  (embedded_fonts no)")
    lines.append(")")
    return "\n".join(lines) + "\n"


def _write_project_file(path: str, project_name: str, sheet_uuid: str) -> None:
    """Write a minimal ``.kicad_pro`` project file.

    ``kicad-cli sch export svg`` opens a schematic through KiCad's project
    loader, which expects a matching ``.kicad_pro`` file in the same directory
    (same base name, ``.kicad_pro`` extension).  Without it the loader returns
    "Failed to load schematic" / exit code 3 even for a syntactically valid
    ``.kicad_sch`` file.

    The ``sheets`` array must list the root sheet UUID so that KiCad can bind
    the sheet hierarchy.  We pass the same UUID that was written into the
    ``(uuid ...)`` token of the companion ``.kicad_sch``.
    """
    import json
    content = {
        "meta": {
            "filename": project_name,
            "version": 3,
        },
        "schematic": {
            "meta": {"version": 1},
        },
        "sheets": [
            [sheet_uuid, "Root"],
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(content, fh, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------------------
# Internal rendering helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _mm(val: float) -> str:
    """Format a millimetre value as KiCad expects (up to 4 decimal places)."""
    return f"{val:.4f}".rstrip("0").rstrip(".")


def _sexp_str(s: str) -> str:
    """Escape a string for embedding inside KiCad S-expression double-quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


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


def _paper_and_cols(n_components: int) -> tuple[str, int]:
    """Choose paper size and grid column count based on component count."""
    if n_components <= 30:
        return "A4", 6
    if n_components <= 72:
        return "A3", 8
    if n_components <= 144:
        return "A2", 12
    if n_components <= 288:
        return "A1", 16
    return "A0", 20


def _header(lines: list[str], model: "SchematicModel", sheet_uuid: str, paper: str) -> None:
    lines += [
        "(kicad_sch",
        f"  (version {_FORMAT_VERSION})",
        f'  (generator "{_GENERATOR}")',
        f'  (generator_version "{_GENERATOR_VERSION}")',
        f'  (uuid "{sheet_uuid}")',
        f'  (paper "{paper}")',
    ]
    tb = getattr(model, "title_block", None)
    if tb:
        lines.append("  (title_block")
        for key, val in tb.items():
            lines.append(f'    ({key} "{val}")')
        lines.append("  )")


def _load_kicad_sym_file(path: str) -> dict[str, str]:
    """Parse a ``.kicad_sym`` file and return ``{symbol_name: raw_text}``.

    The returned text for each symbol is the verbatim S-expression block as it
    appears in the file (tabs, newlines and all) starting with ``(symbol "NAME"``
    and ending with the matching closing parenthesis.  Callers are responsible
    for prefixing the outer name with the library name before embedding.

    Returns an empty dict if the file cannot be read.
    """
    import re as _re
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {}

    symbols: dict[str, str] = {}
    i = 0
    n = len(text)
    depth = 0
    sym_start = -1
    sym_name: str | None = None
    in_string = False
    escape_next = False

    while i < n:
        c = text[i]
        if escape_next:
            escape_next = False
            i += 1
            continue
        if in_string:
            if c == "\\":
                escape_next = True
            elif c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c == "(":
                if depth == 1:
                    # Are we opening a top-level (symbol "NAME" ...) block?
                    m = _re.match(r'\(\s*symbol\s+"([^"]+)"', text[i : i + 300])
                    if m:
                        sym_name = m.group(1)
                        sym_start = i
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 1 and sym_start >= 0 and sym_name is not None:
                    symbols[sym_name] = text[sym_start : i + 1]
                    sym_start = -1
                    sym_name = None
        i += 1

    return symbols


def _find_symbol_in_libs(lib_id: str, search_paths: list[str]) -> str | None:
    """Return an embeddable symbol definition text for *lib_id*.

    Searches *search_paths* in order for a file named ``<lib_name>.kicad_sym``
    (where *lib_name* is the part of *lib_id* before the colon).  When found,
    the raw symbol block is returned with only the outer symbol name prefixed
    to ``"lib_name:sym_name"``; the inner sub-symbol names (``sym_name_X_Y``)
    are left unchanged because KiCad uses the bare base name there.

    Returns ``None`` if the symbol is not found in any of the search paths.
    """
    import re as _re
    if ":" not in lib_id:
        return None
    lib_name, sym_name = lib_id.split(":", 1)
    for search_dir in search_paths:
        sym_file = os.path.join(search_dir, f"{lib_name}.kicad_sym")
        if not os.path.isfile(sym_file):
            continue
        try:
            sym_map = _load_kicad_sym_file(sym_file)
        except Exception:
            continue
        if sym_name not in sym_map:
            continue
        raw = sym_map[sym_name]
        # Replace only the OUTER (first) occurrence of (symbol "sym_name")
        # with the fully-qualified name.  Inner sub-symbols like
        # (symbol "sym_name_0_1") are different strings so they are untouched.
        prefixed = _re.sub(
            r'\(\s*symbol\s+"' + _re.escape(sym_name) + r'"',
            f'(symbol "{lib_id}"',
            raw,
            count=1,
        )
        return prefixed
    return None


def _lib_symbols(
    lines: list[str],
    model: "SchematicModel",
    sym_lib_paths: list[str],
) -> dict[str, str]:
    """Emit the (lib_symbols ...) block and return a mapping lib_id → definition string.

    Resolution order for each lib_id:
    1. Built-in stubs (``_LIB_DEFS``).
    2. Files found in *sym_lib_paths* via ``_find_symbol_in_libs``.
    3. Generic ``power:`` derivation from the +5V template.
    4. Generic IC box (``_LIB_U`` template).

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
        else:
            # Try system / project library files.
            defn = _find_symbol_in_libs(lib_id, sym_lib_paths)
            if defn is None:
                if lib_id.startswith("power:"):
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
                    # Build a generic box using _LIB_U as a template.  We must
                    # update both the outer symbol name AND the inner sub-symbol
                    # names, because KiCad requires sub-symbols to be named
                    # "<base>_<demorgan>_<unit>" where <base> is the part of
                    # the lib_id after the colon.
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


def _grid_position(index: int, n_cols: int) -> tuple[float, float]:
    col = index % n_cols
    row = index // n_cols
    x = _ORIGIN_X_MM + col * _COL_SPACING_MM
    y = _ORIGIN_Y_MM + row * _ROW_SPACING_MM
    return x, y


def _symbol_instances(
    lines: list[str],
    model: "SchematicModel",
    sheet_uuid: str,
    lib_defs: dict[str, str],
    n_cols: int,
    project_name: str = "",
) -> None:
    for idx, comp in enumerate(model.components):
        # Use PDF-derived position when available; fall back to uniform grid.
        if comp.x_mm or comp.y_mm:
            x, y = comp.x_mm, comp.y_mm
        else:
            x, y = _grid_position(idx, n_cols)
        angle = getattr(comp, "angle", 0.0)
        sym_uuid = _uid()
        lines += [
            "  (symbol",
            f'    (lib_id "{comp.symbol}")',
            f"    (at {_mm(x)} {_mm(y)} {int(angle)})",
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
            f'      (project "{project_name}"',
            f'        (path "/{sheet_uuid}"',
            f'          (reference "{comp.ref}")',
            "          (unit 1)",
            "        )",
            "      )",
            "    )",
            "  )",
        ]


def _net_labels(lines: list[str], model: "SchematicModel", n_cols: int) -> None:
    """Place global net labels for every named net that has a detected label position.

    When the net carries PDF-derived label coordinates (``label_x_mm``,
    ``label_y_mm``), a single global label is placed at that wire endpoint.
    Otherwise the old grid-offset fallback is used so that unlocalised nets
    (e.g. from unit-test models) still appear in the output.
    """
    placed: set[str] = set()  # (net_name, mm_x, mm_y) — avoid duplicates

    # ── Pass 1: PDF-derived label positions ──────────────────────────────────
    for net in model.nets:
        lx = getattr(net, "label_x_mm", 0.0)
        ly = getattr(net, "label_y_mm", 0.0)
        if not lx and not ly:
            continue
        angle = getattr(net, "label_angle", 0)
        key = f"{net.name}@{_mm(lx)},{_mm(ly)}"
        if key in placed:
            continue
        placed.add(key)
        lines += [
            f'  (global_label "{_sexp_str(net.name)}"',
            "    (shape bidirectional)",
            f"    (at {_mm(lx)} {_mm(ly)} {angle})",
            "    (fields_autoplaced yes)",
            "    (effects (font (size 1.27 1.27)) (justify left))",
            f'    (uuid "{_uid()}")',
            '    (property "Intersheet References" ""',
            "      (at 0 0 0)",
            "      (effects (font (size 1.27 1.27)) (hide yes))",
            "    )",
            "  )",
        ]

    # ── Pass 2: Grid-offset fallback for nets without position data ──────────
    # Build a mapping: ref → list[(net_name, pin_number)]
    ref_pins: dict[str, list[tuple[str, str]]] = {}
    for net in model.nets:
        lx = getattr(net, "label_x_mm", 0.0)
        ly = getattr(net, "label_y_mm", 0.0)
        if lx or ly:
            continue  # already handled above
        for node in net.nodes:
            if "." in node:
                ref, pin = node.rsplit(".", 1)
            else:
                ref, pin = node, "1"
            ref_pins.setdefault(ref, []).append((net.name, pin))

    if not ref_pins:
        return

    # Index components by ref; use PDF position when available.
    comp_pos: dict[str, tuple[float, float]] = {}
    comp_idx: dict[str, int] = {}
    for i, c in enumerate(model.components):
        comp_idx[c.ref] = i
        if getattr(c, "x_mm", 0.0) or getattr(c, "y_mm", 0.0):
            comp_pos[c.ref] = (c.x_mm, c.y_mm)

    for ref, pin_entries in ref_pins.items():
        idx = comp_idx.get(ref)
        if idx is None:
            continue
        if ref in comp_pos:
            cx, cy = comp_pos[ref]
        else:
            cx, cy = _grid_position(idx, n_cols)
        for pin_offset, (net_name, _pin) in enumerate(pin_entries):
            label_x = cx + _LABEL_OFFSET_MM
            label_y = cy - _LABEL_OFFSET_MM + pin_offset * 2.54
            key = f"{net_name}@{_mm(label_x)},{_mm(label_y)}"
            if key in placed:
                continue
            placed.add(key)
            lines += [
                f'  (global_label "{_sexp_str(net_name)}"',
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


def _wire_segments(lines: list[str], model: "SchematicModel") -> None:
    """Emit PDF-derived wire segments as KiCad ``(wire ...)`` elements."""
    segments = getattr(model, "wire_segments", None)
    if not segments:
        return
    for x0, y0, x1, y1 in segments:
        lines += [
            "  (wire",
            f"    (pts (xy {_mm(x0)} {_mm(y0)}) (xy {_mm(x1)} {_mm(y1)}))",
            "    (stroke (width 0) (type default))",
            f'    (uuid "{_uid()}")',
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
