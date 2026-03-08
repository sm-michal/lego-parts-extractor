"""Pieces list parser - extracts piece images and numbers from pieces list pages."""

import logging
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

import numpy as np
import pdfplumber
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
import cv2

from .utils import find_poppler_path, configure_tesseract

# Configure Tesseract on Windows
configure_tesseract()

logger = logging.getLogger(__name__)


@dataclass
class PieceReference:
    """Reference data for a LEGO piece."""

    piece_number: str
    image: np.ndarray  # Original image
    normalized_image: np.ndarray  # Preprocessed for matching
    reference_quantity: str  # From pieces list (e.g., "2x")
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    page: int  # Source page number


class PiecesListParser:
    """Parser for LEGO pieces list pages."""

    def __init__(
        self,
        pieces_pdf: Path,
        pieces_pages: List[int],
        dpi: int = 300,
        debug_output_dir: Optional[Path] = None,
        threshold: int = 200,
    ):
        """Initialize pieces list parser.

        Args:
            pieces_pdf: Path to pieces list PDF
            pieces_pages: List of page numbers to parse
            dpi: DPI for PDF to image conversion
            debug_output_dir: Directory for debug output (None to disable)
            threshold: Threshold for piece detection (pixels >= threshold are background)
        """
        self.pieces_pdf = pieces_pdf
        self.pieces_pages = pieces_pages
        self.dpi = dpi
        self.debug_output_dir = debug_output_dir
        self.threshold = threshold
        self.parts_list_output_dir = None
        self.contour_debug_dir = None
        self.logger = logging.getLogger(__name__)
        self.poppler_path = find_poppler_path()

        if self.debug_output_dir:
            self.debug_output_dir.mkdir(parents=True, exist_ok=True)
            # Create subdirectory for parts list extracted images
            self.parts_list_output_dir = self.debug_output_dir / "parts_list_extracted"
            self.parts_list_output_dir.mkdir(parents=True, exist_ok=True)
            # Create subdirectory for contour detection debug images
            self.contour_debug_dir = self.debug_output_dir / "contour_debug"
            self.contour_debug_dir.mkdir(parents=True, exist_ok=True)

    def parse(self) -> Dict[str, PieceReference]:
        """Parse pieces list pages and build reference database.

        Returns:
            Dictionary mapping piece_number -> PieceReference
        """
        reference_database = {}

        for page_num in self.pieces_pages:
            self.logger.info(f"  Parsing page {page_num}...")
            pieces = self._parse_page(page_num)
            self.logger.info(f"    Found {len(pieces)} pieces")

            for piece in pieces:
                if piece.piece_number in reference_database:
                    self.logger.warning(
                        f"    Duplicate piece number: {piece.piece_number} "
                        f"(page {reference_database[piece.piece_number].page} and {piece.page})"
                    )
                else:
                    reference_database[piece.piece_number] = piece

        self.logger.info(f"  Total unique pieces: {len(reference_database)}")
        return reference_database

    def _parse_page(self, page_num: int) -> List[PieceReference]:
        """Parse a single pieces list page.

        Args:
            page_num: Page number (1-indexed)

        Returns:
            List of PieceReference objects
        """
        # Convert PDF page to image
        images = convert_from_path(
            self.pieces_pdf,
            dpi=self.dpi,
            first_page=page_num,
            last_page=page_num,
            poppler_path=self.poppler_path,
        )
        page_image = np.array(images[0])

        # Save debug image
        if self.debug_output_dir:
            debug_path = (
                self.debug_output_dir / f"pieces_page_{page_num:02d}_original.png"
            )
            Image.fromarray(page_image).save(debug_path)

        # Extract text and images from PDF
        pdf_text = self._extract_text_from_pdf(page_num)
        pdf_images, pdf_width, pdf_height = self._extract_images_from_pdf(page_num)

        self.logger.debug(f"    PDF has {len(pdf_images)} images, size {pdf_width}x{pdf_height}")

        # Find piece numbers and quantities from PDF text
        piece_numbers = self._extract_piece_numbers_from_pdf(pdf_text)
        quantities = self._extract_quantities_from_pdf(pdf_text)

        self.logger.debug(
            f"    PDF text found {len(piece_numbers)} piece numbers, {len(quantities)} quantities"
        )

        # Match piece numbers with quantities and extract images
        pieces = []
        for piece_num_data in piece_numbers:
            piece_num = piece_num_data["text"]
            piece_bbox = (
                piece_num_data["x"],
                piece_num_data["y"],
                piece_num_data["x"] + piece_num_data["w"],
                piece_num_data["y"] + piece_num_data["h"],
            )

            # Find quantity above this piece number
            quantity = self._find_quantity_above(piece_num_data, quantities)

            # Extract piece image using PDF image positions
            piece_image = self._extract_piece_from_pdf_image(
                page_image, piece_num_data, pdf_images, pdf_width, pdf_height
            )

            if piece_image is not None:
                # Normalize image for matching
                normalized = self._normalize_image(piece_image)

                piece_ref = PieceReference(
                    piece_number=piece_num,
                    image=piece_image,
                    normalized_image=normalized,
                    reference_quantity=quantity if quantity else "1x",
                    bbox=piece_bbox,
                    page=page_num,
                )
                pieces.append(piece_ref)

                # Save extracted part image to parts_list_extracted folder
                if self.parts_list_output_dir:
                    part_output_path = (
                        self.parts_list_output_dir
                        / f"piece_{piece_num}_{page_num:02d}.png"
                    )
                    Image.fromarray(piece_image).save(part_output_path)

        # Create debug visualization
        if self.debug_output_dir and pieces:
            self._create_debug_visualization(page_image, pieces, page_num)

        return pieces

    def _extract_text_from_pdf(self, page_num: int) -> List[dict]:
        """Extract text with positions from PDF using pdfplumber.

        Args:
            page_num: Page number (1-indexed)

        Returns:
            List of text element dictionaries with text, x, y, w, h
        """
        text_elements = []

        try:
            with pdfplumber.open(self.pieces_pdf) as pdf:
                if page_num - 1 >= len(pdf.pages):
                    return text_elements

                page = pdf.pages[page_num - 1]
                words = page.extract_words()

                for word in words:
                    text_elements.append({
                        "text": word["text"],
                        "x": int(word["x0"]),
                        "y": int(word["top"]),
                        "w": int(word["x1"] - word["x0"]),
                        "h": int(word["bottom"] - word["top"]),
                    })

        except Exception as e:
            self.logger.warning(f"Failed to extract PDF text: {e}")

        return text_elements

    def _extract_images_from_pdf(self, page_num: int) -> Tuple[List[dict], int, int]:
        """Extract images from PDF with positions.

        Args:
            page_num: Page number (1-indexed)

        Returns:
            Tuple of (images list, pdf page width, pdf page height)
        """
        images = []
        pdf_width = 612
        pdf_height = 792

        try:
            with pdfplumber.open(self.pieces_pdf) as pdf:
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

    def _extract_piece_numbers_from_pdf(self, text_elements: List[dict]) -> List[dict]:
        """Extract piece numbers from PDF text elements.

        Args:
            text_elements: List of text element dictionaries from PDF

        Returns:
            List of piece number data dictionaries
        """
        piece_numbers = []

        for elem in text_elements:
            text = elem.get("text", "")
            if not text:
                continue

            match = re.match(r"^(\d{6,7})$", text.strip())
            if match:
                piece_numbers.append({
                    "text": match.group(1),
                    "x": elem["x"],
                    "y": elem["y"],
                    "w": elem["w"],
                    "h": elem["h"],
                })

        return piece_numbers

    def _extract_quantities_from_pdf(self, text_elements: List[dict]) -> List[dict]:
        """Extract quantities (e.g., 1x, 2x) from PDF text elements.

        Args:
            text_elements: List of text element dictionaries from PDF

        Returns:
            List of quantity data dictionaries
        """
        quantities = []

        for elem in text_elements:
            text = elem.get("text", "")
            if not text:
                continue

            match = re.match(r"^(\d+)x$", text.strip(), re.IGNORECASE)
            if match:
                quantities.append({
                    "text": text.strip(),
                    "x": elem["x"],
                    "y": elem["y"],
                    "w": elem["w"],
                    "h": elem["h"],
                })

        return quantities

    def _extract_piece_numbers(self, ocr_data: dict) -> List[dict]:
        """Extract piece numbers (6-7 digit sequences) from OCR data.

        Args:
            ocr_data: pytesseract OCR data dictionary

        Returns:
            List of piece number data dictionaries
        """
        piece_numbers = []

        for i, text in enumerate(ocr_data["text"]):
            if not text or not text.strip():
                continue

            # Look for 6-7 digit numbers
            match = re.match(r"^(\d{6,7})$", text.strip())
            if match:
                piece_numbers.append(
                    {
                        "text": match.group(1),
                        "x": ocr_data["left"][i],
                        "y": ocr_data["top"][i],
                        "w": ocr_data["width"][i],
                        "h": ocr_data["height"][i],
                        "conf": ocr_data["conf"][i],
                    }
                )

        return piece_numbers

    def _mask_out_pdf_text(self, page_image: np.ndarray, page_num: int) -> np.ndarray:
        """Mask out text from PDF to avoid it being detected as part of pieces.

        Args:
            page_image: The page image array
            page_num: Page number (1-indexed)

        Returns:
            Image with text areas filled with white
        """
        result = page_image.copy()

        try:
            with pdfplumber.open(self.pieces_pdf) as pdf:
                if page_num - 1 >= len(pdf.pages):
                    return result

                page = pdf.pages[page_num - 1]
                text_elements = page.extract_words()

                if not text_elements:
                    return result

                for word in text_elements:
                    x0 = int(word["x0"])
                    top = int(word["top"])
                    x1 = int(word["x1"])
                    y1 = int(word["bottom"])

                    x0 = max(0, x0)
                    top = max(0, top)
                    x1 = min(result.shape[1], x1)
                    y1 = min(result.shape[0], y1)

                    if y1 > top and x1 > x0:
                        result[top:y1, x0:x1] = 255

        except Exception as e:
            self.logger.warning(f"Failed to extract PDF text for masking: {e}")

        return result

    def _extract_quantities(self, ocr_data: dict) -> List[dict]:
        """Extract quantities (e.g., 1x, 2x, etc.) from OCR data.

        Args:
            ocr_data: pytesseract OCR data dictionary

        Returns:
            List of quantity data dictionaries
        """
        quantities = []

        for i, text in enumerate(ocr_data["text"]):
            if not text or not text.strip():
                continue

            # Look for patterns like "1x", "2x", "10x", etc.
            match = re.match(r"^(\d+)x$", text.strip(), re.IGNORECASE)
            if match:
                quantities.append(
                    {
                        "text": text.strip().lower(),
                        "x": ocr_data["left"][i],
                        "y": ocr_data["top"][i],
                        "w": ocr_data["width"][i],
                        "h": ocr_data["height"][i],
                        "conf": ocr_data["conf"][i],
                    }
                )

        return quantities

    def _find_quantity_above(
        self,
        piece_num_data: dict,
        quantities: List[dict],
        max_horizontal_distance: int = 50,
        max_vertical_distance: int = 40,
    ) -> Optional[str]:
        """Find quantity indicator above a piece number.

        Args:
            piece_num_data: Piece number data dictionary
            quantities: List of quantity data dictionaries
            max_horizontal_distance: Maximum horizontal distance in pixels
            max_vertical_distance: Maximum vertical distance above (in pixels)

        Returns:
            Quantity string (e.g., "2x") or None if not found
        """
        piece_x = piece_num_data["x"] + piece_num_data["w"] / 2
        piece_y = piece_num_data["y"]

        # Find closest quantity above
        best_match = None
        best_distance = float("inf")

        for qty in quantities:
            qty_x = qty["x"] + qty["w"] / 2
            qty_y = qty["y"] + qty["h"]

            # Must be above the piece number
            if qty_y > piece_y:
                continue

            # Check horizontal and vertical distance
            h_dist = abs(qty_x - piece_x)
            v_dist = piece_y - qty_y

            if h_dist <= max_horizontal_distance and v_dist <= max_vertical_distance:
                # Calculate total distance
                total_dist = (h_dist**2 + v_dist**2) ** 0.5
                if total_dist < best_distance:
                    best_distance = total_dist
                    best_match = qty["text"]

        return best_match

    def _extract_piece_from_pdf_image(
        self,
        page_image: np.ndarray,
        piece_num_data: dict,
        pdf_images: List[dict],
        pdf_width: int,
        pdf_height: int
    ) -> Optional[np.ndarray]:
        """Extract piece image using PDF image positions.

        Args:
            page_image: Full page image (rendered)
            piece_num_data: Piece number data from PDF text
            pdf_images: List of image data from PDF
            pdf_width: PDF page width in points
            pdf_height: PDF page height in points

        Returns:
            Cropped piece image or None
        """
        if not pdf_images:
            return None

        piece_x = piece_num_data["x"]
        piece_y = piece_num_data["y"]

        img_width = page_image.shape[1]
        img_height = page_image.shape[0]

        scale_x = img_width / pdf_width
        scale_y = img_height / pdf_height

        def image_distance(img):
            img_center_x = (img["x0"] + img["x1"]) / 2
            img_bottom_y = pdf_height - img["y0"]
            h_dist = abs(img_center_x - piece_x)
            v_dist = piece_y - img_bottom_y
            if v_dist < 0:
                v_dist = abs(v_dist) * 10
            return (h_dist ** 2 + v_dist ** 2) ** 0.5

        pdf_images_sorted = sorted(pdf_images, key=image_distance)
        best_img = pdf_images_sorted[0]

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

        white_bg = np.ones_like(piece_image) * 255
        piece_image = np.where(piece_image < 240, piece_image, white_bg)

        return piece_image

    def _extract_piece_image(
        self,
        page_image: np.ndarray,
        piece_num_data: dict,
        search_height: int = 120,
        search_width: int = 60,
    ) -> Optional[np.ndarray]:
        """Extract piece image above piece number with adaptive region expansion.

        Args:
            page_image: Full page image
            piece_num_data: Piece number data dictionary
            search_height: Initial height to search above number (pixels)
            search_width: Initial width to search on each side (pixels)

        Returns:
            Piece image as numpy array, or None if extraction fails
        """
        piece_num_center_x = piece_num_data["x"] + piece_num_data["w"] / 2
        piece_num_top_y = piece_num_data["y"]

        left_mult = 1.0
        right_mult = 1.0
        up_mult = 2.0
        down_mult = 0.8
        mult_increment = 0.4
        max_iterations = 5

        for iteration in range(max_iterations):
            x0 = max(0, int(piece_num_center_x - search_width * left_mult))
            y0 = max(0, int(piece_num_top_y - search_height * up_mult))
            x1 = min(page_image.shape[1], int(piece_num_center_x + search_width * right_mult))
            y1 = min(page_image.shape[0], int(piece_num_top_y + search_height * down_mult))

            if y1 <= y0 or x1 <= x0:
                return None

            region = page_image[y0:y1, x0:x1]

            if region.size == 0:
                return None

            region_piece_num_x = piece_num_center_x - x0
            region_piece_num_y = piece_num_top_y - y0
            debug_info = None
            if self.contour_debug_dir:
                debug_info = {
                    "piece_num": piece_num_data["text"],
                    "iteration": iteration,
                    "region_coords": (x0, y0, x1, y1)
                }
            piece_image, bbox = self._find_piece_in_region(
                region, exclude_bottom_text=True,
                piece_num_x=region_piece_num_x, piece_num_y=region_piece_num_y,
                debug_info=debug_info
            )

            if bbox is None:
                return piece_image

            region_h, region_w = region.shape[:2]
            edge_threshold = 2
            touches_left = bbox["x"] <= edge_threshold
            touches_right = bbox["x"] + bbox["w"] >= region_w - edge_threshold
            touches_top = bbox["y"] <= edge_threshold
            touches_bottom = bbox["y"] + bbox["h"] >= region_h - edge_threshold

            if not (touches_left or touches_right or touches_top or touches_bottom):
                break

            if touches_left:
                left_mult += mult_increment
            if touches_right:
                right_mult += mult_increment
            if touches_top:
                up_mult += mult_increment
            if touches_bottom:
                down_mult += mult_increment

        return piece_image

    def _find_piece_in_region(
        self, region: np.ndarray, exclude_bottom_text: bool = False,
        piece_num_x: float = None, piece_num_y: float = None,
        debug_info: dict = None
    ) -> Tuple[Optional[np.ndarray], Optional[dict]]:
        """Find piece boundaries within a region using background filtering.

        Args:
            region: Image region to search
            exclude_bottom_text: If True, exclude small contours near the bottom (quantity text)
            piece_num_x: X position of piece number in region coords (for closest contour)
            piece_num_y: Y position of piece number in region coords (for closest contour)
            debug_info: Dict with debug info for saving contour images

        Returns:
            Tuple of (cropped piece image with white background or original region if detection fails,
                     bbox dict with keys x, y, w, h or None if detection fails)
        """
        # Convert to grayscale if needed
        if len(region.shape) == 3:
            gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        else:
            gray = region
            region = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

        # Apply threshold to find foreground (piece)
        # Assuming white background - anything not white is part of the piece
        _, binary = cv2.threshold(gray, self.threshold, 255, cv2.THRESH_BINARY_INV)

        # This binary mask has piece=255 (white), background=0 (black)
        part_mask = binary

        # Morphological operations to clean up mask
        kernel = np.ones((3, 3), np.uint8)
        part_mask = cv2.morphologyEx(part_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        part_mask = cv2.morphologyEx(part_mask, cv2.MORPH_OPEN, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(
            part_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            # No clear boundaries, return whole region
            return region, None

        # Filter contours to find the piece (not small text)
        region_height, region_width = region.shape[:2]
        valid_contours = []

        for contour in contours:
            area = cv2.contourArea(contour)
            x, y, w, h = cv2.boundingRect(contour)

            # Skip very small contours (likely text or noise)
            if area < 100:
                continue

            # If exclude_bottom_text, only consider contours that aren't purely in the bottom area
            # This excludes quantity text like "2x", "5x" at the very bottom
            if exclude_bottom_text:
                contour_top = y
                # Only exclude contours that START in the bottom 15% (likely text only)
                if contour_top > region_height * 0.85:
                    continue

            valid_contours.append((area, contour))

        if not valid_contours:
            # No valid contours found - try returning top 80% of region to exclude text
            if exclude_bottom_text:
                crop_height = int(region_height * 0.8)
                return region[0:crop_height, :], None
            return region, None

        # Find contour closest to piece number position (if provided), otherwise largest
        if piece_num_x is not None and piece_num_y is not None:
            def contour_distance(contour_item):
                _, contour = contour_item
                cx, cy, cw, ch = cv2.boundingRect(contour)
                cont_center_x = cx + cw / 2
                cont_center_y = cy + ch / 2
                return ((cont_center_x - piece_num_x) ** 2 + (cont_center_y - piece_num_y) ** 2) ** 0.5
            _, best_contour = min(valid_contours, key=contour_distance)
        else:
            _, best_contour = max(valid_contours, key=lambda x: x[0])

        # Save debug image with binary and contours
        if debug_info:
            self._save_contour_debug(
                region, part_mask, valid_contours, best_contour,
                piece_num_x, piece_num_y, debug_info
            )

        # Get bounding box of selected contour
        cont_x, cont_y, cont_w, cont_h = cv2.boundingRect(best_contour)

        # If contour is very wide, try to split by vertical gaps
        if cont_w > cont_h * 1.5 and cont_w > 50:
            sub_bboxes = self._split_by_vertical_gaps(part_mask, cont_x, cont_y, cont_w, cont_h)
            if len(sub_bboxes) > 1 and piece_num_x is not None:
                best_sub = min(sub_bboxes, key=lambda b: abs((b[0] + b[2]/2) - piece_num_x))
                cont_x, cont_y, cont_w, cont_h = best_sub

        # Extract the contour region
        contour_region_mask = part_mask[
            cont_y : cont_y + cont_h, cont_x : cont_x + cont_w
        ]

        # Find tight bbox within the contour region based on actual mask pixels
        mask_coords = np.argwhere(contour_region_mask > 0)
        if len(mask_coords) == 0:
            # Fall back to full contour bbox
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

        # Replace background with white
        piece = piece_region.copy()
        white_background = np.ones_like(piece_region) * 255
        mask_3channel = np.stack([piece_mask_region] * 3, axis=2) > 0
        piece = np.where(mask_3channel, piece_region, white_background)

        # Add padding with white background
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
            final_x -= padding
            final_y -= padding
            final_w += 2 * padding
            final_h += 2 * padding

        bbox = {"x": final_x, "y": final_y, "w": final_w, "h": final_h}
        return piece if piece.size > 0 else region, bbox

    def _split_by_vertical_gaps(
        self, part_mask: np.ndarray, x: int, y: int, w: int, h: int
    ) -> List[Tuple[int, int, int, int]]:
        """Split a bounding box by finding vertical gaps (white columns).

        Args:
            part_mask: Binary mask with piece=255, background=0
            x, y, w, h: Bounding box of the contour to split

        Returns:
            List of (x, y, w, h) tuples for each sub-region
        """
        region = part_mask[y:y+h, x:x+w]

        col_white_ratio = []
        for col in range(w):
            white_pixels = np.sum(region[:, col] > 0)
            ratio = white_pixels / h
            col_white_ratio.append(ratio)

        gap_cols = []
        min_gap_width = 3
        current_gap_start = None
        for i, ratio in enumerate(col_white_ratio):
            if ratio < 0.1:
                if current_gap_start is None:
                    current_gap_start = i
            else:
                if current_gap_start is not None:
                    gap_width = i - current_gap_start
                    if gap_width >= min_gap_width:
                        gap_cols.append((current_gap_start, i))
                    current_gap_start = None
        if current_gap_start is not None:
            gap_width = w - current_gap_start
            if gap_width >= min_gap_width:
                gap_cols.append((current_gap_start, w))

        if len(gap_cols) == 0:
            return [(x, y, w, h)]

        split_points = [0] + [g[1] for g in gap_cols] + [w]

        sub_bboxes = []
        for i in range(len(split_points) - 1):
            sub_x = split_points[i]
            sub_w = split_points[i + 1] - sub_x
            sub_region = region[:, sub_x:sub_x+sub_w]
            rows_with_white = np.where(np.any(sub_region > 0, axis=1))[0]
            if len(rows_with_white) > 0:
                sub_y = rows_with_white[0]
                sub_h = rows_with_white[-1] - sub_y + 1
                sub_bboxes.append((x + sub_x, y + sub_y, sub_w, sub_h))

        return sub_bboxes if sub_bboxes else [(x, y, w, h)]

    def _save_contour_debug(
        self, region: np.ndarray, part_mask: np.ndarray,
        valid_contours: List, best_contour,
        piece_num_x: float, piece_num_y: float,
        debug_info: dict
    ):
        """Save debug image showing binary mask and contours."""
        piece_num = debug_info["piece_num"]
        iteration = debug_info["iteration"]
        region_coords = debug_info["region_coords"]

        inverted_mask = 255 - part_mask
        debug_img = cv2.cvtColor(inverted_mask, cv2.COLOR_GRAY2BGR)

        for area, contour in valid_contours:
            x, y, w, h = cv2.boundingRect(contour)
            color = (0, 255, 0) if contour is best_contour else (0, 0, 255)
            cv2.rectangle(debug_img, (x, y), (x + w, y + h), color, 2)

        if piece_num_x is not None and piece_num_y is not None:
            cv2.circle(debug_img, (int(piece_num_x), int(piece_num_y)), 8, (255, 0, 0), 2)

        filename = f"piece_{piece_num}_iter{iteration}_region{region_coords[0]}_{region_coords[1]}.png"
        filepath = self.contour_debug_dir / filename
        cv2.imwrite(str(filepath), debug_img)

    def _normalize_image(self, image: np.ndarray) -> np.ndarray:
        """Normalize image for matching.

        Args:
            image: Input image

        Returns:
            Normalized image
        """
        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            gray = image

        # Normalize contrast
        normalized = cv2.equalizeHist(gray)

        # Resize to standard size for faster matching
        standard_size = (100, 100)
        resized = cv2.resize(normalized, standard_size, interpolation=cv2.INTER_AREA)

        return resized

    def _create_debug_visualization(
        self,
        page_image: np.ndarray,
        pieces: List[PieceReference],
        page_num: int,
    ):
        """Create debug visualization showing extracted pieces.

        Args:
            page_image: Original page image
            pieces: List of extracted pieces
            page_num: Page number
        """
        # Create annotated image with bounding boxes
        annotated = page_image.copy()

        for piece in pieces:
            x0, y0, x1, y1 = piece.bbox
            # Draw bounding box around the extraction region
            cv2.rectangle(
                annotated,
                (int(x0), int(y0) - 80),
                (int(x1), int(y0)),
                (0, 255, 0),  # Green box
                2,
            )
            # Add label
            cv2.putText(
                annotated,
                piece.piece_number,
                (int(x0), int(y0) + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 0, 0),
                1,
            )

        # Save annotated image
        debug_path = self.debug_output_dir / f"pieces_page_{page_num:02d}_annotated.png"
        Image.fromarray(annotated).save(debug_path)

        # Create grid of extracted pieces with boxes showing extraction boundaries
        if len(pieces) > 0:
            grid_cols = 8
            grid_rows = (len(pieces) + grid_cols - 1) // grid_cols
            cell_size = 120

            grid = (
                np.ones(
                    (grid_rows * cell_size, grid_cols * cell_size, 3), dtype=np.uint8
                )
                * 255
            )

            for idx, piece in enumerate(pieces):
                row = idx // grid_cols
                col = idx % grid_cols

                # Get piece image
                piece_img = piece.image
                if len(piece_img.shape) == 2:
                    piece_img = cv2.cvtColor(piece_img, cv2.COLOR_GRAY2RGB)

                h, w = piece_img.shape[:2]
                max_size = cell_size - 40
                scale = min(max_size / w, max_size / h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                resized = cv2.resize(piece_img, (new_w, new_h))

                # Center in cell
                y_offset = row * cell_size + (cell_size - new_h) // 2 - 10
                x_offset = col * cell_size + (cell_size - new_w) // 2

                # Place the extracted part
                grid[y_offset : y_offset + new_h, x_offset : x_offset + new_w] = resized

                # Draw green border around the extracted part to show extraction boundary
                cv2.rectangle(
                    grid,
                    (x_offset, y_offset),
                    (x_offset + new_w, y_offset + new_h),
                    (0, 255, 0),  # Green border
                    1,
                )

                # Add label
                label_y = row * cell_size + cell_size - 15
                label_x = col * cell_size + 5
                cv2.putText(
                    grid,
                    f"{piece.piece_number}",
                    (label_x, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.3,
                    (0, 0, 0),
                    1,
                )

            grid_path = self.debug_output_dir / f"pieces_page_{page_num:02d}_grid.png"
            Image.fromarray(grid).save(grid_path)
