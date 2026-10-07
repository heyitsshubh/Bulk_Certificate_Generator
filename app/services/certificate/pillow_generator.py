"""
Concrete certificate generator — Strategy implementation using Pillow + ReportLab.

Design:
- Implements AbstractCertificateGenerator (Strategy Pattern).
- All rendering is private (_draw_*) — only generate() is public
  (Interface Segregation; callers only need the one contract method).
- Font loading uses a priority-ordered fallback chain so the generator
  works on Windows, macOS, and Linux without additional setup.
- The certificate is rendered entirely in-memory as a PIL Image, then
  wrapped in a PDF by ReportLab — no temporary files on disk.

Certificate layout (A4 landscape at 150 DPI = 1754 × 1240 px):
  ┌────────────────────────────────────────────────────┐
  │           CERTIFICATE OF ACHIEVEMENT               │
  │         ─────────────────────────────              │
  │           This is to certify that                  │
  │                                                    │
  │              [RECIPIENT NAME]                      │
  │                                                    │
  │      has successfully completed the course         │
  │                                                    │
  │              [EVENT NAME]                          │
  │                                                    │
  │   Date: [TODAY]          Issued by: [ISSUER]       │
  └────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from app.services.certificate.base import AbstractCertificateGenerator
from app.services.certificate.data import CertificateData

# ---------------------------------------------------------------------------
# Layout constants (pixels, A4 landscape @ 150 DPI)
# ---------------------------------------------------------------------------

_W = 1754   # canvas width
_H = 1240   # canvas height

# Colour palette
_BG         = (255, 254, 245)   # warm cream
_NAVY       = (22,  54,  100)   # deep navy
_GOLD       = (197, 158,  36)   # warm gold
_DARK_GRAY  = (55,  55,   55)
_LIGHT_GRAY = (140, 140, 140)

# Proportional margins for the outer / inner border rectangles
_OUTER_MARGIN = 28
_INNER_MARGIN = 48


# ---------------------------------------------------------------------------
# Font helper (platform-aware fallback chain)
# ---------------------------------------------------------------------------

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Attempt to load a TrueType font from common system paths.
    Falls back gracefully to PIL's built-in bitmap font.
    """
    candidates: list[str] = []

    if sys.platform == "win32":
        candidates = [
            r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
            r"C:\Windows\Fonts\arialbd.ttf"  if bold else r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\georgia.ttf",
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Library/Fonts/Arial Bold.ttf"    if bold else "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Georgia.ttf",
        ]
    else:  # Linux / Docker
        candidates = [
            f"/usr/share/fonts/truetype/dejavu/DejaVuSans-{'Bold' if bold else ''}.ttf",
            f"/usr/share/fonts/truetype/liberation/LiberationSans-{'Bold-' if bold else 'Regular-'}Italic.ttf",
            f"/usr/share/fonts/truetype/freefont/FreeSans{'Bold' if bold else ''}.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

    # Optionally check for a bundled font placed alongside this module
    module_dir = Path(__file__).parent.parent.parent / "templates" / "fonts"
    bundled_candidates = [
        str(module_dir / ("RobotoCondensed-Bold.ttf" if bold else "RobotoCondensed-Regular.ttf")),
        str(module_dir / "Roboto-Bold.ttf"),
        str(module_dir / "Roboto-Regular.ttf"),
    ]

    for path in bundled_candidates + candidates:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue

    # PIL built-in fallback (no external file needed)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Concrete Strategy
# ---------------------------------------------------------------------------

class PillowReportLabGenerator(AbstractCertificateGenerator):
    """
    Generates a certificate as a PIL image, then wraps it in a PDF with
    ReportLab.  All intermediate data is kept in memory (io.BytesIO).
    """

    # Pre-load font sizes as class-level constants for efficiency
    _FONT_SIZES = {
        "title":      72,
        "subtitle":   36,
        "body":       38,
        "name":       80,
        "event":      52,
        "footer":     32,
    }

    # ------------------------------------------------------------------
    # Public interface (AbstractCertificateGenerator contract)
    # ------------------------------------------------------------------

    def generate(self, data: CertificateData, output_path: Path) -> Path:
        """Render the certificate and write it as a PDF at output_path."""
        img = self._render_image(data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._save_as_pdf(img, output_path)
        return output_path.resolve()

    # ------------------------------------------------------------------
    # Private rendering pipeline
    # ------------------------------------------------------------------

    def _render_image(self, data: CertificateData) -> Image.Image:
        """Build the certificate image layer by layer."""
        img = Image.new("RGB", (_W, _H), color=_BG)
        draw = ImageDraw.Draw(img)

        self._draw_borders(draw)
        self._draw_corner_ornaments(draw)
        self._draw_title(draw)
        self._draw_divider(draw, y=260, width=900)
        self._draw_preamble(draw)
        self._draw_recipient_name(draw, data.recipient_name)
        self._draw_completion_text(draw)
        self._draw_event_name(draw, data.event_name)
        self._draw_divider(draw, y=960, width=700)
        self._draw_footer(draw, data)

        return img

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_borders(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw the outer (navy) and inner (gold) rectangular borders."""
        m = _OUTER_MARGIN
        draw.rectangle(
            [m, m, _W - m, _H - m],
            outline=_NAVY, width=6,
        )
        m = _INNER_MARGIN
        draw.rectangle(
            [m, m, _W - m, _H - m],
            outline=_GOLD, width=3,
        )

    def _draw_corner_ornaments(self, draw: ImageDraw.ImageDraw) -> None:
        """Place a small filled gold diamond at each inner corner."""
        r = 12  # ornament radius
        corners = [
            (_INNER_MARGIN, _INNER_MARGIN),
            (_W - _INNER_MARGIN, _INNER_MARGIN),
            (_INNER_MARGIN, _H - _INNER_MARGIN),
            (_W - _INNER_MARGIN, _H - _INNER_MARGIN),
        ]
        for cx, cy in corners:
            draw.polygon(
                [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                fill=_GOLD,
            )

    def _draw_title(self, draw: ImageDraw.ImageDraw) -> None:
        """Render the bold certificate heading."""
        font = _load_font(self._FONT_SIZES["title"], bold=True)
        text = "CERTIFICATE OF ACHIEVEMENT"
        self._draw_centered_text(draw, text, y=120, font=font, fill=_NAVY)

    def _draw_divider(
        self,
        draw: ImageDraw.ImageDraw,
        y: int,
        width: int,
    ) -> None:
        """Draw a short decorative horizontal rule."""
        cx = _W // 2
        half = width // 2
        # Central gold line
        draw.line([(cx - half, y), (cx + half, y)], fill=_GOLD, width=2)
        # Small diamond accent in the centre
        r = 6
        draw.polygon(
            [(cx, y - r), (cx + r, y), (cx, y + r), (cx - r, y)],
            fill=_GOLD,
        )

    def _draw_preamble(self, draw: ImageDraw.ImageDraw) -> None:
        font = _load_font(self._FONT_SIZES["subtitle"])
        self._draw_centered_text(
            draw, "This is to certify that", y=310, font=font, fill=_DARK_GRAY
        )

    def _draw_recipient_name(
        self, draw: ImageDraw.ImageDraw, name: str
    ) -> None:
        """Render the recipient's name prominently."""
        font = _load_font(self._FONT_SIZES["name"], bold=True)
        self._draw_centered_text(draw, name, y=420, font=font, fill=_NAVY)

        # Underline beneath the name
        try:
            bbox = font.getbbox(name)
            text_w = bbox[2] - bbox[0]
        except AttributeError:
            text_w = len(name) * (self._FONT_SIZES["name"] // 2)
        cx = _W // 2
        y_line = 420 + self._FONT_SIZES["name"] + 12
        draw.line(
            [(cx - text_w // 2, y_line), (cx + text_w // 2, y_line)],
            fill=_GOLD, width=2,
        )

    def _draw_completion_text(self, draw: ImageDraw.ImageDraw) -> None:
        font = _load_font(self._FONT_SIZES["body"])
        self._draw_centered_text(
            draw,
            "has successfully completed the course",
            y=630,
            font=font,
            fill=_DARK_GRAY,
        )

    def _draw_event_name(
        self, draw: ImageDraw.ImageDraw, event_name: str
    ) -> None:
        font = _load_font(self._FONT_SIZES["event"], bold=True)
        self._draw_centered_text(
            draw, event_name, y=710, font=font, fill=_NAVY
        )

    def _draw_footer(
        self, draw: ImageDraw.ImageDraw, data: CertificateData
    ) -> None:
        """Render date (left) and issuer (right) in the footer zone."""
        font = _load_font(self._FONT_SIZES["footer"])
        margin = 140

        date_str = data.date.strftime("%B %d, %Y")
        draw.text((margin, 1020), f"Date:  {date_str}", font=font, fill=_DARK_GRAY)
        draw.text((margin, 1060), f"Issued by:  {data.issuer}", font=font, fill=_DARK_GRAY)

        # Decorative signature line on the right
        sig_x = _W - 360
        draw.line([(sig_x, 1060), (sig_x + 280, 1060)], fill=_LIGHT_GRAY, width=1)
        draw.text((sig_x + 60, 1065), "Authorised Signatory", font=font, fill=_LIGHT_GRAY)

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_centered_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        y: int,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        fill: tuple[int, int, int],
    ) -> None:
        """Draw text horizontally centred on the canvas."""
        try:
            bbox = font.getbbox(text)
            text_w = bbox[2] - bbox[0]
        except AttributeError:
            # Older Pillow fallback
            text_w = draw.textlength(text, font=font)
        x = (_W - text_w) // 2
        draw.text((x, y), text, font=font, fill=fill)

    @staticmethod
    def _save_as_pdf(img: Image.Image, output_path: Path) -> None:
        """
        Embed the PIL image into a PDF page using ReportLab.
        The image is piped through an in-memory BytesIO buffer — no
        temporary files are created on disk.
        """
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="PNG", optimize=True)
        img_buffer.seek(0)

        # Page size matches the image (landscape A4 in points ≈ 841.9 × 595.3)
        # We use pixel dimensions directly so the image fills the page exactly.
        pdf = rl_canvas.Canvas(str(output_path), pagesize=(img.width, img.height))
        img_reader = ImageReader(img_buffer)
        pdf.drawImage(img_reader, 0, 0, width=img.width, height=img.height)
        pdf.save()
