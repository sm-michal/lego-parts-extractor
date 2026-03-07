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
    ):
        """Initialize pieces list parser.

        Args:
            pieces_pdf: Path to pieces list PDF
            pieces_pages: List of page numbers to parse
            dpi: DPI for PDF to image conversion
            debug_output_dir: Directory for debug output (None to disable)
        """
        self.pieces_pdf = pieces_pdf
        self.pieces_pages = pieces_pages
        self.dpi = dpi
        self.debug_output_dir = debug_output_dir
        self.parts_list_output_dir = None
        self.logger = logging.getLogger(__name__)
        self.poppler_path = find_poppler_path()

        if self.debug_output_dir:
            self.debug_output_dir.mkdir(parents=True, exist_ok=True)
            # Create subdirectory for parts list extracted images
            self.parts_list_output_dir = self.debug_output_dir / "parts_list_extracted"
            self.parts_list_output_dir.mkdir(parents=True, exist_ok=True)

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

        # Extract text with positions using pytesseract
        ocr_data = pytesseract.image_to_data(
            page_image,
            output_type=pytesseract.Output.DICT,
        )

        # Find piece numbers and quantities
        piece_numbers = self._extract_piece_numbers(ocr_data)
        quantities = self._extract_quantities(ocr_data)

        self.logger.debug(
            f"    OCR found {len(piece_numbers)} piece numbers, {len(quantities)} quantities"
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

            # Find quantity above this piece number (within ±50px horizontal, 0-40px above)
            quantity = self._find_quantity_above(piece_num_data, quantities)

            # Extract piece image above the number (within ±50px horizontal, 10-80px above)
            piece_image = self._extract_piece_image(page_image, piece_num_data)

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
                        / f"piece_{page_num:02d}_{piece_num}.png"
                    )
                    Image.fromarray(piece_image).save(part_output_path)

        # Create debug visualization
        if self.debug_output_dir and pieces:
            self._create_debug_visualization(page_image, pieces, page_num)

        return pieces

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

    def _extract_piece_image(
        self,
        page_image: np.ndarray,
        piece_num_data: dict,
        search_height: int = 120,
        search_width: int = 60,
    ) -> Optional[np.ndarray]:
        """Extract piece image above piece number.

        Args:
            page_image: Full page image
            piece_num_data: Piece number data dictionary
            search_height: Height to search above number (pixels)
            search_width: Width to search on each side (pixels)

        Returns:
            Piece image as numpy array, or None if extraction fails
        """
        # Define search region
        # The piece number OCR box includes quantity text (e.g., "2x") below the actual number
        # We need to search above the entire piece number box to avoid including text
        piece_num_center_x = piece_num_data["x"] + piece_num_data["w"] / 2
        piece_num_top_y = piece_num_data["y"]

        # Search region should be above the piece number box
        x0 = max(0, int(piece_num_center_x - search_width))
        y0 = max(0, int(piece_num_top_y - search_height))
        x1 = min(page_image.shape[1], int(piece_num_center_x + search_width))
        # Extend slightly below the piece number top to capture full part
        # but stay above the quantity text which is typically 15-20px below
        y1 = min(page_image.shape[0], int(piece_num_top_y + 10))

        if y1 <= y0 or x1 <= x0:
            return None

        # Extract region
        region = page_image[y0:y1, x0:x1]

        if region.size == 0:
            return None

        # Find piece boundaries using edge detection
        piece_image = self._find_piece_in_region(region, exclude_bottom_text=True)

        return piece_image

    def _find_piece_in_region(
        self, region: np.ndarray, exclude_bottom_text: bool = False
    ) -> Optional[np.ndarray]:
        """Find piece boundaries within a region using background filtering.

        Args:
            region: Image region to search
            exclude_bottom_text: If True, exclude small contours near the bottom (quantity text)

        Returns:
            Cropped piece image with white background or original region if detection fails
        """
        # Convert to grayscale if needed
        if len(region.shape) == 3:
            gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
        else:
            gray = region
            region = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

        # Apply threshold to find foreground (piece)
        # Assuming white background - anything not white is part of the piece
        _, binary = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)

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
            return region

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
                return region[0:crop_height, :]
            return region

        # Find largest valid contour (the piece)
        largest_area, largest_contour = max(valid_contours, key=lambda x: x[0])

        # Get bounding box of contour, then refine using mask
        cont_x, cont_y, cont_w, cont_h = cv2.boundingRect(largest_contour)

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

        return piece if piece.size > 0 else region

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
