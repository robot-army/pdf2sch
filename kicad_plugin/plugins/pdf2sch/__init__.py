"""
KiCad 9 PCM Action Plugin entry point.

KiCad loads every Python package found under ``<pcm_install>/plugins/`` and
calls ``register()`` on any ``ActionPlugin`` subclass it discovers.  This
module registers the pdf2sch action, which adds an entry to the PCB editor's
*Tools* menu.

Running from the eeschema scripting console
-------------------------------------------
In KiCad 9 the scripting console is available from the schematic editor via
*Tools → Scripting Console*.  To trigger the import dialog manually::

    import pdf2sch
    pdf2sch.PDF2SchAction().Run()

That invocation bypasses KiCad's action-plugin registration and calls the
dialog directly, making it usable from both the PCB editor *and* the schematic
editor without a KiCad fork.
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Conditional pcbnew import – the module must be importable in unit tests
# where pcbnew is replaced by a mock via sys.modules.
# ---------------------------------------------------------------------------
try:
    import pcbnew  # type: ignore[import]
    _PCBNEW_AVAILABLE = True
except ImportError:
    pcbnew = None  # type: ignore[assignment]
    _PCBNEW_AVAILABLE = False

# Ensure the repo root is on sys.path so that pdf2sch.py is importable when
# the plugin runs inside KiCad (the repo root is not added automatically).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ---------------------------------------------------------------------------
# Base class shim so the class definition works when pcbnew is unavailable
# ---------------------------------------------------------------------------
_ActionPluginBase = (pcbnew.ActionPlugin if _PCBNEW_AVAILABLE else object)


class PDF2SchAction(_ActionPluginBase):  # type: ignore[misc]
    """KiCad 9 action plugin: import a PDF schematic into KiCad."""

    def defaults(self) -> None:  # noqa: D102
        self.name = "pdf2sch"
        self.category = "Import"
        self.description = "Import a PDF schematic and generate a KiCad 9 .kicad_sch file"
        self.show_toolbar_button = False  # toolbar button requires an icon
        icon_path = os.path.join(_HERE, "resources", "icon.png")
        if os.path.exists(icon_path):
            self.icon_file_name = icon_path
            self.show_toolbar_button = True

    # KiCad convention: method name is capitalised
    def Run(self) -> None:  # noqa: N802
        import sys as _sys
        wx = _sys.modules.get("wx")
        if wx is None:
            try:
                import wx  # type: ignore[import]
            except ImportError:
                _fallback_no_wx()
                return

        app = wx.GetApp()
        parent = app.GetTopWindow() if app else None

        from pdf2sch.dialog import PDF2SchDialog
        dlg = PDF2SchDialog(parent)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return

        pdf_source = dlg.get_pdf_source()
        config = dlg.get_config()
        import_overlay = dlg.get_import_overlay()
        dlg.Destroy()

        if not pdf_source:
            wx.MessageBox("No PDF source specified.", "pdf2sch", wx.OK | wx.ICON_WARNING, parent)
            return

        from pdf2sch.pipeline import PDF2SchPipeline
        from pdf2sch.writer import write_kicad_schematic

        pipeline = PDF2SchPipeline(config=config)
        detection = pipeline.detect(pdf_source)
        model = pipeline.build_model(detection)

        # Inline review for uncertain nets
        if model.review_questions:
            from pdf2sch.review_dialog import ReviewDialog
            rdlg = ReviewDialog(parent, model)
            if rdlg.ShowModal() == wx.ID_OK:
                model = rdlg.get_reviewed_model()
            rdlg.Destroy()

        out_path = _choose_output_path(wx, parent, pdf_source)
        if not out_path:
            return

        write_kicad_schematic(
            model,
            out_path,
            overlay_pdf=pdf_source if import_overlay else None,
        )

        wx.MessageBox(
            f"Schematic written to:\n{out_path}\n\n"
            "Open it with File \u2192 Open Schematic in the schematic editor.",
            "pdf2sch complete",
            wx.OK | wx.ICON_INFORMATION,
            parent,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _choose_output_path(wx, parent, pdf_source: str) -> str | None:
    import os as _os
    default_name = _os.path.splitext(_os.path.basename(pdf_source))[0] + ".kicad_sch"
    with wx.FileDialog(
        parent,
        "Save KiCad Schematic",
        wildcard="KiCad Schematic (*.kicad_sch)|*.kicad_sch",
        defaultFile=default_name,
        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
    ) as fd:
        if fd.ShowModal() == wx.ID_CANCEL:
            return None
        return fd.GetPath()


def _fallback_no_wx() -> None:
    """Minimal headless fallback when wx is not available (e.g. scripting console)."""
    print(
        "[pdf2sch] wx is not available.  Run the following in a terminal:\n"
        "    python -c \"from pdf2sch import convert_pdf_to_kicad; "
        "open('out.kicad_sch','w').write(convert_pdf_to_kicad('your.pdf'))\""
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register() -> None:
    """Register the action plugin with KiCad 9 (called automatically at load)."""
    if _PCBNEW_AVAILABLE:
        PDF2SchAction().register()


register()
