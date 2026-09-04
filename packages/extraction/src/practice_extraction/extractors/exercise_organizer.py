from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np
from practice_core.errors import PracticeError
from practice_runtime.logging import get_logger
from tqdm import tqdm

from practice_extraction.constants import (
    BOTTOM_WHITE_MARGIN,
    BOTTOM_WHITE_MIN_RATIO,
    BOTTOM_WHITE_SEARCH_HEIGHT_RATIO,
    BOTTOM_WHITE_THRESHOLD,
    EXERCISE_BOX_MAX_HEIGHT,
    EXERCISE_BOX_MAX_WIDTH,
    EXERCISE_BOX_MIN_HEIGHT,
    EXERCISE_BOX_MIN_WIDTH,
    EXERCISE_CROP_BOTTOM,
    EXERCISE_CROP_LEFT,
    EXERCISE_CROP_RIGHT,
    EXERCISE_CROP_TOP,
    EXERCISE_DILATE_ITERATIONS,
    EXERCISE_ERODE_ITERATIONS,
    EXERCISE_HSV_LOWER_HUE,
    EXERCISE_HSV_LOWER_SAT,
    EXERCISE_HSV_LOWER_VAL,
    EXERCISE_HSV_UPPER_HUE,
    EXERCISE_HSV_UPPER_SAT,
    EXERCISE_HSV_UPPER_VAL,
    EXERCISE_KERNEL_SIZE,
    EXERCISE_MIN_AREA,
    EXERCISE_MIN_HEIGHT,
    EXERCISE_PADDING,
    EXERCISE_SEARCH_WIDTH_RATIO,
    MIN_MEANINGFUL_CROP_PIXELS,
)

logger = get_logger(__name__)


class UnusableSlice(PracticeError):
    """A page produced a slice too small to be an exercise."""


class BoundingBox(NamedTuple):
    """Represents a bounding box with position and dimensions."""

    x: int
    y: int
    w: int
    h: int


class HSVRange(NamedTuple):
    """Represents an HSV color range for filtering."""

    lower: np.ndarray
    upper: np.ndarray


class ExerciseOrganizer:
    """Organize exercise images by extracting individual exercises from pages."""

    @staticmethod
    def _create_hsv_range(
        lower_h: int,
        lower_s: int,
        lower_v: int,
        upper_h: int,
        upper_s: int,
        upper_v: int,
    ) -> HSVRange:
        """Create HSV range arrays for color filtering."""
        lower = np.array([lower_h, lower_s, lower_v])
        upper = np.array([upper_h, upper_s, upper_v])
        return HSVRange(lower, upper)

    @staticmethod
    def _create_hsv_mask(
        region: np.ndarray,
        hsv_range: HSVRange,
        kernel_size: int | None = None,
        dilate_iterations: int = 0,
        erode_iterations: int = 0,
    ) -> np.ndarray:
        """Create an HSV-based binary mask for color detection."""
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, hsv_range.lower, hsv_range.upper)

        if kernel_size and (dilate_iterations > 0 or erode_iterations > 0):
            kernel = np.ones((kernel_size, kernel_size), np.uint8)
            if dilate_iterations > 0:
                mask = cv2.dilate(mask, kernel, iterations=dilate_iterations)
            if erode_iterations > 0:
                mask = cv2.erode(mask, kernel, iterations=erode_iterations)

        return mask

    def _extract_from_page(
        self,
        image_path: Path,
    ) -> list[np.ndarray]:
        """Extract exercises from a single page using blue/teal box detection."""
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")

        img = self._crop_image(img)

        search_width = int(img.shape[1] * EXERCISE_SEARCH_WIDTH_RATIO)
        left_region = img[:, :search_width]
        boxes = self._detect_exercise_headers(left_region)

        if not boxes:
            return [img]

        exercises = self._split_into_exercises(img, boxes)

        return exercises if exercises else [img]

    def _detect_exercise_headers(self, region: np.ndarray) -> list[BoundingBox]:
        """Return the header boxes found by HSV colour and contour."""
        hsv_range = self._create_hsv_range(
            EXERCISE_HSV_LOWER_HUE,
            EXERCISE_HSV_LOWER_SAT,
            EXERCISE_HSV_LOWER_VAL,
            EXERCISE_HSV_UPPER_HUE,
            EXERCISE_HSV_UPPER_SAT,
            EXERCISE_HSV_UPPER_VAL,
        )

        mask = self._create_hsv_mask(
            region,
            hsv_range,
            kernel_size=EXERCISE_KERNEL_SIZE,
            dilate_iterations=EXERCISE_DILATE_ITERATIONS,
            erode_iterations=EXERCISE_ERODE_ITERATIONS,
        )

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes: list[BoundingBox] = []
        for cnt in contours:
            box = BoundingBox(*cv2.boundingRect(cnt))
            area = cv2.contourArea(cnt)

            if self._is_valid_exercise_header(box, area):
                boxes.append(box)

        return sorted(boxes, key=lambda b: b.y)

    @staticmethod
    def _is_valid_exercise_header(box: BoundingBox, area: float) -> bool:
        """Check if a bounding box matches the expected exercise header dimensions."""
        return (
            EXERCISE_BOX_MIN_WIDTH < box.w < EXERCISE_BOX_MAX_WIDTH
            and EXERCISE_BOX_MIN_HEIGHT < box.h < EXERCISE_BOX_MAX_HEIGHT
            and area > EXERCISE_MIN_AREA
        )

    def _split_into_exercises(
        self,
        img: np.ndarray,
        boxes: list[BoundingBox],
    ) -> list[np.ndarray]:
        """Split page image into individual exercises based on header positions."""
        height, width = img.shape[:2]
        exercises = []

        for i, box in enumerate(boxes):
            start_y = max(0, box.y - EXERCISE_PADDING)

            is_last = i == len(boxes) - 1
            end_y = height if is_last else boxes[i + 1].y - EXERCISE_PADDING

            exercise_img = img[start_y:end_y, 0:width]

            # Dropping a slice renumbers the page, and every later stage keys on that.
            if exercise_img.shape[0] < EXERCISE_MIN_HEIGHT:
                raise UnusableSlice(
                    f"header {i + 1} of {len(boxes)} yielded a "
                    f"{exercise_img.shape[0]}px slice, under the "
                    f"{EXERCISE_MIN_HEIGHT}px minimum"
                )

            if is_last:
                exercise_img = self._crop_bottom_white_space(exercise_img)

            exercises.append(exercise_img)

        return exercises

    def _crop_bottom_white_space(self, img: np.ndarray) -> np.ndarray:
        """Detect and crop white space from the bottom of the image."""
        height = img.shape[0]

        search_height = int(height * BOTTOM_WHITE_SEARCH_HEIGHT_RATIO)
        start_y = height - search_height

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        content_end_y = None

        for y in range(height - 1, start_y - 1, -1):
            row = gray[y, :]

            white_pixels = np.sum(row >= BOTTOM_WHITE_THRESHOLD)
            white_ratio = white_pixels / len(row)

            if white_ratio < BOTTOM_WHITE_MIN_RATIO:
                content_end_y = y
                break

        if content_end_y is not None:
            crop_y = content_end_y + BOTTOM_WHITE_MARGIN

            removed_pixels = height - crop_y
            if removed_pixels > MIN_MEANINGFUL_CROP_PIXELS:
                return img[:crop_y, :]

        return img

    def _crop_image(self, img: np.ndarray) -> np.ndarray:
        """Crop the image based on configured margins."""
        original_height, original_width = img.shape[:2]

        if not any(
            [
                EXERCISE_CROP_TOP,
                EXERCISE_CROP_BOTTOM,
                EXERCISE_CROP_LEFT,
                EXERCISE_CROP_RIGHT,
            ]
        ):
            return img

        bottom_limit = (
            original_height - EXERCISE_CROP_BOTTOM
            if EXERCISE_CROP_BOTTOM > 0
            else original_height
        )
        right_limit = (
            original_width - EXERCISE_CROP_RIGHT
            if EXERCISE_CROP_RIGHT > 0
            else original_width
        )

        return img[EXERCISE_CROP_TOP:bottom_limit, EXERCISE_CROP_LEFT:right_limit]

    def organize(
        self,
        file_path: Path,
        output_dir: Path,
    ) -> list[Path]:
        """Extract and organize exercises from page images."""
        file_path = Path(file_path)
        output_dir = Path(output_dir)

        if not file_path.exists():
            raise FileNotFoundError(f"Source directory not found: {file_path}")

        page_files = self._get_sorted_page_files(file_path)

        if not page_files:
            raise ValueError(f"No PNG files found in {file_path}")

        return self._process_pages(page_files, output_dir)

    @staticmethod
    def _get_sorted_page_files(file_path: Path) -> list[Path]:
        """Get sorted list of page image files."""
        return sorted(
            file_path.glob("*.png"),
            key=lambda p: int(p.stem),
        )

    def _process_pages(
        self,
        page_files: list[Path],
        output_dir: Path,
    ) -> list[Path]:
        """Process all page files and save organized exercises."""
        output_paths = []

        refused: list[int] = []

        for page_path in tqdm(page_files, desc="Processing pages"):
            page_num = int(page_path.stem)
            # A page with no detected header is kept whole rather than dropped.
            try:
                exercises = self._extract_from_page(page_path)
            except UnusableSlice as exc:
                # The gap stays visible to later stages instead of renumbering.
                refused.append(page_num)
                logger.warning("page_refused", page=page_num, reason=str(exc))
                continue

            page_output_paths = self._save_exercises(exercises, output_dir, page_num)
            output_paths.extend(page_output_paths)

        if refused:
            logger.warning("pages_need_attention", pages=refused, count=len(refused))

        return output_paths

    @staticmethod
    def _save_exercises(
        exercises: list[np.ndarray],
        output_dir: Path,
        page_num: int,
    ) -> list[Path]:
        """Save exercises to disk."""
        page_dir = output_dir / str(page_num)
        page_dir.mkdir(parents=True, exist_ok=True)

        output_paths = []
        for i, exercise_img in enumerate(exercises, start=1):
            output_path = page_dir / f"{page_num}.{i}.png"
            if not cv2.imwrite(str(output_path), exercise_img):
                raise OSError(f"could not write exercise image: {output_path}")
            output_paths.append(output_path)

        return output_paths
