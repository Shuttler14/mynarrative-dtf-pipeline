"""
Background Remover - DTF Print Preparation
==========================================
Removes background from design images using rembg library.
Uses U2NET model for high-quality segmentation.
Returns RGBA image with transparent background.

Requirements:
- rembg package
- u2net model (auto-downloaded on first use)

Author: Claude Code
"""

import io
from typing import Optional
from PIL import Image
import numpy as np

# Try to import rembg, fallback to basic method if not available
try:
    from rembg import remove
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False
    print("Warning: rembg not installed. Using basic background removal.")


class BackgroundRemover:
    """
    Remove background from design images for DTF printing
    """

    def __init__(self):
        self.alpha_matting = True
        self.alpha_matting_foreground_threshold = 240
        self.alpha_matting_background_threshold = 10
        self.alpha_matting_erode_size = 10

    async def remove_background(
        self,
        image_bytes: bytes,
        alpha_matting: bool = True
    ) -> bytes:
        """
        Remove background from image.

        Args:
            image_bytes: Input image as bytes (PNG/JPG)
            alpha_matting: Enable edge refinement for cleaner edges

        Returns:
            Image with transparent background as PNG bytes
        """
        if REMBG_AVAILABLE:
            return await self._remove_with_rembg(image_bytes, alpha_matting)
        else:
            return await self._remove_basic(image_bytes)

    async def _remove_with_rembg(
        self,
        image_bytes: bytes,
        alpha_matting: bool
    ) -> bytes:
        """
        Remove background using rembg library
        """
        try:
            output_bytes = remove(
                image_bytes,
                alpha_matting=alpha_matting,
                alpha_matting_foreground_threshold=self.alpha_matting_foreground_threshold,
                alpha_matting_background_threshold=self.alpha_matting_background_threshold,
                alpha_matting_erode_size=self.alpha_matting_erode_size
            )

            # Verify output is RGBA
            img = Image.open(io.BytesIO(output_bytes))
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            output = io.BytesIO()
            img.save(output, format='PNG')
            return output.getvalue()

        except Exception as e:
            print(f"rembg failed: {e}, falling back to basic method")
            return await self._remove_basic(image_bytes)

    async def _remove_basic(self, image_bytes: bytes) -> bytes:
        """
        Basic background removal using simple threshold
        This is a fallback when rembg is not available
        """
        img = Image.open(io.BytesIO(image_bytes))

        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Get pixel data
        pixels = img.load()
        width, height = img.size

        # Simple white/transparent background detection
        # This is very basic - works for white backgrounds only
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]

                # If pixel is nearly white, make it transparent
                if r > 245 and g > 245 and b > 245 and a > 200:
                    pixels[x, y] = (r, g, b, 0)

        output = io.BytesIO()
        img.save(output, format='PNG')
        return output.getvalue()

    async def remove_background_with_mask(
        self,
        image_bytes: bytes,
        mask_bytes: bytes
    ) -> bytes:
        """
        Remove background using a pre-generated mask

        Args:
            image_bytes: Original image
            mask_bytes: Alpha mask as bytes
        """
        img = Image.open(io.BytesIO(image_bytes))
        mask = Image.open(io.BytesIO(mask_bytes)).convert('L')

        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        img.putalpha(mask)

        output = io.BytesIO()
        img.save(output, format='PNG')
        return output.getvalue()

    def validate_transparency(self, image_bytes: bytes) -> dict:
        """
        Validate that image has proper transparency for DTF
        """
        img = Image.open(io.BytesIO(image_bytes))

        if img.mode != 'RGBA':
            return {
                "valid": False,
                "reason": "Image is not RGBA"
            }

        # Check for transparent pixels
        pixels = np.array(img)
        alpha_channel = pixels[:, :, 3]

        transparent_pixels = np.sum(alpha_channel == 0)
        opaque_pixels = np.sum(alpha_channel > 0)
        total_pixels = alpha_channel.size

        transparency_ratio = transparent_pixels / total_pixels

        return {
            "valid": True,
            "transparent_pixels": int(transparent_pixels),
            "opaque_pixels": int(opaque_pixels),
            "transparency_ratio": float(transparency_ratio),
            "has_transparency": transparent_pixels > 0
        }


# Test function
if __name__ == "__main__":
    import asyncio

    async def test():
        from PIL import Image

        # Create test image with white background
        img = Image.new('RGBA', (500, 500), (255, 255, 255, 255))
        # Draw a red circle
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.ellipse([100, 100, 400, 400], fill=(255, 0, 0, 255))

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        test_bytes = buffer.getvalue()

        remover = BackgroundRemover()
        result = await remover.remove_background(test_bytes)

        print(f"Result size: {len(result)} bytes")
        validation = remover.validate_transparency(result)
        print(f"Validation: {validation}")

    asyncio.run(test())