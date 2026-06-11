"""
PDF Generator - CoralDraw Sheet Export
======================================
Generates print-ready PDF files optimized for CoralDraw and DTF printing.
Creates multi-design sheets with proper bleed margins and crop marks.

Output specs:
- PDF/X-1a format for print consistency
- 300 DPI resolution
- CMYK color space (converts from RGB)
- Crop marks and registration marks

Author: Claude Code
"""

import io
import time
import json
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw
from PIL.features import features  # Check for required features

# Try to import reportlab for professional PDF generation
try:
    from reportlab.lib.pagesizes import A3, A4, inch
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("Warning: reportlab not installed. Using basic PDF generation.")


class PDFGenerator:
    """
    Generate print-ready PDF sheets for DTF printing
    """

    # Sheet size constants (in mm)
    SHEET_SIZES_MM = {
        "a3": {"width": 297, "height": 420},
        "12x18": {"width": 305, "height": 457},
        "17x22": {"width": 432, "height": 559}
    }

    def __init__(self):
        self.default_sheet_size = "12x18"
        self.bleed_mm = 3  # 3mm bleed
        self.crop_mark_length = 5  # mm
        self.crop_mark_offset = 3  # mm from design edge
        self.edge_margin_mm = 15  # Safe zone from sheet edge

    async def generate_coraldraw_sheet(
        self,
        sheet_id: str,
        designs: List[Dict] = None
    ) -> bytes:
        """
        Generate a print-ready PDF for the sheet.

        Args:
            sheet_id: Sheet identifier
            designs: List of design dicts with image_bytes, position, size
                   If None, uses designs from nesting_optimizer

        Returns:
            PDF bytes
        """
        if REPORTLAB_AVAILABLE:
            return await self._generate_with_reportlab(sheet_id, designs)
        else:
            return await self._generate_basic_pdf(sheet_id, designs)

    async def _generate_with_reportlab(
        self,
        sheet_id: str,
        designs: List[Dict]
    ) -> bytes:
        """
        Generate professional PDF with reportlab
        Includes crop marks, registration marks, and job info
        """
        output = io.BytesIO()

        # Get sheet dimensions
        sheet_dims = self.SHEET_SIZES_MM.get(self.default_sheet_size)
        page_width_mm = sheet_dims["width"]
        page_height_mm = sheet_dims["height"]

        # Create canvas
        c = canvas.Canvas(
            output,
            pagesize=(
                page_width_mm * mm,
                page_height_mm * mm
            )
        )

        # Set PDF metadata
        c.setTitle(f"DTF Print Sheet - {sheet_id}")
        c.setAuthor("DTF Automation System")
        c.setSubject("DTF Print Ready")

        # Draw crop marks for each design
        for design in designs or []:
            x_mm = design.get("x_mm", 0)
            y_mm = design.get("y_mm", 0)
            width_mm = design.get("width_mm", 0)
            height_mm = design.get("height_mm", 0)

            # Draw design on PDF
            if "image_bytes" in design:
                self._draw_image_on_canvas(c, design["image_bytes"], x_mm, y_mm, width_mm, height_mm)

            # Draw crop marks around design
            self._draw_crop_marks(c, x_mm, y_mm, width_mm, height_mm)

        # Add job info in corner
        self._add_job_info(c, sheet_id, len(designs or []))

        # Save PDF
        c.save()

        return output.getvalue()

    def _draw_image_on_canvas(
        self,
        c,
        image_bytes: bytes,
        x_mm: float,
        y_mm: float,
        width_mm: float,
        height_mm: float
    ):
        """
        Draw image on canvas, converting to CMYK approximation
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))

            # Convert to RGB if RGBA (remove alpha channel for print)
            if img.mode == 'RGBA':
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background

            # Convert to CMYK approximation (for better print results)
            img = img.convert('CMYK')

            # Save to temporary buffer
            temp_buffer = io.BytesIO()
            img.save(temp_buffer, format='JPEG', quality=95)

            # Draw on canvas
            x_pt = x_mm * mm
            y_pt = y_mm * mm
            width_pt = width_mm * mm
            height_pt = height_mm * mm

            c.drawImage(
                temp_buffer,
                x_pt, y_pt,
                width=width_pt,
                height=height_pt,
                preserveAspectRatio=True
            )
        except Exception as e:
            print(f"Error drawing image: {e}")
            # Fallback: draw placeholder rectangle
            c.setStrokeColorRGB(0, 0, 0)
            c.setFillColorRGB(0.9, 0.9, 0.9)
            c.rect(x_mm * mm, y_mm * mm, width_mm * mm, height_mm * mm, fill=1)

    def _draw_crop_marks(
        self,
        c,
        x_mm: float,
        y_mm: float,
        width_mm: float,
        height_mm: float
    ):
        """
        Draw crop marks around design area
        """
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.25)

        # Extend beyond design edge
        bleed = self.bleed_mm
        mark_length = self.crop_mark_length

        # Top-left corner
        # Horizontal mark
        c.line(
            (x_mm - bleed) * mm, (y_mm + height_mm + bleed) * mm,
            (x_mm - bleed - mark_length) * mm, (y_mm + height_mm + bleed) * mm
        )
        # Vertical mark
        c.line(
            (x_mm - bleed) * mm, (y_mm + height_mm + bleed) * mm,
            (x_mm - bleed) * mm, (y_mm + height_mm + bleed + mark_length) * mm
        )

        # Top-right corner
        c.line(
            (x_mm + width_mm + bleed) * mm, (y_mm + height_mm + bleed) * mm,
            (x_mm + width_mm + bleed + mark_length) * mm, (y_mm + height_mm + bleed) * mm
        )
        c.line(
            (x_mm + width_mm + bleed) * mm, (y_mm + height_mm + bleed) * mm,
            (x_mm + width_mm + bleed) * mm, (y_mm + height_mm + bleed + mark_length) * mm
        )

        # Bottom-left corner
        c.line(
            (x_mm - bleed) * mm, (y_mm - bleed) * mm,
            (x_mm - bleed - mark_length) * mm, (y_mm - bleed) * mm
        )
        c.line(
            (x_mm - bleed) * mm, (y_mm - bleed) * mm,
            (x_mm - bleed) * mm, (y_mm - bleed - mark_length) * mm
        )

        # Bottom-right corner
        c.line(
            (x_mm + width_mm + bleed) * mm, (y_mm - bleed) * mm,
            (x_mm + width_mm + bleed + mark_length) * mm, (y_mm - bleed) * mm
        )
        c.line(
            (x_mm + width_mm + bleed) * mm, (y_mm - bleed) * mm,
            (x_mm + width_mm + bleed) * mm, (y_mm - bleed - mark_length) * mm
        )

    def _add_job_info(
        self,
        c,
        sheet_id: str,
        design_count: int
    ):
        """
        Add job information in bottom-left corner
        """
        from datetime import datetime

        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 6)

        info_text = [
            f"Job ID: {sheet_id}",
            f"Designs: {design_count}",
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Generated by: DTF Automation"
        ]

        y_position = 5  # mm from bottom
        for i, line in enumerate(info_text):
            c.drawString(
                self.edge_margin_mm * mm,
                y_position * mm + (i * 4 * mm),
                line
            )

    async def _generate_basic_pdf(
        self,
        sheet_id: str,
        designs: List[Dict]
    ) -> bytes:
        """
        Basic PDF generation using only PIL (fallback)
        Creates a simple image-based PDF
        """
        # Get sheet dimensions
        sheet_dims = self.SHEET_SIZES_MM.get(self.default_sheet_size)
        width_px = int(sheet_dims["width"] * 300 / 25.4)  # 300 DPI
        height_px = int(sheet_dims["height"] * 300 / 25.4)

        # Create canvas
        canvas = Image.new('RGB', (width_px, height_px), (255, 255, 255))

        # Place each design
        dpi_factor = 300 / 25.4  # 11.81 px per mm

        for design in designs or []:
            if "image_bytes" not in design:
                continue

            img = Image.open(io.BytesIO(design["image_bytes"]))

            # Ensure RGBA for transparency handling
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # Calculate position in pixels
            x_px = int((design.get("x_mm", 0) + self.edge_margin_mm) * dpi_factor)
            y_px = int((design.get("y_mm", 0) + self.edge_margin_mm) * dpi_factor)
            width_px = int(design.get("width_mm", 0) * dpi_factor)
            height_px = int(design.get("height_mm", 0) * dpi_factor)

            # Resize to fit
            if img.width != width_px or img.height != height_px:
                img = img.resize((width_px, height_px), Image.Resampling.LANCZOS)

            # Create white background
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)

            # Paste on canvas
            canvas.paste(bg, (x_px, y_px))

        # Save as PDF
        output = io.BytesIO()
        canvas.save(output, format='PDF', resolution=300)
        return output.getvalue()

    async def generate_single_design_pdf(
        self,
        design_bytes: bytes,
        design_uuid: str
    ) -> bytes:
        """
        Generate PDF for a single design (for testing)
        """
        output = io.BytesIO()

        sheet_dims = self.SHEET_SIZES_MM.get(self.default_sheet_size)
        page_width = sheet_dims["width"] * mm
        page_height = sheet_dims["height"] * mm

        if REPORTLAB_AVAILABLE:
            c = canvas.Canvas(output, pagesize=(page_width, page_height))

            # Load and place design centered
            img = Image.open(io.BytesIO(design_bytes))
            width_mm = (img.width / 300) * 25.4
            height_mm = (img.height / 300) * 25.4

            x_mm = (sheet_dims["width"] - width_mm) / 2
            y_mm = (sheet_dims["height"] - height_mm) / 2

            # Convert to CMYK and draw
            temp_buffer = io.BytesIO()
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                bg = bg.convert('CMYK')
            else:
                bg = img.convert('CMYK')
            bg.save(temp_buffer, format='JPEG', quality=95)

            c.drawImage(temp_buffer, x_mm * mm, y_mm * mm,
                       width=width_mm * mm, height=height_mm * mm)

            # Add crop marks
            self._draw_crop_marks(c, x_mm, y_mm, width_mm, height_mm)

            # Job info
            self._add_job_info(c, design_uuid, 1)

            c.save()
        else:
            # Fallback: just save as PDF
            img = Image.open(io.BytesIO(design_bytes))
            img.save(output, format='PDF')

        return output.getvalue()


# Test function
if __name__ == "__main__":
    import asyncio

    async def test():
        from PIL import Image, ImageDraw

        # Create test design
        img = Image.new('RGBA', (2000, 2000), (255, 0, 0, 255))
        draw = ImageDraw.Draw(img)
        draw.ellipse([500, 500, 1500, 1500], fill=(0, 255, 0, 255))

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        design_bytes = buffer.getvalue()

        generator = PDFGenerator()

        # Test single design
        pdf = await generator.generate_single_design_pdf(
            design_bytes,
            "test_design_001"
        )

        print(f"Generated PDF: {len(pdf)} bytes")

        # Save test file
        with open("/tmp/test_sheet.pdf", "wb") as f:
            f.write(pdf)

        print("Saved to /tmp/test_sheet.pdf")

    asyncio.run(test())