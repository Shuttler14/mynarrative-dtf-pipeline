"""
Image Upscaler - Print Quality Enhancement
==========================================
Upscales images to meet DTF print requirements:
- Minimum 300 DPI
- Minimum 3000x3000px for A3 print
- Applies sharpening for print quality

Uses Pillow with LANCZOS resampling for quality upscaling.
For better results, can integrate with Real-ESRGAN API.

Author: Claude Code
"""

import io
from typing import Tuple, Optional
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np


class ImageUpscaler:
    """
    Upscale images to print-ready resolution
    """

    def __init__(self):
        # DTF Print requirements
        self.target_dpi = 300
        self.min_width = 3000
        self.min_height = 3000
        # A3 size at 300 DPI: 3508 x 4961 pixels
        self.a3_width = 3508
        self.a3_height = 4961

    async def upscale(
        self,
        image_bytes: bytes,
        target_dpi: int = 300,
        min_width: int = 3000,
        min_height: int = 3000
    ) -> bytes:
        """
        Upscale image to meet print requirements.

        Args:
            image_bytes: Input image as bytes
            target_dpi: Target DPI (default 300)
            min_width: Minimum width in pixels
            min_height: Minimum height in pixels

        Returns:
            Upscaled image as bytes (PNG)
        """
        # Load image
        image = Image.open(io.BytesIO(image_bytes))

        # Convert to RGBA if needed
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        current_width, current_height = image.size

        # Calculate upscale factor
        width_factor = max(1, min_width / current_width)
        height_factor = max(1, min_height / current_height)
        upscale_factor = max(width_factor, height_factor)

        if upscale_factor > 1:
            # Use LANCZOS for high-quality upscaling
            new_size = (
                int(current_width * upscale_factor),
                int(current_height * upscale_factor)
            )
            image = image.resize(new_size, Image.Resampling.LANCZOS)

            # Apply sharpening after upscaling
            image = self._sharpen_for_print(image)

        # Ensure dimensions are even (required for some printers)
        width, height = image.size
        if width % 2 != 0:
            image = image.crop((0, 0, width-1, height))
        if height % 2 != 0:
            image = image.crop((0, 0, width, height-1))

        # Save as PNG
        output = io.BytesIO()
        image.save(output, format='PNG', optimize=False)
        return output.getvalue()

    def _sharpen_for_print(self, image: Image.Image) -> Image.Image:
        """
        Apply sharpening filter for print-quality output
        """
        # Apply unsharp mask for crisp edges
        enhancer = ImageEnhance.Sharpness(image)
        sharpened = enhancer.enhance(1.5)

        # Optional: Apply slight contrast boost
        contrast = ImageEnhance.Contrast(sharpened)
        result = contrast.enhance(1.1)

        return result

    def calculate_required_size(
        self,
        print_width_cm: float,
        print_height_cm: float,
        dpi: int = 300
    ) -> Tuple[int, int]:
        """
        Calculate required pixel dimensions for print size.

        Args:
            print_width_cm: Print width in centimeters
            print_height_cm: Print height in centimeters
            dpi: Target DPI

        Returns:
            (width, height) in pixels
        """
        # 1 inch = 2.54 cm
        width_inches = print_width_cm / 2.54
        height_inches = print_height_cm / 2.54

        return (
            int(width_inches * dpi),
            int(height_inches * dpi)
        )

    async def fit_to_a3_sheet(
        self,
        image_bytes: bytes,
        margin_mm: int = 15
    ) -> bytes:
        """
        Fit image to A3 sheet with margin.
        Used for single design PDF generation.
        """
        image = Image.open(io.BytesIO(image_bytes))

        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # A3 at 300 DPI
        a3_width = 3508
        a3_height = 4961

        # Apply margin (15mm = ~177px at 300 DPI)
        margin_px = int(margin_mm * 300 / 25.4)
        usable_width = a3_width - (2 * margin_px)
        usable_height = a3_height - (2 * margin_px)

        # Calculate scale to fit
        width_scale = usable_width / image.width
        height_scale = usable_height / image.height
        scale = min(width_scale, height_scale, 1.0)

        if scale < 1:
            new_size = (
                int(image.width * scale),
                int(image.height * scale)
            )
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            image = self._sharpen_for_print(image)

        # Create A3 canvas
        canvas = Image.new('RGBA', (a3_width, a3_height), (255, 255, 255, 255))

        # Center the image
        x_offset = (a3_width - image.width) // 2
        y_offset = (a3_height - image.height) // 2
        canvas.paste(image, (x_offset, y_offset), image)

        output = io.BytesIO()
        canvas.save(output, format='PNG')
        return output.getvalue()


# Test function
if __name__ == "__main__":
    import asyncio

    async def test():
        from PIL import Image

        # Create test image
        img = Image.new('RGBA', (500, 500), (255, 0, 0, 255))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        test_bytes = buffer.getvalue()

        upscaler = ImageUpscaler()
        result = await upscaler.upscale(test_bytes)

        print(f"Upscaled size: {len(result)} bytes")
        result_img = Image.open(io.BytesIO(result))
        print(f"Dimensions: {result_img.size}")

    asyncio.run(test())