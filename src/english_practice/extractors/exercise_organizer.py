from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm


from english_practice.models import (
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
)


class ExerciseOrganizer:
    """Organize exercise images by extracting individual exercises from pages."""

    def _extract_from_page(
        self,
        image_path: Path,
    ) -> list[np.ndarray]:
        """Extract exercises from a single page using blue/teal box detection."""
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")

        img = self._crop_image(img)

        height, width = img.shape[:2]

        search_width = int(width * EXERCISE_SEARCH_WIDTH_RATIO)
        left_region = img[:, :search_width]

        boxes = self._detect_contours(left_region)

        boxes.sort(key=lambda b: b["y"])

        if not boxes:
            return [img]

        exercises: list[np.ndarray] = []

        for i, box in enumerate(boxes):
            start_y = max(0, box["y"] - EXERCISE_PADDING)

            if i < len(boxes) - 1:
                end_y = boxes[i + 1]["y"] - EXERCISE_PADDING
            else:
                end_y = height

            exercise_img = img[start_y:end_y, 0:width]

            if exercise_img.shape[0] < EXERCISE_MIN_HEIGHT:
                continue

            exercises.append(exercise_img)

        if not exercises:
            return [img]

        return exercises

    def _detect_contours(
        self,
        region: np.ndarray,
    ) -> list[dict[str, int]]:
        """Detect exercise header boxes using HSV color filtering and contour detection."""
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        lower_teal = np.array(
            [EXERCISE_HSV_LOWER_HUE, EXERCISE_HSV_LOWER_SAT, EXERCISE_HSV_LOWER_VAL]
        )
        upper_teal = np.array(
            [EXERCISE_HSV_UPPER_HUE, EXERCISE_HSV_UPPER_SAT, EXERCISE_HSV_UPPER_VAL]
        )
        mask = cv2.inRange(hsv, lower_teal, upper_teal)

        kernel = np.ones((EXERCISE_KERNEL_SIZE, EXERCISE_KERNEL_SIZE), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=EXERCISE_DILATE_ITERATIONS)
        mask = cv2.erode(mask, kernel, iterations=EXERCISE_ERODE_ITERATIONS)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)

            if (
                EXERCISE_BOX_MIN_WIDTH < w < EXERCISE_BOX_MAX_WIDTH
                and EXERCISE_BOX_MIN_HEIGHT < h < EXERCISE_BOX_MAX_HEIGHT
                and area > EXERCISE_MIN_AREA
            ):
                boxes.append({"x": x, "y": y, "w": w, "h": h})

        return boxes

    def _crop_image(self, img: np.ndarray) -> np.ndarray:
        """Crop the image based on configured margins."""
        original_height, original_width = img.shape[:2]

        if (
            EXERCISE_CROP_TOP > 0
            or EXERCISE_CROP_BOTTOM > 0
            or EXERCISE_CROP_LEFT > 0
            or EXERCISE_CROP_RIGHT > 0
        ):
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
            img = img[EXERCISE_CROP_TOP:bottom_limit, EXERCISE_CROP_LEFT:right_limit]

        return img

    def organize(
        self,
        file_path: Path,
        output_dir: Path,
    ) -> list[Path]:
        """
        Extract and organize exercises from page images.

        Args:
            file_path: Directory containing page images (1.png, 2.png...)
            output_dir: Destination directory for organized exercises

        Returns:
            List of created exercise paths
        """
        file_path = Path(file_path)
        output_dir = Path(output_dir)

        if not file_path.exists():
            raise FileNotFoundError(f"Source directory not found: {file_path}")

        page_files = sorted(
            file_path.glob("*.png"),
            key=lambda p: int(p.stem),
        )

        if not page_files:
            raise ValueError(f"No PNG files found in {file_path}")

        output_paths: list[Path] = []

        for page_path in tqdm(page_files, desc="Processing pages"):
            page_num = int(page_path.stem)
            exercises = self._extract_from_page(page_path)

            if not exercises:
                continue

            page_dir = output_dir / str(page_num)
            page_dir.mkdir(parents=True, exist_ok=True)

            for i, exercise_img in enumerate(exercises, start=1):
                output_path = page_dir / f"{page_num}.{i}.png"
                cv2.imwrite(str(output_path), exercise_img)
                output_paths.append(output_path)

        return output_paths
