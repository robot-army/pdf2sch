"""
Rasterise a PDF page to a PNG file so it can be embedded as a SCH_BITMAP
background overlay in KiCad 9.

Requires ``pypdfium2`` (``pip install pypdfium2``).  If it is not available the
function returns ``None`` and the caller skips the overlay silently.
"""

from __future__ import annotations

import os
import tempfile


def rasterise_first_page(pdf_path: str, dpi: int = 150) -> str | None:
    """Rasterise the first page of *pdf_path* at *dpi* and return the PNG path.

    The PNG is written to a temporary directory whose lifetime is managed by the
    caller.  Returns ``None`` if pypdfium2 is not installed or the PDF cannot be
    opened.
    """
    try:
        import pypdfium2 as pdfium  # type: ignore[import]
    except ImportError:
        return None

    try:
        doc = pdfium.PdfDocument(pdf_path)
    except Exception:  # noqa: BLE001
        return None

    try:
        page = doc[0]
        scale = dpi / 72.0  # pypdfium2 default is 72 DPI
        bitmap = page.render(scale=scale, rotation=0)
        pil_image = bitmap.to_pil()
        out_dir = tempfile.mkdtemp(prefix="pdf2sch_overlay_")
        out_path = os.path.join(out_dir, "overlay_page1.png")
        pil_image.save(out_path, "PNG")
        return out_path
    except Exception:  # noqa: BLE001
        return None
    finally:
        doc.close()
