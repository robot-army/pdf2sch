"""
wx.Dialog for the pdf2sch import options.

Intentionally importable without wx installed so that unit tests can mock the
``wx`` module at the ``sys.modules`` level before importing this file.
"""

from __future__ import annotations

import sys


def _wx():
    """Return the wx module (allows test mocking via sys.modules)."""
    return sys.modules.get("wx")


class PDF2SchDialog:
    """Import-options dialog shown before the pipeline runs."""

    def __init__(self, parent=None) -> None:
        wx = _wx()
        if wx is None:  # pragma: no cover – only reached inside KiCad
            raise RuntimeError("wx is not available")

        super().__init__(
            parent,
            title="pdf2sch – Import PDF Schematic",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        self._build_ui(wx)
        self.Fit()
        self.Centre()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, wx) -> None:
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # PDF source row
        src_box = wx.StaticBox(panel, label="PDF source")
        src_sizer = wx.StaticBoxSizer(src_box, wx.VERTICAL)

        self._pdf_picker = wx.FilePickerCtrl(
            panel,
            message="Select PDF schematic",
            wildcard="PDF files (*.pdf)|*.pdf|All files (*.*)|*.*",
            style=wx.FLP_OPEN | wx.FLP_FILE_MUST_EXIST | wx.FLP_USE_TEXTCTRL,
        )
        src_sizer.Add(self._pdf_picker, flag=wx.EXPAND | wx.ALL, border=4)

        url_row = wx.BoxSizer(wx.HORIZONTAL)
        url_row.Add(wx.StaticText(panel, label="…or URL:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self._url_ctrl = wx.TextCtrl(panel, size=(320, -1))
        url_row.Add(self._url_ctrl, proportion=1, flag=wx.EXPAND | wx.LEFT, border=4)
        src_sizer.Add(url_row, flag=wx.EXPAND | wx.ALL, border=4)
        vbox.Add(src_sizer, flag=wx.EXPAND | wx.ALL, border=8)

        # Options row
        opts_box = wx.StaticBox(panel, label="Options")
        opts_sizer = wx.StaticBoxSizer(opts_box, wx.VERTICAL)

        conf_row = wx.BoxSizer(wx.HORIZONTAL)
        conf_row.Add(
            wx.StaticText(panel, label="Low-confidence threshold:"),
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        self._conf_slider = wx.Slider(
            panel, value=80, minValue=0, maxValue=100,
            style=wx.SL_HORIZONTAL | wx.SL_LABELS,
        )
        conf_row.Add(self._conf_slider, proportion=1, flag=wx.EXPAND | wx.LEFT, border=8)
        opts_sizer.Add(conf_row, flag=wx.EXPAND | wx.ALL, border=4)

        self._overlay_chk = wx.CheckBox(panel, label="Import PDF pages as background overlay")
        self._overlay_chk.SetValue(True)
        opts_sizer.Add(self._overlay_chk, flag=wx.ALL, border=4)

        vbox.Add(opts_sizer, flag=wx.EXPAND | wx.ALL, border=8)

        # Buttons
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK)
        ok_btn.SetDefault()
        cancel_btn = wx.Button(panel, wx.ID_CANCEL)
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, flag=wx.EXPAND | wx.ALL, border=8)

        panel.SetSizer(vbox)

    # ------------------------------------------------------------------
    # Value accessors (called by the plugin after ShowModal() == ID_OK)
    # ------------------------------------------------------------------

    def get_pdf_source(self) -> str:
        """Return the PDF path or URL entered by the user."""
        path = self._pdf_picker.GetPath().strip()
        if path:
            return path
        return self._url_ctrl.GetValue().strip()

    def get_config(self):
        """Return a PipelineConfig built from the dialog values."""
        PipelineConfig = _resolve_pipeline_config()
        threshold = self._conf_slider.GetValue() / 100.0
        return PipelineConfig(low_confidence_threshold=threshold)

    def get_import_overlay(self) -> bool:
        """Return True if the user wants a PDF background overlay."""
        return bool(self._overlay_chk.GetValue())


# PDF2SchDialog must inherit from wx.Dialog at class-creation time so KiCad's
# wx event loop can manage it.  We defer the inheritance to avoid importing wx
# at module load time (which would fail outside KiCad).
def _patch_base_class() -> None:
    wx = _wx()
    if wx is None:
        return
    wx_dialog = getattr(wx, "Dialog", None)
    # Only patch when wx.Dialog is a genuine class (not a MagicMock used in tests).
    if wx_dialog is None or not isinstance(wx_dialog, type):
        return
    if wx_dialog not in PDF2SchDialog.__bases__:
        PDF2SchDialog.__bases__ = (wx_dialog,)


# Patch is applied when the module is first imported inside KiCad.
_patch_base_class()
