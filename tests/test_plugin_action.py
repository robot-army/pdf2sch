"""
Unit tests for the KiCad 9 action-plugin entry point (__init__.py), dialog,
overlay, and review_dialog modules.

pcbnew and wx are replaced by lightweight in-process mocks injected into
sys.modules *before* any plugin import, so no KiCad installation is required.

We load the plugin package by file path via importlib to avoid the naming
collision between the root ``pdf2sch.py`` module and the plugin package
``kicad_plugin/plugins/pdf2sch/``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PLUGIN_PKG = os.path.join(_REPO_ROOT, "kicad_plugin", "plugins", "pdf2sch")


def _load_plugin_file(module_name: str, filename: str, extra_sys_modules: dict | None = None):
    """Load a plugin source file by path, with optional sys.modules pre-population."""
    path = os.path.join(_PLUGIN_PKG, filename)
    # Remove any previously cached version
    sys.modules.pop(module_name, None)
    if extra_sys_modules:
        sys.modules.update(extra_sys_modules)
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------

class _MockActionPlugin:
    def defaults(self) -> None: ...
    def Run(self) -> None: ...  # noqa: N802
    def register(self) -> None: ...


def _make_pcbnew_mock() -> types.ModuleType:
    mod = types.ModuleType("pcbnew")
    mod.ActionPlugin = _MockActionPlugin
    return mod


def _make_wx_mock() -> types.ModuleType:
    wx = types.ModuleType("wx")
    wx.ID_OK = 5100
    wx.ID_CANCEL = 5101
    wx.DEFAULT_DIALOG_STYLE = 0x0001
    wx.RESIZE_BORDER = 0x0040
    wx.VSCROLL = 0x80000000
    wx.HORIZONTAL = 4
    wx.VERTICAL = 8
    wx.EXPAND = 8192
    wx.ALL = 15
    wx.LEFT = 16
    wx.ALIGN_CENTER_VERTICAL = 256
    wx.OK = 4
    wx.ICON_WARNING = 256
    wx.ICON_INFORMATION = 512
    wx.FLP_OPEN = 1
    wx.FLP_FILE_MUST_EXIST = 2
    wx.FLP_USE_TEXTCTRL = 4
    wx.SL_HORIZONTAL = 4
    wx.SL_LABELS = 512
    wx.FD_SAVE = 2
    wx.FD_OVERWRITE_PROMPT = 16
    for cls_name in (
        "Dialog", "Panel", "BoxSizer", "StaticBox", "StaticBoxSizer",
        "FilePickerCtrl", "TextCtrl", "CheckBox", "Slider", "StaticText",
        "Button", "StdDialogButtonSizer", "ScrolledWindow", "FlexGridSizer",
        "FileDialog",
    ):
        setattr(wx, cls_name, MagicMock(name=cls_name))
    wx.GetApp = MagicMock(return_value=MagicMock(GetTopWindow=MagicMock(return_value=None)))
    wx.MessageBox = MagicMock()
    return wx


# ---------------------------------------------------------------------------
# Helper: ensure pipeline module is loaded (provides _pdf2sch_core)
# ---------------------------------------------------------------------------

def _ensure_pipeline_loaded():
    if "_test_act_pipeline" not in sys.modules:
        _load_plugin_file("_test_act_pipeline", "pipeline.py")


# ---------------------------------------------------------------------------
# Tests: ActionPlugin defaults
# ---------------------------------------------------------------------------

class TestPDF2SchActionDefaults(unittest.TestCase):
    def setUp(self):
        _ensure_pipeline_loaded()
        self._pcbnew = _make_pcbnew_mock()

    def _load_action_module(self):
        return _load_plugin_file(
            "_test_action_init",
            "__init__.py",
            extra_sys_modules={"pcbnew": self._pcbnew},
        )

    def test_name_attribute(self):
        mod = self._load_action_module()
        action = mod.PDF2SchAction()
        action.defaults()
        self.assertEqual(action.name, "pdf2sch")

    def test_category_attribute(self):
        mod = self._load_action_module()
        action = mod.PDF2SchAction()
        action.defaults()
        self.assertEqual(action.category, "Import")

    def test_description_non_empty(self):
        mod = self._load_action_module()
        action = mod.PDF2SchAction()
        action.defaults()
        self.assertTrue(action.description)


# ---------------------------------------------------------------------------
# Tests: register() calls pcbnew ActionPlugin.register()
# ---------------------------------------------------------------------------

class TestPDF2SchActionRegistration(unittest.TestCase):
    def test_register_invoked_once_when_pcbnew_available(self):
        _ensure_pipeline_loaded()
        registered: list[bool] = []

        class TrackingPlugin(_MockActionPlugin):
            def register(self):
                registered.append(True)

        pcbnew_mock = _make_pcbnew_mock()
        pcbnew_mock.ActionPlugin = TrackingPlugin

        _load_plugin_file(
            "_test_reg_init",
            "__init__.py",
            extra_sys_modules={"pcbnew": pcbnew_mock},
        )
        self.assertEqual(len(registered), 1)

    def test_no_crash_when_pcbnew_absent(self):
        _ensure_pipeline_loaded()
        sys.modules.pop("pcbnew", None)
        _load_plugin_file("_test_no_pcbnew_init", "__init__.py")
        # No exception = pass


# ---------------------------------------------------------------------------
# Tests: dialog value accessors
# ---------------------------------------------------------------------------

class TestPDF2SchDialogAccessors(unittest.TestCase):
    def setUp(self):
        _ensure_pipeline_loaded()
        self._wx = _make_wx_mock()
        sys.modules["wx"] = self._wx

    def tearDown(self):
        sys.modules.pop("wx", None)
        sys.modules.pop("_test_dialog", None)

    def _make_stub_dialog(self, path="", url="", conf=80, overlay=True):
        mod = _load_plugin_file("_test_dialog", "dialog.py")
        dlg = mod.PDF2SchDialog.__new__(mod.PDF2SchDialog)
        dlg._pdf_picker = MagicMock()
        dlg._pdf_picker.GetPath.return_value = path
        dlg._url_ctrl = MagicMock()
        dlg._url_ctrl.GetValue.return_value = url
        dlg._conf_slider = MagicMock()
        dlg._conf_slider.GetValue.return_value = conf
        dlg._overlay_chk = MagicMock()
        dlg._overlay_chk.GetValue.return_value = overlay
        return dlg

    def test_get_pdf_source_returns_file_path(self):
        dlg = self._make_stub_dialog(path="/tmp/sch.pdf")
        self.assertEqual(dlg.get_pdf_source(), "/tmp/sch.pdf")

    def test_get_pdf_source_falls_back_to_url(self):
        dlg = self._make_stub_dialog(path="", url="https://example.com/sch.pdf")
        self.assertEqual(dlg.get_pdf_source(), "https://example.com/sch.pdf")

    def test_get_config_respects_slider(self):
        dlg = self._make_stub_dialog(conf=65)
        config = dlg.get_config()
        self.assertAlmostEqual(config.low_confidence_threshold, 0.65)

    def test_get_import_overlay_true(self):
        self.assertTrue(self._make_stub_dialog(overlay=True).get_import_overlay())

    def test_get_import_overlay_false(self):
        self.assertFalse(self._make_stub_dialog(overlay=False).get_import_overlay())


# ---------------------------------------------------------------------------
# Tests: overlay
# ---------------------------------------------------------------------------

class TestOverlay(unittest.TestCase):
    def _load_overlay(self):
        return _load_plugin_file("_test_overlay", "overlay.py")

    def test_returns_none_when_pypdfium2_unavailable(self):
        sys.modules["pypdfium2"] = None  # type: ignore[assignment]
        try:
            mod = self._load_overlay()
            self.assertIsNone(mod.rasterise_first_page("/nonexistent.pdf"))
        finally:
            del sys.modules["pypdfium2"]

    def test_returns_none_for_missing_file(self):
        mod = self._load_overlay()
        self.assertIsNone(mod.rasterise_first_page("/this/does/not/exist.pdf"))


if __name__ == "__main__":
    unittest.main()
