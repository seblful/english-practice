"""Tests for ExerciseOrganizer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.english_practice.extractors.exercise_organizer import (
    BoundingBox,
    ExerciseOrganizer,
    HSVRange,
)


class TestBoundingBox:
    """Tests for BoundingBox NamedTuple."""

    def test_fields(self) -> None:
        box = BoundingBox(10, 20, 100, 50)
        assert box.x == 10
        assert box.y == 20
        assert box.w == 100
        assert box.h == 50


class TestHSVRange:
    """Tests for HSVRange NamedTuple."""

    def test_fields(self) -> None:
        lower = np.array([0, 0, 0])
        upper = np.array([180, 255, 255])
        r = HSVRange(lower, upper)
        assert np.array_equal(r.lower, lower)
        assert np.array_equal(r.upper, upper)


class TestExerciseOrganizer:
    """Tests for ExerciseOrganizer."""

    def test_create_hsv_range(self) -> None:
        result = ExerciseOrganizer._create_hsv_range(0, 50, 50, 180, 255, 255)
        assert isinstance(result, HSVRange)
        assert np.array_equal(result.lower, np.array([0, 50, 50]))
        assert np.array_equal(result.upper, np.array([180, 255, 255]))

    @patch("cv2.cvtColor")
    @patch("cv2.inRange")
    @patch("cv2.dilate")
    def test_create_hsv_mask_with_morphology(
        self, mock_dilate, mock_inrange, mock_cvt
    ) -> None:
        mock_cvt.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        mock_inrange.return_value = np.zeros((10, 10), dtype=np.uint8)

        hsv_range = HSVRange(
            np.array([0, 0, 0]), np.array([180, 255, 255])
        )
        result = ExerciseOrganizer._create_hsv_mask(
            np.zeros((10, 10, 3), dtype=np.uint8),
            hsv_range,
            kernel_size=5,
            dilate_iterations=1,
            erode_iterations=0,
        )
        mock_dilate.assert_called_once()

    @patch("cv2.cvtColor")
    @patch("cv2.inRange")
    def test_create_hsv_mask_no_morphology(self, mock_inrange, mock_cvt) -> None:
        mock_cvt.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        mock_inrange.return_value = np.zeros((10, 10), dtype=np.uint8)

        hsv_range = HSVRange(
            np.array([0, 0, 0]), np.array([180, 255, 255])
        )
        result = ExerciseOrganizer._create_hsv_mask(
            np.zeros((10, 10, 3), dtype=np.uint8),
            hsv_range,
        )
        assert result is not None

    @patch("cv2.boundingRect")
    def test_extract_bounding_boxes(self, mock_rect) -> None:
        mock_rect.side_effect = [(0, 0, 10, 10), (20, 30, 50, 40)]
        contours = [MagicMock(), MagicMock()]
        boxes = ExerciseOrganizer._extract_bounding_boxes(contours)
        assert len(boxes) == 2
        assert boxes[0] == BoundingBox(0, 0, 10, 10)

    def test_is_valid_exercise_header(self) -> None:
        from src.english_practice.models.constants import (
            EXERCISE_BOX_MIN_WIDTH, EXERCISE_BOX_MAX_WIDTH,
            EXERCISE_BOX_MIN_HEIGHT, EXERCISE_BOX_MAX_HEIGHT,
            EXERCISE_MIN_AREA,
        )
        w = (EXERCISE_BOX_MIN_WIDTH + EXERCISE_BOX_MAX_WIDTH) // 2
        h = (EXERCISE_BOX_MIN_HEIGHT + EXERCISE_BOX_MAX_HEIGHT) // 2
        area = max(EXERCISE_MIN_AREA + 1, w * h)
        valid = BoundingBox(0, 0, w, h)
        assert ExerciseOrganizer._is_valid_exercise_header(valid, area=area)

    def test_is_valid_exercise_header_too_small(self) -> None:
        small = BoundingBox(0, 0, 5, 5)
        assert not ExerciseOrganizer._is_valid_exercise_header(small, area=10)

    def test_is_valid_exercise_header_too_large(self) -> None:
        large = BoundingBox(0, 0, 5000, 5000)
        assert not ExerciseOrganizer._is_valid_exercise_header(large, area=100000)

    def test_split_into_exercises(self) -> None:
        from src.english_practice.models.constants import EXERCISE_PADDING
        img = np.zeros((500, 300, 3), dtype=np.uint8)
        boxes = [{"x": 0, "y": 50, "w": 100, "h": 20}, {"x": 0, "y": 200, "w": 100, "h": 20}]
        exercises = ExerciseOrganizer()._split_into_exercises(img, boxes, 500, 300)
        assert len(exercises) == 2
        start_y = max(0, 50 - EXERCISE_PADDING)
        end_y = 200 - EXERCISE_PADDING
        assert exercises[0].shape[0] == end_y - start_y

    def test_crop_bottom_white_space_no_crop(self) -> None:
        img = np.ones((100, 100, 3), dtype=np.uint8) * 200
        result = ExerciseOrganizer()._crop_bottom_white_space(img)
        assert result.shape[0] == 100

    def test_crop_image_no_crop(self) -> None:
        with patch(
            "src.english_practice.extractors.exercise_organizer.EXERCISE_CROP_TOP", 0
        ), patch(
            "src.english_practice.extractors.exercise_organizer.EXERCISE_CROP_BOTTOM", 0
        ), patch(
            "src.english_practice.extractors.exercise_organizer.EXERCISE_CROP_LEFT", 0
        ), patch(
            "src.english_practice.extractors.exercise_organizer.EXERCISE_CROP_RIGHT", 0
        ):
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            result = ExerciseOrganizer()._crop_image(img)
            assert result.shape == (100, 100, 3)

    def test_crop_image_with_crops(self) -> None:
        with patch(
            "src.english_practice.extractors.exercise_organizer.EXERCISE_CROP_TOP", 10
        ), patch(
            "src.english_practice.extractors.exercise_organizer.EXERCISE_CROP_BOTTOM", 20
        ), patch(
            "src.english_practice.extractors.exercise_organizer.EXERCISE_CROP_LEFT", 5
        ), patch(
            "src.english_practice.extractors.exercise_organizer.EXERCISE_CROP_RIGHT", 5
        ):
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            result = ExerciseOrganizer()._crop_image(img)
            assert result.shape == (70, 90, 3)

    def test_get_sorted_page_files(self, tmp_path) -> None:
        for name in ["2.png", "1.png", "10.png"]:
            (tmp_path / name).write_text("img")
        files = ExerciseOrganizer._get_sorted_page_files(tmp_path)
        stems = [f.stem for f in files]
        assert stems == ["1", "2", "10"]

    def test_organize_raises_on_missing_dir(self) -> None:
        with pytest.raises(FileNotFoundError):
            ExerciseOrganizer().organize(Path("/nonexistent"), Path("/out"))

    def test_organize_raises_on_no_pngs(self, tmp_path) -> None:
        with pytest.raises(ValueError, match="No PNG files"):
            ExerciseOrganizer().organize(tmp_path, Path("/out"))

    def test_organize_processes_pages(self, tmp_path) -> None:
        src_dir = tmp_path / "source"
        out_dir = tmp_path / "out"
        src_dir.mkdir()
        (src_dir / "1.png").write_bytes(b"data")

        organizer = ExerciseOrganizer()
        with patch.object(organizer, "_extract_from_page", return_value=[
            np.zeros((100, 200, 3), dtype=np.uint8)
        ]):
            with patch.object(organizer, "_save_exercises", return_value=[out_dir / "1" / "1.1.png"]):
                results = organizer.organize(src_dir, out_dir)
                assert len(results) == 1

    def test_save_exercises(self, tmp_path) -> None:
        exercises = [np.zeros((100, 200, 3), dtype=np.uint8)]
        results = ExerciseOrganizer._save_exercises(exercises, tmp_path, 1)
        assert len(results) == 1
        assert results[0].parent.exists()
        assert results[0].name == "1.1.png"
