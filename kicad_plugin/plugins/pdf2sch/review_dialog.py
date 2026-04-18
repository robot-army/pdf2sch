"""
wx.Dialog for reviewing low-confidence nets before the schematic is written.

Each net flagged with a REVIEW_REQUIRED_ prefix is displayed in a scrollable
list.  The user can accept the detected name or type a replacement.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pdf2sch import SchematicModel


def _wx():
    return sys.modules.get("wx")


class ReviewDialog:
    """Scrollable grid showing every low-confidence net for user confirmation."""

    def __init__(self, parent=None, model: "SchematicModel | None" = None) -> None:
        wx = _wx()
        if wx is None:  # pragma: no cover
            raise RuntimeError("wx is not available")

        super().__init__(
            parent,
            title="pdf2sch – Review low-confidence nets",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        self._model = model
        self._row_ctrls: list[tuple[int, object]] = []  # (net_idx, TextCtrl)
        self._build_ui(wx)
        self.Fit()
        self.SetSize(600, 400)
        self.Centre()

    # ------------------------------------------------------------------

    def _build_ui(self, wx) -> None:
        vbox = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            self,
            label=(
                "The following nets have low detection confidence.\n"
                "Edit the net name to correct it, or leave as-is to accept."
            ),
        )
        vbox.Add(intro, flag=wx.ALL, border=8)

        scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        scroll.SetScrollRate(0, 10)
        grid = wx.FlexGridSizer(cols=3, hgap=8, vgap=4)
        grid.AddGrowableCol(1, proportion=1)

        config = getattr(self._model, "_config", None)
        prefix = "REVIEW_REQUIRED_"

        for net_idx, question in zip(
            self._model.review_net_indices,
            self._model.review_questions,
        ):
            net = self._model.nets[net_idx]
            raw_name = net.name.removeprefix(prefix) if net.name.startswith(prefix) else net.name

            grid.Add(wx.StaticText(scroll, label=f"Net {net_idx}:"), flag=wx.ALIGN_CENTER_VERTICAL)
            ctrl = wx.TextCtrl(scroll, value=raw_name, size=(200, -1))
            grid.Add(ctrl, flag=wx.EXPAND)
            grid.Add(
                wx.StaticText(scroll, label=question[:60] + ("…" if len(question) > 60 else "")),
                flag=wx.ALIGN_CENTER_VERTICAL,
            )
            self._row_ctrls.append((net_idx, ctrl))

        scroll.SetSizer(grid)
        vbox.Add(scroll, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK, label="Accept all")
        ok_btn.SetDefault()
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(wx.Button(self, wx.ID_CANCEL, label="Discard review"))
        btn_sizer.Realize()
        vbox.Add(btn_sizer, flag=wx.EXPAND | wx.ALL, border=8)

        self.SetSizer(vbox)

    # ------------------------------------------------------------------

    def get_reviewed_model(self) -> "SchematicModel":
        """Apply user edits to *self._model* and return it."""
        for net_idx, ctrl in self._row_ctrls:
            new_name = ctrl.GetValue().strip()
            if new_name:
                self._model.nets[net_idx].name = new_name
        return self._model


def _patch_base_class() -> None:
    wx = _wx()
    if wx is None:
        return
    wx_dialog = getattr(wx, "Dialog", None)
    if wx_dialog is None or not isinstance(wx_dialog, type):
        return
    if wx_dialog not in ReviewDialog.__bases__:
        ReviewDialog.__bases__ = (wx_dialog,)


_patch_base_class()
