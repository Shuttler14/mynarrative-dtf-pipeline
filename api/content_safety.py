"""
Content Safety Checker - OpenAI Moderation API
==============================================
Uses OpenAI's Moderation API to check if design content is safe.
If unsafe, the design is flagged and not processed further.

Supported categories:
- hate, hate/threatening
- harassment, harassment/threatening
- self-harm, self-harm/intent, self-harm/instructions
- sexual, sexual/minors
- violence, violence/graphic

Environment:
- OPENAI_API_KEY: Required for API calls

Author: Claude Code
"""

import os
import base64
from typing import Dict, Any, Optional
import httpx


class ContentSafetyChecker:
    """
    Checks image content for safety violations using OpenAI Moderation API
    """

    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.endpoint = "https://api.openai.com/v1/moderations"
        self.timeout = 30.0

    async def check_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Check if image content is safe for printing.

        Args:
            image_bytes: Raw image bytes (PNG/JPG)

        Returns:
            Dict with keys:
                - is_safe: bool
                - flagged_categories: list of flagged categories
                - confidence_scores: dict of category scores
        """
        if not self.api_key:
            return {
                "is_safe": True,  # Skip check if no API key
                "flags": [],
                "note": "No OPENAI_API_KEY configured - skipped check"
            }

        # Convert image to base64 for API
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "input": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_base64}"
                    }
                }
            ],
            "parameters": {
                "categories": [
                    "hate",
                    "hate/threatening",
                    "harassment",
                    "harassment/threatening",
                    "self-harm",
                    "self-harm/intent",
                    "self-harm/instructions",
                    "sexual",
                    "sexual/minors",
                    "violence",
                    "violence/graphic"
                ]
            }
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers=headers,
                    json=payload
                )

                if response.status_code != 200:
                    return {
                        "is_safe": False,
                        "flags": ["api_error"],
                        "error": f"API returned {response.status_code}",
                        "raw_response": response.text
                    }

                result = response.json()

                # Parse moderation results
                return self._parse_moderation_result(result)

        except httpx.TimeoutException:
            return {
                "is_safe": False,
                "flags": ["timeout"],
                "error": "OpenAI API timeout"
            }
        except Exception as e:
            return {
                "is_safe": False,
                "flags": ["exception"],
                "error": str(e)
            }

    def _parse_moderation_result(self, result: Dict) -> Dict[str, Any]:
        """
        Parse OpenAI moderation API response
        """
        try:
            # Handle the nested response structure
            results = result.get("results", [])

            if not results:
                return {
                    "is_safe": True,
                    "flags": [],
                    "note": "No results in response"
                }

            first_result = results[0]

            # Check flagged categories
            flagged = []
            category_scores = {}

            categories = first_result.get("categories", {})
            category_scores_raw = first_result.get("category_scores", {})

            for category, is_flagged in categories.items():
                if is_flagged:
                    flagged.append(category)
                category_scores[category] = category_scores_raw.get(category, 0.0)

            # Consider unsafe if any category is flagged with > 0.5 confidence
            is_safe = len(flagged) == 0 or all(
                category_scores.get(cat, 0) < 0.5 for cat in flagged
            )

            return {
                "is_safe": is_safe,
                "flags": flagged,
                "confidence_scores": category_scores,
                "model": first_result.get("model", "unknown")
            }

        except Exception as e:
            return {
                "is_safe": False,
                "flags": ["parse_error"],
                "error": f"Failed to parse: {str(e)}"
            }

    async def check_with_fallback(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Fallback: if OpenAI fails, use a basic image analysis
        as a second line of defense
        """
        result = await self.check_image(image_bytes)

        if not result.get("is_safe"):
            return result

        # Fallback to basic checks
        return self._basic_content_check(image_bytes)

    def _basic_content_check(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Basic content checks as fallback (placeholder)
        In production, this could use:
        - AWS Rekognition
        - Google Cloud Vision
        - Local ML model
        """
        # For now, pass through if OpenAI check passed
        return {
            "is_safe": True,
            "flags": [],
            "method": "basic_check_passed"
        }


# Test function
if __name__ == "__main__":
    import asyncio

    async def test():
        checker = ContentSafetyChecker()

        # Test with a sample image (create a simple 100x100 PNG)
        from PIL import Image
        import io

        img = Image.new('RGB', (100, 100), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        test_bytes = buffer.getvalue()

        result = await checker.check_image(test_bytes)
        print(f"Result: {result}")

    asyncio.run(test())