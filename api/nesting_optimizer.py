"""
Nesting Optimizer - CoralDraw Sheet Layout
==========================================
Optimizes placement of multiple designs on standard DTF/CoralDraw sheets.
Uses bin-packing algorithm to maximize sheet utilization.

Standard sheet sizes:
- A3: 297 x 420 mm (for larger designs)
- 12x18 inch: 304.8 x 457.2 mm (common DTF sheet)
- 17x22 inch: 431.8 x 558.8 mm (large format)

Design spacing: 10mm bleed between designs

Author: Claude Code
"""

import io
import time
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import numpy as np


class NestingOptimizer:
    """
    Optimizes design placement on print sheets
    """

    # Standard sheet sizes in mm
    SHEET_SIZES = {
        "a3": {"width": 297, "height": 420},
        "12x18": {"width": 305, "height": 457},  # 12x18 inches
        "17x22": {"width": 432, "height": 559},  # 17x22 inches
        "a4": {"width": 210, "height": 297}
    }

    def __init__(self, sheet_size: str = "12x18"):
        self.sheet_size = sheet_size
        self.sheet_dimensions = self.SHEET_SIZES.get(sheet_size, self.SHEET_SIZES["12x18"])
        self.bleed_mm = 10  # 10mm bleed between designs
        self.edge_margin_mm = 15  # 15mm from sheet edge

        # Queue for pending designs
        self.pending_sheets: Dict[str, Dict] = {}
        self.max_designs_per_sheet = 4  # Maximum designs per A3-equivalent sheet

    async def add_design(
        self,
        design_uuid: str,
        design_image: bytes,
        user_id: str,
        product_type: str = "tee"
    ) -> Dict[str, Any]:
        """
        Add a design to the nesting queue.
        Returns sheet_ready=true when sheet is full and needs PDF generation.

        Args:
            design_uuid: Unique identifier for the design
            design_image: PNG image bytes with transparency
            user_id: User who created the design
            product_type: "tee" or "hoodie" (affects sizing)

        Returns:
            Dict with placement info and sheet_ready status
        """
        # Get or create pending sheet
        sheet_id = self._get_or_create_sheet()

        # Load image to get dimensions
        img = Image.open(io.BytesIO(design_image))
        width_mm, height_mm = self._pixels_to_mm(img.width, img.height)

        # Determine design size based on product type
        max_width, max_height = self._get_max_dimensions(product_type)

        # Scale design if needed
        if width_mm > max_width or height_mm > max_height:
            scale = min(max_width / width_mm, max_height / height_mm)
            new_width = int(img.width * scale)
            new_height = int(img.height * scale)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            width_mm, height_mm = self._pixels_to_mm(new_width, new_height)

        # Store design info
        design_info = {
            "design_uuid": design_uuid,
            "user_id": user_id,
            "product_type": product_type,
            "image_bytes": design_image,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "added_at": time.time()
        }

        # Try to place design on current sheet
        placement = self._find_placement(
            sheet_id,
            width_mm + self.bleed_mm,
            height_mm + self.bleed_mm
        )

        if placement:
            design_info["x_mm"] = placement["x"]
            design_info["y_mm"] = placement["y"]
            design_info["placed"] = True
            self.pending_sheets[sheet_id]["designs"].append(design_info)
        else:
            # No room, design waits for next sheet
            design_info["placed"] = False
            # Create new sheet
            sheet_id = self._create_new_sheet()
            placement = self._find_placement(
                sheet_id,
                width_mm + self.bleed_mm,
                height_mm + self.bleed_mm
            )
            design_info["x_mm"] = placement["x"]
            design_info["y_mm"] = placement["y"]
            design_info["placed"] = True
            self.pending_sheets[sheet_id]["designs"].append(design_info)

        # Check if sheet is ready
        sheet = self.pending_sheets[sheet_id]
        sheet_ready = len(sheet["designs"]) >= self.max_designs_per_sheet

        return {
            "sheet_id": sheet_id,
            "design_uuid": design_uuid,
            "placed": design_info["placed"],
            "position": placement,
            "sheet_ready": sheet_ready,
            "designs_in_sheet": len(sheet["designs"]),
            "max_designs": self.max_designs_per_sheet
        }

    def _get_or_create_sheet(self) -> str:
        """Get existing open sheet or create new one"""
        for sheet_id, sheet in self.pending_sheets.items():
            if sheet["status"] == "open" and len(sheet["designs"]) < self.max_designs_per_sheet:
                return sheet_id

        return self._create_new_sheet()

    def _create_new_sheet(self) -> str:
        """Create a new sheet"""
        sheet_id = f"sheet_{int(time.time())}_{len(self.pending_sheets)}"

        # Calculate usable area
        usable_width = self.sheet_dimensions["width"] - (2 * self.edge_margin_mm)
        usable_height = self.sheet_dimensions["height"] - (2 * self.edge_margin_mm)

        self.pending_sheets[sheet_id] = {
            "sheet_id": sheet_id,
            "sheet_size": self.sheet_size,
            "dimensions_mm": self.sheet_dimensions,
            "usable_area": {
                "width": usable_width,
                "height": usable_height
            },
            "designs": [],
            "occupied_cells": set(),  # Grid-based tracking
            "status": "open",
            "created_at": time.time()
        }

        return sheet_id

    def _find_placement(
        self,
        sheet_id: str,
        width_mm: float,
        height_mm: float
    ) -> Optional[Dict[str, float]]:
        """
        Find optimal placement for a design using shelf algorithm.
        Simplified bin-packing: places items in rows, moves to next row when no room.
        """
        sheet = self.pending_sheets[sheet_id]
        usable = sheet["usable_area"]

        # Quick-fit algorithm - try to find best fit
        best_placement = None
        best_waste = float('inf')

        # Try different x positions with edge margin
        for x_offset in range(0, int(usable["width"] - width_mm) + 1, 5):
            for y_offset in range(0, int(usable["height"] - height_mm) + 1, 5):
                if self._can_place(sheet_id, x_offset, y_offset, width_mm, height_mm, usable):
                    # Calculate waste (distance to right edge)
                    waste = (usable["width"] - (x_offset + width_mm)) + \
                            (usable["height"] - (y_offset + height_mm))

                    if waste < best_waste:
                        best_waste = waste
                        best_placement = {
                            "x": x_offset + self.edge_margin_mm,
                            "y": y_offset + self.edge_margin_mm
                        }

        return best_placement

    def _can_place(
        self,
        sheet_id: str,
        x_mm: float,
        y_mm: float,
        width_mm: float,
        height_mm: float,
        usable: Dict
    ) -> bool:
        """
        Check if placement is valid (no overlap with existing designs)
        """
        sheet = self.pending_sheets[sheet_id]

        for design in sheet["designs"]:
            if not design.get("placed"):
                continue

            dx = design.get("x_mm", 0)
            dy = design.get("y_mm", 0)
            dw = design.get("width_mm", 0)
            dh = design.get("height_mm", 0)

            # Check overlap
            if not (x_mm + width_mm <= dx or x_mm >= dx + dw or
                    y_mm + height_mm <= dy or y_mm >= dy + dh):
                return False

        return True

    def _get_max_dimensions(self, product_type: str) -> Tuple[float, float]:
        """Get maximum design dimensions based on product type (in mm)"""
        if product_type == "hoodie":
            # Larger for hoodie front/back print
            return (280, 380)  # ~11x15 inches
        else:
            # Standard tee size
            return (250, 350)  # ~10x14 inches

    def _pixels_to_mm(self, width_px: int, height_px: int, dpi: int = 300) -> Tuple[float, float]:
        """Convert pixels to millimeters at given DPI"""
        # 1 inch = 25.4 mm
        width_mm = (width_px / dpi) * 25.4
        height_mm = (height_px / dpi) * 25.4
        return width_mm, height_mm

    def get_sheet_status(self, sheet_id: str) -> Dict[str, Any]:
        """Get current status of a sheet"""
        if sheet_id not in self.pending_sheets:
            return {"error": "Sheet not found"}

        sheet = self.pending_sheets[sheet_id]
        return {
            "sheet_id": sheet_id,
            "designs_count": len(sheet["designs"]),
            "max_designs": self.max_designs_per_sheet,
            "is_full": len(sheet["designs"]) >= self.max_designs_per_sheet,
            "designs": [
                {
                    "uuid": d["design_uuid"],
                    "position": (d.get("x_mm", 0), d.get("y_mm", 0)),
                    "size": (d.get("width_mm", 0), d.get("height_mm", 0))
                }
                for d in sheet["designs"]
            ]
        }

    def force_sheet_completion(self, sheet_id: str = None) -> Optional[Dict]:
        """
        Force completion of a sheet even if not full.
        Used for end-of-day processing.
        """
        if sheet_id and sheet_id in self.pending_sheets:
            sheets_to_complete = [self.pending_sheets[sheet_id]]
        else:
            # Complete all open sheets
            sheets_to_complete = [
                s for s in self.pending_sheets.values()
                if s["status"] == "open"
            ]

        results = []
        for sheet in sheets_to_complete:
            sheet["status"] = "completed"
            results.append({
                "sheet_id": sheet["sheet_id"],
                "designs_count": len(sheet["designs"])
            })

        return results if results else None


# Test function
if __name__ == "__main__":
    import asyncio

    async def test():
        from PIL import Image, ImageDraw

        # Create test designs
        def create_test_design(width, height, color):
            img = Image.new('RGBA', (width, height), color)
            return img

        optimizer = NestingOptimizer()

        # Add 4 designs
        for i in range(4):
            # Different sized designs
            sizes = [(400, 400), (300, 500), (350, 350), (450, 300)]
            w, h = sizes[i]
            img = create_test_design(w, h, (255, i*50, 0, 255))

            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_bytes = buffer.getvalue()

            result = await optimizer.add_design(
                design_uuid=f"design_{i}",
                design_image=img_bytes,
                user_id=f"user_{i}",
                product_type="tee"
            )
            print(f"Design {i}: {result}")

        # Check final sheet status
        status = optimizer.get_sheet_status("sheet_1")
        print(f"\nFinal sheet status: {status}")

    asyncio.run(test())