"""Parts detector - extracts parts from instruction pages."""

import logging
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

import numpy as np
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
import cv2
import pdfplumber

from .utils import find_poppler_path, configure_tesseract, format_page_ranges, normalize_background_color

# Configure Tesseract on Windows
configure_tesseract()

logger = logging.getLogger(__name__)


@dataclass
class ExtractedPart:
    """Extracted part from instruction page."""

    image: np.ndarray  # Extracted part image
    normalized_image: np.ndarray  # Preprocessed for matching
    quantity: str  # e.g., "2x"
    quantity_value: int  # Numeric value (e.g., 2)
    page: int  # Source page number
    position: Tuple[int, int]  # (x, y) position on page
    bbox: Tuple[int, int, int, int]  # (x0, y0, x1, y1) bounding box
    confidence: float  # OCR confidence for quantity


class PartsDetector:
    """Detector for parts in instruction pages."""

    def __init__(
        self,
        instruction_pdf: Path,
        instruction_pages: List[int],
        search_radius: int = 80,
        min_piece_size: int = 20,
        max_piece_size: int = 250,
        dpi: int = 300,
        match_color: bool = True,
        debug_output_dir: Optional[Path] = None,
    ):
        """Initialize parts detector.

        Args:
            instruction_pdf: Path to instruction PDF
            instruction_pages: List of pages to process
            search_radius: Pixel radius to search around quantity
            min_piece_size: Minimum piece dimensions
            max_piece_size: Maximum piece dimensions
            dpi: DPI for PDF to image conversion
            match_color: Whether to preserve color in normalized images
            debug_output_dir: Directory for debug output (None to disable)
        """
        self.instruction_pdf = instruction_pdf
        self.instruction_pages = instruction_pages
        self.search_radius = search_radius
        self.min_piece_size = min_piece_size
        self.max_piece_size = max_piece_size
        self.dpi = dpi
        self.match_color = match_color
        self.debug_output_dir = debug_output_dir
        self.instruction_parts_output_dir = None
        self.logger = logging.getLogger(__name__)
        self.poppler_path = find_poppler_path()

        if self.debug_output_dir:
            self.debug_output_dir.mkdir(parents=True, exist_ok=True)
            # Create subdirectory for instruction parts extracted images
            self.instruction_parts_output_dir = (
                self.debug_output_dir / "instruction_parts_extracted"
            )
            self.instruction_parts_output_dir.mkdir(parents=True, exist_ok=True)

    def detect(self) -> List[ExtractedPart]:
        """Detect parts from all instruction pages.

        Returns:
            List of ExtractedPart objects
        """
        all_parts = []

        # Open PDF once and reuse for all pages to avoid file handle exhaustion
        try:
            with pdfplumber.open(self.instruction_pdf) as pdf:
                for page_num in self.instruction_pages:
                    self.logger.info(f"  Processing page {page_num}...")
                    parts = self._detect_parts_on_page(page_num, pdf)
                    self.logger.info(f"    Found {len(parts)} parts boxes")
                    all_parts.extend(parts)
        except Exception as e:
            self.logger.warning(f"Failed to open PDF with pdfplumber: {e}")
            self.logger.warning("Falling back to OCR-only mode")
            # Fall back to OCR-only mode
            for page_num in self.instruction_pages:
                self.logger.info(f"  Processing page {page_num}...")
                parts = self._detect_parts_on_page(page_num, None)
                self.logger.info(f"    Found {len(parts)} parts boxes")
                all_parts.extend(parts)

        self.logger.info(f"  Total parts extracted: {len(all_parts)}")
        return all_parts

    def _detect_parts_on_page(self, page_num: int, pdf=None) -> List[ExtractedPart]:
        """Detect parts on a single instruction page.

        Args:
            page_num: Page number (1-indexed)
            pdf: Optional pdfplumber PDF object (for reuse across pages)

        Returns:
            List of ExtractedPart objects
        """
        # Convert PDF page to image
        images = convert_from_path(
            self.instruction_pdf,
            dpi=self.dpi,
            first_page=page_num,
            last_page=page_num,
            poppler_path=self.poppler_path,
        )
        page_image = np.array(images[0])

        # Save debug image
        if self.debug_output_dir:
            debug_path = (
                self.debug_output_dir / f"instruction_page_{page_num:02d}_original.png"
            )
            Image.fromarray(page_image).save(debug_path)

        # Try to extract text directly from PDF first (more reliable)
        quantities = self._extract_quantities_from_pdf(page_num, page_image, pdf)

        # Fall back to OCR if PDF extraction fails or finds nothing
        if not quantities:
            self.logger.debug(f"    No text found in PDF, falling back to OCR")
            ocr_data = pytesseract.image_to_data(
                page_image,
                output_type=pytesseract.Output.DICT,
            )
            quantities = self._extract_quantities(ocr_data, page_image)

        self.logger.debug(f"    Found {len(quantities)} quantity indicators")

        # Save debug image with quantity locations
        if self.debug_output_dir:
            self._save_quantity_debug_image(page_image, quantities, page_num)

        # Extract parts near each quantity
        # Try PDF image extraction first (same algorithm as pieces list parser)
        parts = []
        for qty_idx, qty_data in enumerate(quantities):
            self.logger.debug(
                f"    Processing quantity {qty_idx + 1}/{len(quantities)}: {qty_data['text']} at ({qty_data['x']}, {qty_data['y']})"
            )
            
            # Try PDF image extraction first (same algorithm as pieces_parser)
            part = self._extract_part_from_pdf_image(page_image, qty_data, page_num, pdf)
            
            # Fall back to contour-based extraction if PDF extraction fails
            if part is None:
                part = self._extract_part_near_quantity(page_image, qty_data, page_num)
                if part is not None:
                    self.logger.debug(f"      Used fallback extraction (contour-based)")
            else:
                self.logger.debug(f"      Used PDF image extraction")
            
            if part is not None:
                parts.append(part)
            else:
                self.logger.debug(f"      No part found for this quantity")

        # Create debug visualization
        if self.debug_output_dir and parts:
            self._create_debug_visualization(page_image, parts, page_num)

        return parts

    def _is_on_blue_background(
        self, page_image: np.ndarray, x: int, y: int, w: int, h: int
    ) -> bool:
        """Check if a region is on a blue background (parts box).

        Blue backgrounds indicate individual LEGO parts.
        Beige/tan backgrounds indicate sub-assemblies (should be ignored).

        Args:
            page_image: Full page image (RGB)
            x, y, w, h: Bounding box of quantity text

        Returns:
            True if background is blue, False otherwise
        """
        # Sample the area around the quantity text to determine background color
        # Expand the sampling region to get more context
        sample_margin = 10
        x0 = max(0, x - sample_margin)
        y0 = max(0, y - sample_margin)
        x1 = min(page_image.shape[1], x + w + sample_margin)
        y1 = min(page_image.shape[0], y + h + sample_margin)

        region = page_image[y0:y1, x0:x1]

        if region.size == 0:
            return False

        # Calculate mean color in RGB
        mean_color = np.mean(region, axis=(0, 1))
        r, g, b = mean_color

        # LEGO instruction blue backgrounds are light blue/cyan (e.g., RGB ~[205, 230, 247])
        # Characteristics:
        # - Blue channel is highest (B > G > R)
        # - Overall brightness is high (all channels > 150)
        # - Blue-ish hue (B > R by at least 30)
        #
        # Beige/tan backgrounds have more balanced RGB or higher red (e.g., RGB ~[230, 220, 200])
        # - Red/Green higher than blue
        # - More neutral or warm tone

        is_light_blue = (
            b > 200  # High blue component (light blue)
            and b > g + 10  # Blue higher than green
            and b > r + 30  # Blue significantly higher than red (blue hue)
            and g > 180  # Green also high (makes it light, not dark blue)
        )

        # Also check for darker blue variants (in case some pages use darker blue)
        is_dark_blue = (
            b > 150  # Moderate blue component
            and b > r + 40  # Blue much higher than red
            and b > g + 20  # Blue higher than green
            and r < 180  # Not too much red (avoid purple/white)
        )

        return is_light_blue or is_dark_blue

    def _extract_quantities(self, ocr_data: dict, page_image: np.ndarray) -> List[dict]:
        """Extract quantity indicators from OCR data.

        Args:
            ocr_data: pytesseract OCR data dictionary
            page_image: Full page image for background color detection

        Returns:
            List of quantity data dictionaries
        """
        quantities = []

        for i, text in enumerate(ocr_data["text"]):
            if not text or not text.strip():
                continue

            # Look for patterns like "1x", "2x", "10x", etc.
            # Also handle OCR errors like "lx" -> "1x"
            text_clean = text.strip().lower()
            text_clean = text_clean.replace("l", "1").replace("o", "0")

            match = re.match(r"^(\d+)x$", text_clean, re.IGNORECASE)
            if match:
                quantity_value = int(match.group(1))

                # Sanity check - quantities are typically small (1-50)
                if 1 <= quantity_value <= 50:
                    x = ocr_data["left"][i]
                    y = ocr_data["top"][i]
                    w = ocr_data["width"][i]
                    h = ocr_data["height"][i]

                    # Filter by background color - only keep quantities on blue backgrounds
                    if not self._is_on_blue_background(page_image, x, y, w, h):
                        continue

                    # Filter by position - parts boxes are typically in top 50% OR bottom 20%
                    # Exclude middle section (50-80%) where assembly instructions are common
                    relative_y = y / page_image.shape[0]
                    if 0.5 < relative_y < 0.8:
                        continue

                    quantities.append(
                        {
                            "text": f"{quantity_value}x",
                            "value": quantity_value,
                            "x": x,
                            "y": y,
                            "w": w,
                            "h": h,
                            "conf": float(ocr_data["conf"][i])
                            if ocr_data["conf"][i] != -1
                            else 0.0,
                        }
                    )

        return quantities

    def _extract_quantities_from_pdf(
        self, page_num: int, page_image: np.ndarray, pdf=None
    ) -> List[dict]:
        """Extract quantity indicators directly from PDF text.

        Args:
            page_num: Page number (1-indexed)
            page_image: Full page image for background color detection
            pdf: Optional pdfplumber PDF object (for reuse across pages)

        Returns:
            List of quantity data dictionaries
        """
        quantities = []

        # If no PDF object provided, skip PDF extraction
        if pdf is None:
            return quantities

        try:
            # pdfplumber uses 0-indexed pages
            page = pdf.pages[page_num - 1]

            # Get page dimensions from PDF (in points)
            pdf_width = float(page.width)
            pdf_height = float(page.height)

            # Calculate rendered page dimensions
            # DPI determines the scale: points_to_pixels = dpi / 72
            scale = self.dpi / 72.0
            rendered_width = int(pdf_width * scale)
            rendered_height = int(pdf_height * scale)

            # Extract text with positions
            words = page.extract_words()

            for word in words:
                text = word["text"].strip()

                # Look for patterns like "1x", "2x", "10x"
                match = re.match(r"^(\d+)x$", text, re.IGNORECASE)
                if match:
                    quantity_value = int(match.group(1))

                    # Sanity check - quantities are typically small (1-50)
                    if 1 <= quantity_value <= 50:
                        # Convert PDF coordinates to image coordinates
                        # pdfplumber uses top-left origin (same as images), so no Y-flip needed
                        pdf_x0 = float(word["x0"])
                        pdf_y0 = float(word["top"])
                        pdf_x1 = float(word["x1"])
                        pdf_y1 = float(word["bottom"])

                        # Scale PDF coordinates to image resolution
                        img_x = int(pdf_x0 * scale)
                        img_y = int(pdf_y0 * scale)
                        img_w = int((pdf_x1 - pdf_x0) * scale)
                        img_h = int((pdf_y1 - pdf_y0) * scale)

                        # Filter by background color - only keep quantities on blue backgrounds
                        # Blue backgrounds = individual parts, Beige backgrounds = sub-assemblies
                        if not self._is_on_blue_background(
                            page_image, img_x, img_y, img_w, img_h
                        ):
                            continue

                        # Filter by position - parts boxes are typically in top 50% OR bottom 20%
                        # Exclude middle section (50-80%) where assembly instructions are common
                        relative_y = img_y / rendered_height
                        if 0.5 < relative_y < 0.8:
                            continue

                        quantities.append(
                            {
                                "text": f"{quantity_value}x",
                                "value": quantity_value,
                                "x": img_x,
                                "y": img_y,
                                "w": img_w,
                                "h": img_h,
                                "conf": 100.0,  # PDF text extraction is reliable
                            }
                        )

        except Exception as e:
            self.logger.warning(f"Failed to extract text from PDF page {page_num}: {e}")

        return quantities

    def _extract_images_from_pdf(self, page_num: int, pdf=None) -> Tuple[List[dict], int, int]:
        """Extract images from PDF with positions.

        Args:
            page_num: Page number (1-indexed)
            pdf: Optional pdfplumber PDF object (for reuse across pages)

        Returns:
            Tuple of (images list, pdf page width, pdf page height)
        """
        images = []
        pdf_width = 612
        pdf_height = 792

        if pdf is None:
            try:
                with pdfplumber.open(self.instruction_pdf) as pdf:
                    return self._extract_images_from_pdf(page_num, pdf)
            except Exception as e:
                self.logger.warning(f"Failed to open PDF for image extraction: {e}")
                return images, pdf_width, pdf_height

        try:
            if page_num - 1 >= len(pdf.pages):
                return images, pdf_width, pdf_height

            page = pdf.pages[page_num - 1]
            pdf_width = int(page.width)
            pdf_height = int(page.height)
            page_images = page.images

            for img in page_images:
                images.append({
                    "x0": int(img.get("x0", 0)),
                    "y0": int(img.get("y0", 0)),
                    "x1": int(img.get("x1", 0)),
                    "y1": int(img.get("y1", 0)),
                    "width": int(img.get("width", 0)),
                    "height": int(img.get("height", 0)),
                    "stream": img.get("stream"),
                })

        except Exception as e:
            self.logger.warning(f"Failed to extract PDF images: {e}")

        return images, pdf_width, pdf_height

    def _extract_part_from_pdf_image(
        self,
        page_image: np.ndarray,
        qty_data: dict,
        page_num: int,
        pdf=None,
    ) -> Optional[ExtractedPart]:
        """Extract part image using PDF image positions (same algorithm as pieces_parser).

        Args:
            page_image: Full page image
            qty_data: Quantity data dictionary
            page_num: Page number
            pdf: Optional pdfplumber PDF object

        Returns:
            ExtractedPart object or None if extraction fails
        """
        qty_center_x = qty_data["x"] + qty_data["w"] / 2
        qty_center_y = qty_data["y"] + qty_data["h"] / 2
        debug_prefix = f"page{page_num:02d}_qty{qty_data['value']}_x{int(qty_center_x)}_y{int(qty_center_y)}"
        
        def save_debug_image(img_array, suffix):
            if self.instruction_parts_output_dir:
                path = self.instruction_parts_output_dir / f"{debug_prefix}_{suffix}.png"
                Image.fromarray(img_array).save(path)

        pdf_images, pdf_width, pdf_height = self._extract_images_from_pdf(page_num, pdf)

        if not pdf_images:
            save_debug_image(page_image[max(0, int(qty_center_y)-100):int(qty_center_y)+50, 
                             max(0, int(qty_center_x)-100):int(qty_center_x)+100], "0_no_pdf_images")
            return None

        qty_x = qty_data["x"]
        qty_y = qty_data["y"]

        img_width = page_image.shape[1]
        img_height = page_image.shape[0]

        scale_x = img_width / pdf_width
        scale_y = img_height / pdf_height

        def image_distance(img):
            img_center_x = (img["x0"] + img["x1"]) / 2
            img_bottom_y = pdf_height - img["y0"]
            h_dist = abs(img_center_x - qty_x)
            v_dist = qty_y - img_bottom_y
            if v_dist < 0:
                v_dist = abs(v_dist) * 10
            return (h_dist ** 2 + v_dist ** 2) ** 0.5

        pdf_images_sorted = sorted(pdf_images, key=image_distance)
        
        best_img = None
        best_distance = float("inf")
        
        for idx, img in enumerate(pdf_images_sorted):
            img_x0 = int(img["x0"] * scale_x)
            img_y0 = int((pdf_height - img["y1"]) * scale_y)
            img_x1 = int(img["x1"] * scale_x)
            img_y1 = int((pdf_height - img["y0"]) * scale_y)
            
            img_x0 = max(0, img_x0)
            img_y0 = max(0, img_y0)
            img_x1 = min(img_width, img_x1)
            img_y1 = min(img_height, img_y1)
            
            if img_y1 < img_y0:
                img_y0, img_y1 = img_y1, img_y0
            
            if img_x1 <= img_x0 or img_y1 <= img_y0:
                continue
            
            closest_x = max(img_x0, min(qty_center_x, img_x1))
            closest_y = max(img_y0, min(qty_center_y, img_y1))
            dist_to_edge = ((closest_x - qty_center_x) ** 2 + (closest_y - qty_center_y) ** 2) ** 0.5
            
            if dist_to_edge > self.search_radius * 3:
                continue
            
            sample_region = page_image[img_y0:min(img_y0+20, img_height), img_x0:min(img_x0+20, img_width)]
            if sample_region.size == 0:
                continue
            
            r, g, b = sample_region[:,:,0], sample_region[:,:,1], sample_region[:,:,2]
            mean_b = np.mean(b)
            mean_r = np.mean(r)
            mean_g = np.mean(g)
            
            is_blue_bg = mean_b > 200 and mean_b > mean_r + 30 and mean_b > mean_g + 10
            
            if not is_blue_bg:
                save_debug_image(page_image[max(0, int(qty_center_y)-150):int(qty_center_y)+100,
                                 max(0, int(qty_center_x)-150):int(qty_center_x)+150], 
                               f"1_rejected_not_blue_bg")
                continue
            
            best_img = img
            best_distance = dist_to_edge
            break
        
        if best_img is None:
            save_debug_image(page_image[max(0, int(qty_center_y)-150):int(qty_center_y)+100,
                             max(0, int(qty_center_x)-150):int(qty_center_x)+150], 
                           "2_no_suitable_image")
            return None

        img_x0 = int(best_img["x0"] * scale_x)
        img_y0 = int((pdf_height - best_img["y1"]) * scale_y)
        img_x1 = int(best_img["x1"] * scale_x)
        img_y1 = int((pdf_height - best_img["y0"]) * scale_y)

        img_x0 = max(0, img_x0)
        img_y0 = max(0, img_y0)
        img_x1 = min(img_width, img_x1)
        img_y1 = min(img_height, img_y1)

        if img_y1 < img_y0:
            img_y0, img_y1 = img_y1, img_y0

        if img_x1 <= img_x0 or img_y1 <= img_y0:
            return None

        piece_image = page_image[img_y0:img_y1, img_x0:img_x1]

        if piece_image.size == 0:
            return None

        piece_image = normalize_background_color(piece_image)
        white_bg = np.ones_like(piece_image) * 255
        piece_image = np.where(piece_image < 240, piece_image, white_bg)

        h, w = piece_image.shape[:2]
        if w < self.min_piece_size or h < self.min_piece_size:
            save_debug_image(piece_image, f"3_rejected_too_small_{w}x{h}")
            return None

        normalized = self._normalize_image(piece_image)

        part = ExtractedPart(
            image=piece_image,
            normalized_image=normalized,
            quantity=qty_data["text"],
            quantity_value=qty_data["value"],
            page=page_num,
            position=(int(qty_center_x), int(qty_center_y)),
            bbox=(img_x0, img_y0, img_x1, img_y1),
            confidence=qty_data["conf"] / 100.0,
        )

        save_debug_image(piece_image, "success")

        return part

    def _extract_part_near_quantity(
        self,
        page_image: np.ndarray,
        qty_data: dict,
        page_num: int,
    ) -> Optional[ExtractedPart]:
        """Extract part image near a quantity indicator.

        Args:
            page_image: Full page image
            qty_data: Quantity data dictionary
            page_num: Page number

        Returns:
            ExtractedPart object or None if extraction fails
        """
        # Define search region around quantity
        qty_center_x = qty_data["x"] + qty_data["w"] / 2
        qty_center_y = qty_data["y"] + qty_data["h"] / 2

        # Search primarily ABOVE the quantity indicator since LEGO instructions
        # typically place part images directly above the quantity text
        # However, sometimes quantities are overlaid ON the part images (in corner)
        # Strategy: Create a search box that includes above AND the quantity location
        # to capture parts whether they're above or behind the quantity text

        # Adaptive search region expansion
        # CRITICAL: LEGO parts are ALWAYS positioned ABOVE the quantity indicator
        # Step numbers appear BELOW in white space
        # Strategy: Heavily favor upward search, allow moderate downward search
        # to capture parts that may be positioned below quantity text
        max_iterations = 5
        left_mult = 1.5
        right_mult = 1.5
        up_mult = 2.5  # More upward to find parts
        down_mult = 0.8  # Allow some downward for parts below quantity, but filtering catches text
        mult_increment = 0.3

        piece_image = None
        piece_bbox_in_region = None

        for iteration in range(max_iterations):
            x0 = max(0, int(qty_center_x - self.search_radius * left_mult))
            y0 = max(0, int(qty_center_y - self.search_radius * up_mult))
            x1 = min(
                page_image.shape[1], int(qty_center_x + self.search_radius * right_mult)
            )
            y1 = min(
                page_image.shape[0], int(qty_center_y + self.search_radius * down_mult)
            )

            if y1 <= y0 or x1 <= x0:
                continue

            # Extract search region
            search_region = page_image[y0:y1, x0:x1]

            # Calculate quantity position in region coordinates
            qty_y_in_region = qty_center_y - y0

            # Find piece in region, preferring parts above the quantity
            piece_image, piece_bbox_in_region = self._find_piece_in_region(
                search_region, qty_y_in_region, qty_center_x, qty_center_y, x0, y0
            )

            if piece_image is None:
                # No piece found, try expanding
                left_mult += mult_increment
                right_mult += mult_increment
                up_mult += mult_increment
                down_mult += mult_increment
                continue

            # Check if piece touches the edge of the search region
            px0, py0, px1, py1 = piece_bbox_in_region
            region_height, region_width = search_region.shape[:2]
            touches_edge = (
                px0 <= 0 or py0 <= 0 or px1 >= region_width or py1 >= region_height
            )

            if not touches_edge or iteration == max_iterations - 1:
                # Use this piece
                break
            else:
                # Expand in the directions it touches
                if px0 <= 0:
                    left_mult += mult_increment
                if px1 >= region_width:
                    right_mult += mult_increment
                if py0 <= 0:
                    up_mult += mult_increment
                if py1 >= region_height:
                    down_mult += mult_increment

        if piece_image is None:
            # No valid piece found after all expansion attempts
            return None

        # Check size constraints
        h, w = piece_image.shape[:2]
        if w < self.min_piece_size or h < self.min_piece_size:
            self.logger.debug(f"      Rejected part: too small ({w}x{h})")
            return None
        if w > self.max_piece_size or h > self.max_piece_size:
            self.logger.debug(f"      Rejected part: too large ({w}x{h})")
            return None

        # Convert bbox to page coordinates
        px0, py0, px1, py1 = piece_bbox_in_region
        page_bbox = (
            x0 + px0,
            y0 + py0,
            x0 + px1,
            y0 + py1,
        )

        # Normalize image for matching
        normalized = self._normalize_image(piece_image)

        part = ExtractedPart(
            image=piece_image,
            normalized_image=normalized,
            quantity=qty_data["text"],
            quantity_value=qty_data["value"],
            page=page_num,
            position=(int(qty_center_x), int(qty_center_y)),
            bbox=page_bbox,
            confidence=qty_data["conf"] / 100.0,  # Convert to 0-1
        )

        # Save extracted part image to instruction_parts_extracted folder
        if self.instruction_parts_output_dir:
            part_output_path = (
                self.instruction_parts_output_dir
                / f"extracted_page{page_num:02d}_qty{qty_data['value']}_x{int(qty_center_x)}_y{int(qty_center_y)}.png"
            )
            Image.fromarray(piece_image).save(part_output_path)

        return part

    def _find_piece_in_region(
        self,
        region: np.ndarray,
        qty_y_in_region: float,
        qty_center_x: float,
        qty_center_y: float,
        region_x0: int,
        region_y0: int,
    ) -> Tuple[Optional[np.ndarray], Optional[Tuple[int, int, int, int]]]:
        """Find piece within a search region using background filtering.

        Args:
            region: Image region to search (RGB)
            qty_y_in_region: Y position of quantity in region coordinates
            qty_center_x: X position of quantity in page coordinates
            qty_center_y: Y position of quantity in page coordinates
            region_x0: X offset of region in page coordinates
            region_y0: Y offset of region in page coordinates

        Returns:
            Tuple of (piece_image, bbox) or (None, None) if not found
        """
        if len(region.shape) != 3:
            # Need RGB image for color-based segmentation
            return None, None

        # Create mask to separate part from blue background
        # Blue background: high B channel, B > R, B > G
        r, g, b = region[:, :, 0], region[:, :, 1], region[:, :, 2]

        # Mask for blue background (parts are NOT blue background)
        # Light blue background: B > 180 and B > R+20 and B > G+10
        blue_mask = (b > 180) & (b > r + 20) & (b > g + 10)

        # Invert to get part mask (part = not blue background)
        part_mask = ~blue_mask

        # IMPORTANT: Mask out the quantity text location to avoid extracting it as a part
        # Quantity text is typically ~80-100px in both dimensions
        # We create a mask to exclude this region
        qty_exclusion_radius = 60  # pixels around quantity center
        qty_x_in_region = int(qty_center_x - region_x0)
        qty_y_in_region_val = int(qty_center_y - region_y0)

        # Create exclusion rectangle around quantity
        qty_exclude_x0 = max(0, qty_x_in_region - qty_exclusion_radius)
        qty_exclude_y0 = max(0, qty_y_in_region_val - qty_exclusion_radius)
        qty_exclude_x1 = min(region.shape[1], qty_x_in_region + qty_exclusion_radius)
        qty_exclude_y1 = min(
            region.shape[0], qty_y_in_region_val + qty_exclusion_radius
        )

        # Zero out the quantity text area in the part mask
        part_mask[qty_exclude_y0:qty_exclude_y1, qty_exclude_x0:qty_exclude_x1] = 0

        # Also filter out very light pixels (near white) as background
        brightness = (
            r.astype(np.float32) + g.astype(np.float32) + b.astype(np.float32)
        ) / 3
        white_mask = brightness > 240
        part_mask = part_mask & ~white_mask

        # Convert to uint8
        part_mask = part_mask.astype(np.uint8) * 255

        # Morphological operations to clean up mask
        kernel = np.ones((3, 3), np.uint8)
        part_mask = cv2.morphologyEx(part_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        part_mask = cv2.morphologyEx(part_mask, cv2.MORPH_OPEN, kernel, iterations=1)

        # Find contours in mask
        contours, _ = cv2.findContours(
            part_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return None, None

        # Filter and sort contours by area and quality
        min_area = self.min_piece_size * self.min_piece_size
        max_area = self.max_piece_size * self.max_piece_size

        valid_contours = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue

            # Get bounding rect to check dimensions
            x, y, w, h = cv2.boundingRect(contour)

            # Skip if too large
            if w > self.max_piece_size or h > self.max_piece_size:
                continue

            # Skip if aspect ratio is too extreme (likely border/noise)
            # LEGO parts typically have aspect ratios between 1:3 and 3:1
            aspect_ratio = max(w, h) / max(min(w, h), 1)
            if aspect_ratio > 3.5:
                continue

            # Calculate fill ratio (actual contour area vs bounding box area)
            bbox_area = w * h
            fill_ratio = area / max(bbox_area, 1)

            # EARLY FILTERING: Reject obvious text before adding to valid list
            # Quantity text and step numbers have very low fill ratios
            if fill_ratio < 0.25:
                # Extremely skeletal - definitely text, not a part
                # Skip this contour entirely
                continue

            valid_contours.append((y, area, contour, fill_ratio, aspect_ratio, w, h))

        if not valid_contours:
            return None, None

        # Sort by quality metrics:
        # 1. Higher fill ratio is better (solid parts > skeletal text)
        # 2. Larger area is better
        # 3. More square aspect ratio is better (closer to 1.0)
        valid_contours.sort(key=lambda x: (-x[3], -x[1], -abs(1.0 - x[4])))

        y, area, selected_contour, fill_ratio, aspect_ratio, cont_w, cont_h = (
            valid_contours[0]
        )
        cont_x, cont_y, _, _ = cv2.boundingRect(selected_contour)

        # KEY INSIGHT: LEGO parts are ALWAYS positioned ABOVE the quantity indicator
        # Strategy:
        # - ABOVE quantity (cont_y < qty_y_in_region): Accept any solid contour (lenient)
        # - BELOW quantity (cont_y >= qty_y_in_region): Strict text filtering (to avoid step numbers)

        is_above_quantity = cont_y < qty_y_in_region
        contour_area = cv2.contourArea(selected_contour)
        min_dimension = min(cont_w, cont_h)

        if is_above_quantity:
            # ABOVE quantity: Very lenient filtering
            # Parts above quantity are legitimate LEGO pieces
            # Only filter out extreme aspect ratios or extremely small items
            if aspect_ratio > 4.0:
                # Extremely tall or narrow - likely noise
                return None, None
            if contour_area < 50:
                # Too small to be a real part
                return None, None
            # Accept this contour - it's above the quantity so likely a valid part
        else:
            # BELOW/AT quantity: Strict text filtering
            # Quantity text like "2x", "3x" and step numbers appear near/below quantity
            # Reject anything that looks like text or numbers

            # FILTER: Reject very low fill ratio - characteristic of skeletal text
            # Quantity text "2x" has fill_ratio ~0.25, while LEGO parts are >0.4
            if fill_ratio < 0.35:
                # Very skeletal/thin - likely text, not a solid part
                return None, None

            # FILTER: Check for text-like characteristics
            # Text is typically:
            # - Very tall and narrow (high aspect ratio)
            # - Has low fill ratio (skeleton-like, not solid)
            # - Is very small (typical LEGO parts are at least ~50px in one dimension)

            # Filter out likely text/numbers:
            # - Aspect ratio > 2.0 AND fill ratio < 0.5 = likely text (tall, thin, skeletal)
            # - Very small bounding box (< 50px in smaller dimension) = likely text/noise
            # - Aspect ratio > 3.0 regardless of fill = extremely tall/narrow = text
            if aspect_ratio > 3.0:
                # Extremely tall or narrow - definitely text
                return None, None
            if min_dimension < 50 and aspect_ratio > 2.0 and fill_ratio < 0.5:
                # Small, tall, and skeletal - likely a number or character
                return None, None

            # FILTER: Reject small, tall contours that are likely text/numbers
            # Step numbers like "1", "2", "3" are characteristic:
            # - Very small (< 300 pixels total area)
            # - Very tall relative to width (aspect ratio > 1.8)
            # - Low fill ratio (skeletal)
            if contour_area < 300 and aspect_ratio > 1.8 and fill_ratio < 0.5:
                # Definitely a small, skeletal character - reject it
                return None, None

        # FILTER 3: Validate that the context around the part is appropriate
        # (mostly blue background or white, not dark areas like step numbers or text)
        # Expand search box slightly to check surrounding area
        context_margin = 10
        ctx_x0 = max(0, cont_x - context_margin)
        ctx_y0 = max(0, cont_y - context_margin)
        ctx_x1 = min(region.shape[1], cont_x + cont_w + context_margin)
        ctx_y1 = min(region.shape[0], cont_y + cont_h + context_margin)

        context_region = region[ctx_y0:ctx_y1, ctx_x0:ctx_x1]
        r_ctx = context_region[:, :, 0].astype(np.float32)
        g_ctx = context_region[:, :, 1].astype(np.float32)
        b_ctx = context_region[:, :, 2].astype(np.float32)

        # Check if context is mostly blue (parts box background)
        # LEGO parts should be in blue boxes, not white background
        # Step numbers appear on white background below the part boxes
        brightness_ctx = (r_ctx + g_ctx + b_ctx) / 3
        blue_ctx = b_ctx > 180
        white_ctx = brightness_ctx > 220

        # Calculate blue ratio in context
        blue_ratio = np.mean(blue_ctx)
        white_ratio = np.mean(white_ctx)

        # For parts BELOW quantity: require strong blue background (>50%)
        # to avoid capturing step numbers on white background
        # For parts ABOVE quantity: more lenient (>30% blue) since parts may be at edges
        if not is_above_quantity:
            # Below quantity - strict: need significant blue background
            if blue_ratio < 0.5:
                # Not enough blue background - likely text on white, not a part
                return None, None
        else:
            # Above quantity - still require some blue context
            # but more lenient than below
            if blue_ratio < 0.3:
                # Very little blue background - suspicious
                return None, None

        # Extract the contour region
        contour_region_mask = part_mask[
            cont_y : cont_y + cont_h, cont_x : cont_x + cont_w
        ]

        # Find tight bbox within the contour region based on actual mask pixels
        mask_coords = np.argwhere(contour_region_mask > 0)
        if len(mask_coords) == 0:
            # Fall back to full contour bbox if no mask pixels found
            final_x, final_y = cont_x, cont_y
            final_w, final_h = cont_w, cont_h
        else:
            # Compute tight bbox from mask pixels within contour
            y_min, x_min = mask_coords.min(axis=0)
            y_max, x_max = mask_coords.max(axis=0)
            final_x = cont_x + x_min
            final_y = cont_y + y_min
            final_w = x_max - x_min + 1
            final_h = y_max - y_min + 1

        # Extract piece region with mask applied
        piece_region = region[final_y : final_y + final_h, final_x : final_x + final_w]
        piece_mask_region = part_mask[
            final_y : final_y + final_h, final_x : final_x + final_w
        ]

        # For parts matching, we need solid background, so replace transparent areas with white
        piece = piece_region.copy()
        piece = normalize_background_color(piece)
        white_background = np.ones_like(piece_region) * 255
        mask_3channel = np.stack([piece_mask_region] * 3, axis=2) > 0
        piece = np.where(mask_3channel, piece_region, white_background)

        # Add padding with white background (not blue background from original)
        # This gives the part some breathing room but doesn't include original blue background
        padding = 5
        if padding > 0:
            padded_piece = (
                np.ones(
                    (final_h + 2 * padding, final_w + 2 * padding, 3), dtype=np.uint8
                )
                * 255
            )
            padded_piece[padding : padding + final_h, padding : padding + final_w] = (
                piece
            )
            piece = padded_piece

        if piece.size == 0:
            return None, None

        # Return bbox in region coordinates
        return piece, (final_x, final_y, final_x + final_w, final_y + final_h)

    def _normalize_image(self, image: np.ndarray) -> np.ndarray:
        """Normalize image for matching.

        Args:
            image: Input image

        Returns:
            Normalized image
        """
        if not self.match_color:
            # Convert to grayscale
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            else:
                gray = image

            # Normalize contrast
            normalized = cv2.equalizeHist(gray)

            # Resize to standard size
            standard_size = (100, 100)
            resized = cv2.resize(
                normalized, standard_size, interpolation=cv2.INTER_AREA
            )

            return resized
        else:
            # Preserve color
            if len(image.shape) == 2:
                # Already grayscale, convert to RGB
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)

            # Normalize each channel
            normalized = image.copy()
            for i in range(3):
                normalized[:, :, i] = cv2.equalizeHist(normalized[:, :, i])

            # Resize to standard size
            standard_size = (100, 100)
            resized = cv2.resize(
                normalized, standard_size, interpolation=cv2.INTER_AREA
            )

            return resized

    def _save_quantity_debug_image(
        self,
        page_image: np.ndarray,
        quantities: List[dict],
        page_num: int,
    ):
        """Save debug image showing detected quantity locations.

        Args:
            page_image: Original page image
            quantities: List of quantity data
            page_num: Page number
        """
        annotated = page_image.copy()

        for qty in quantities:
            x, y, w, h = qty["x"], qty["y"], qty["w"], qty["h"]

            # Draw bounding box around quantity
            cv2.rectangle(
                annotated,
                (x, y),
                (x + w, y + h),
                (255, 0, 0),  # Blue
                2,
            )

            # Draw search radius
            center_x = x + w // 2
            center_y = y + h // 2
            cv2.circle(
                annotated,
                (center_x, center_y),
                self.search_radius,
                (0, 255, 0),  # Green
                1,
            )

            # Add label
            cv2.putText(
                annotated,
                qty["text"],
                (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 0, 0),
                1,
            )

        debug_path = (
            self.debug_output_dir / f"instruction_page_{page_num:02d}_quantities.png"
        )
        Image.fromarray(annotated).save(debug_path)

    def _create_debug_visualization(
        self,
        page_image: np.ndarray,
        parts: List[ExtractedPart],
        page_num: int,
    ):
        """Create debug visualization showing extracted parts.

        Args:
            page_image: Original page image
            parts: List of extracted parts
            page_num: Page number
        """
        # Annotated page with bounding boxes
        annotated = page_image.copy()

        for part in parts:
            x0, y0, x1, y1 = part.bbox

            # Draw bounding box
            cv2.rectangle(
                annotated,
                (x0, y0),
                (x1, y1),
                (0, 255, 0),  # Green
                2,
            )

            # Add label
            cv2.putText(
                annotated,
                part.quantity,
                (x0, y0 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
            )

        debug_path = (
            self.debug_output_dir
            / f"instruction_page_{page_num:02d}_parts_detected.png"
        )
        Image.fromarray(annotated).save(debug_path)

        # Create grid of extracted parts
        if len(parts) > 0:
            grid_cols = min(6, len(parts))
            grid_rows = (len(parts) + grid_cols - 1) // grid_cols
            cell_size = 150

            grid = (
                np.ones(
                    (grid_rows * cell_size, grid_cols * cell_size, 3), dtype=np.uint8
                )
                * 255
            )

            for idx, part in enumerate(parts):
                row = idx // grid_cols
                col = idx % grid_cols

                # Resize part image to fit cell
                part_img = part.image
                if len(part_img.shape) == 2:
                    part_img = cv2.cvtColor(part_img, cv2.COLOR_GRAY2RGB)

                h, w = part_img.shape[:2]
                max_size = cell_size - 40
                scale = min(max_size / w, max_size / h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                resized = cv2.resize(part_img, (new_w, new_h))

                # Center in cell
                y_offset = row * cell_size + (cell_size - new_h) // 2 - 10
                x_offset = col * cell_size + (cell_size - new_w) // 2

                grid[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = resized

                # Add label
                label_y = row * cell_size + cell_size - 20
                label_x = col * cell_size + 5
                cv2.putText(
                    grid,
                    f"{part.quantity} (pg{part.page})",
                    (label_x, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    (0, 0, 0),
                    1,
                )

            grid_path = (
                self.debug_output_dir
                / f"instruction_page_{page_num:02d}_parts_grid.png"
            )
            Image.fromarray(grid).save(grid_path)
