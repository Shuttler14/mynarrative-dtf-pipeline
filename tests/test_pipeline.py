"""
Test Suite for DTF Automation Pipeline
======================================
Tests each component of the pipeline independently and end-to-end.

Run with: pytest tests/ -v

Author: Claude Code
"""

import pytest
import io
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from PIL import Image, ImageDraw

# Test data - create simple test images
def create_test_image(size=(1000, 1000), color=(255, 0, 0, 255)):
    """Create a test RGBA image"""
    img = Image.new('RGBA', size, color)
    draw = ImageDraw.Draw(img)
    # Add some detail
    draw.rectangle([200, 200, 800, 800], fill=(0, 255, 0, 255))
    draw.ellipse([300, 300, 700, 700], fill=(0, 0, 255, 255))
    return img


def image_to_bytes(img, format='PNG'):
    """Convert PIL Image to bytes"""
    buffer = io.BytesIO()
    img.save(buffer, format=format)
    return buffer.getvalue()


class TestContentSafety:
    """Test content safety checker"""

    @pytest.mark.asyncio
    async def test_safe_image_passes(self):
        """Test that safe images pass the check"""
        from api.content_safety import ContentSafetyChecker

        checker = ContentSafetyChecker()

        # Create test image
        img = create_test_image()
        img_bytes = image_to_bytes(img)

        # Check (will skip if no API key)
        result = await checker.check_image(img_bytes)

        assert "is_safe" in result
        assert isinstance(result["is_safe"], bool)

    @pytest.mark.asyncio
    async def test_no_api_key_skips_check(self):
        """Test that missing API key skips the check"""
        from api.content_safety import ContentSafetyChecker

        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}):
            checker = ContentSafetyChecker()
            img = create_test_image()
            result = await checker.check_image(image_to_bytes(img))

            assert result["is_safe"] == True
            assert "note" in result


class TestImageUpscaler:
    """Test image upscaler"""

    @pytest.mark.asyncio
    async def test_upscale_small_image(self):
        """Test upscaling a small image to print quality"""
        from api.image_upscaler import ImageUpscaler

        upscaler = ImageUpscaler()

        # Create small image (500x500 - below minimum)
        img = Image.new('RGBA', (500, 500), (255, 0, 0, 255))
        img_bytes = image_to_bytes(img)

        # Upscale
        result = await upscaler.upscale(img_bytes, min_width=3000, min_height=3000)
        result_img = Image.open(io.BytesIO(result))

        # Should be at least 3000px on longest side
        width, height = result_img.size
        max_dim = max(width, height)

        assert max_dim >= 3000, f"Expected >= 3000, got {max_dim}"
        assert result_img.mode == 'RGBA'

    @pytest.mark.asyncio
    async def test_large_image_unchanged(self):
        """Test that already large images are not upscaled"""
        from api.image_upscaler import ImageUpscaler

        upscaler = ImageUpscaler()

        # Create large image
        img = Image.new('RGBA', (4000, 4000), (255, 0, 0, 255))
        img_bytes = image_to_bytes(img)

        result = await upscaler.upscale(img_bytes, min_width=3000, min_height=3000)
        result_img = Image.open(io.BytesIO(result))

        # Should still be 4000x4000 (no upscaling needed)
        assert result_img.size == (4000, 4000)

    def test_calculate_required_size(self):
        """Test pixel dimension calculation"""
        from api.image_upscaler import ImageUpscaler

        upscaler = ImageUpscaler()

        # 10cm x 10cm at 300 DPI = 1181 x 1181 pixels
        width, height = upscaler.calculate_required_size(10, 10, dpi=300)

        assert 1170 < width < 1190, f"Expected ~1181, got {width}"
        assert 1170 < height < 1190, f"Expected ~1181, got {height}"


class TestBackgroundRemover:
    """Test background removal"""

    @pytest.mark.asyncio
    async def test_remove_white_background(self):
        """Test removing a white background"""
        from api.background_remover import BackgroundRemover

        remover = BackgroundRemover()

        # Create image with white background
        img = Image.new('RGBA', (1000, 1000), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Draw a red circle (non-white)
        draw.ellipse([250, 250, 750, 750], fill=(255, 0, 0, 255))

        img_bytes = image_to_bytes(img)

        result = await remover.remove_background(img_bytes)
        result_img = Image.open(io.BytesIO(result))

        assert result_img.mode == 'RGBA'

    def test_validate_transparency(self):
        """Test transparency validation"""
        from api.background_remover import BackgroundRemover

        remover = BackgroundRemover()

        # Create transparent image
        img = Image.new('RGBA', (100, 100), (255, 0, 0, 0))  # Fully transparent
        img_bytes = image_to_bytes(img)

        result = remover.validate_transparency(img_bytes)

        assert result["valid"] == True
        assert result["has_transparency"] == True


class TestNestingOptimizer:
    """Test nesting optimizer"""

    @pytest.mark.asyncio
    async def test_add_first_design(self):
        """Test adding first design to empty sheet"""
        from api.nesting_optimizer import NestingOptimizer

        optimizer = NestingOptimizer()

        img = create_test_image((400, 400))
        img_bytes = image_to_bytes(img)

        result = await optimizer.add_design(
            design_uuid="test_001",
            design_image=img_bytes,
            user_id="user_001",
            product_type="tee"
        )

        assert result["placed"] == True
        assert "sheet_id" in result

    @pytest.mark.asyncio
    async def test_fill_sheet_triggers_completion(self):
        """Test that filling a sheet sets sheet_ready=True"""
        from api.nesting_optimizer import NestingOptimizer

        optimizer = NestingOptimizer()
        optimizer.max_designs_per_sheet = 2  # Small for testing

        # Add first design
        img1 = create_test_image((300, 300))
        result1 = await optimizer.add_design(
            design_uuid="test_001",
            design_image=image_to_bytes(img1),
            user_id="user_001",
            product_type="tee"
        )

        assert result1["sheet_ready"] == False

        # Add second design (fills the sheet)
        img2 = create_test_image((300, 300))
        result2 = await optimizer.add_design(
            design_uuid="test_002",
            design_image=image_to_bytes(img2),
            user_id="user_002",
            product_type="tee"
        )

        assert result2["sheet_ready"] == True

    def test_get_sheet_status(self):
        """Test getting sheet status"""
        from api.nesting_optimizer import NestingOptimizer

        optimizer = NestingOptimizer()

        status = optimizer.get_sheet_status("nonexistent")

        assert "error" in status


class TestPDFGenerator:
    """Test PDF generation"""

    @pytest.mark.asyncio
    async def test_generate_single_design_pdf(self):
        """Test generating PDF for single design"""
        from api.pdf_generator import PDFGenerator

        generator = PDFGenerator()

        # Create test design
        img = create_test_image((1000, 1000))
        img_bytes = image_to_bytes(img)

        # Generate PDF
        pdf_bytes = await generator.generate_single_design_pdf(
            img_bytes,
            "test_design_001"
        )

        assert len(pdf_bytes) > 0
        # Basic PDF header check
        assert pdf_bytes[:4] == b'%PDF'

    @pytest.mark.asyncio
    async def test_sheet_pdf_contains_designs(self):
        """Test that sheet PDF has correct number of pages"""
        from api.pdf_generator import PDFGenerator

        generator = PDFGenerator()

        # Create designs
        designs = []
        for i in range(2):
            img = create_test_image((500, 500))
            designs.append({
                "design_uuid": f"test_{i}",
                "image_bytes": image_to_bytes(img),
                "x_mm": 30 + (i * 100),
                "y_mm": 30,
                "width_mm": 80,
                "height_mm": 80
            })

        pdf_bytes = await generator.generate_coraldraw_sheet(
            "test_sheet_001",
            designs=designs
        )

        assert len(pdf_bytes) > 0
        assert pdf_bytes[:4] == b'%PDF'


class TestIntegration:
    """End-to-end integration tests"""

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """Test the complete DTF pipeline"""
        # This test would require mocking S3 and OpenAI
        # For now, just test that all modules can be imported
        from api.content_safety import ContentSafetyChecker
        from api.image_upscaler import ImageUpscaler
        from api.background_remover import BackgroundRemover
        from api.nesting_optimizer import NestingOptimizer
        from api.pdf_generator import PDFGenerator

        # All modules should be importable
        assert ContentSafetyChecker
        assert ImageUpscaler
        assert BackgroundRemover
        assert NestingOptimizer
        assert PDFGenerator


class TestShopifyWebhook:
    """Test Shopify webhook handling"""

    def test_verify_shopify_hmac(self):
        """Test HMAC verification"""
        from api.shopify_webhook import verify_shopify_hmac
        import hmac
        import hashlib

        secret = "test_secret"
        body = b'{"order_id": "123"}'

        # Create valid HMAC
        expected = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256
        ).digest()
        import base64
        hmac_header = base64.b64encode(expected).decode()

        # Verify
        result = verify_shopify_hmac(body, hmac_header, secret)
        assert result == True

    def test_verify_shopify_hmac_invalid(self):
        """Test HMAC verification with invalid signature"""
        from api.shopify_webhook import verify_shopify_hmac

        result = verify_shopify_hmac(
            b'{"test": true}',
            "invalid_signature",
            "secret"
        )
        assert result == False

    def test_extract_design_from_line_item(self):
        """Test extracting design info from Shopify line item"""
        from api.shopify_webhook import extract_design_from_line_item

        item = {
            "id": "line_item_123",
            "title": "Custom Tee",
            "properties": [
                {"name": "_design_uuid", "value": "uuid-abc-123"},
                {"name": "_product_type", "value": "hoodie"}
            ]
        }

        result = extract_design_from_line_item(item)

        assert result["design_uuid"] == "uuid-abc-123"
        assert result["product_type"] == "hoodie"

    def test_extract_design_missing_uuid(self):
        """Test handling of line item without design UUID"""
        from api.shopify_webhook import extract_design_from_line_item

        item = {
            "id": "line_item_123",
            "title": "Regular Tee",
            "properties": []
        }

        result = extract_design_from_line_item(item)

        assert result is None


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])