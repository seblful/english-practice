"""Tests for ExerciseOrganizer."""

from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from practice_extraction.constants import (
    BOTTOM_WHITE_MARGIN,
    EXERCISE_BOX_MAX_HEIGHT,
    EXERCISE_BOX_MAX_WIDTH,
    EXERCISE_BOX_MIN_HEIGHT,
    EXERCISE_BOX_MIN_WIDTH,
    EXERCISE_CROP_BOTTOM,
    EXERCISE_CROP_LEFT,
    EXERCISE_CROP_RIGHT,
    EXERCISE_CROP_TOP,
    EXERCISE_MIN_AREA,
    EXERCISE_MIN_HEIGHT,
    EXERCISE_PADDING,
    EXERCISE_SEARCH_WIDTH_RATIO,
)
from practice_extraction.extractors import exercise_organizer
from practice_extraction.extractors.exercise_organizer import (
    BoundingBox,
    ExerciseOrganizer,
    HSVRange,
    UnusableSlice,
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

        hsv_range = HSVRange(np.array([0, 0, 0]), np.array([180, 255, 255]))
        ExerciseOrganizer._create_hsv_mask(
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

        hsv_range = HSVRange(np.array([0, 0, 0]), np.array([180, 255, 255]))
        result = ExerciseOrganizer._create_hsv_mask(
            np.zeros((10, 10, 3), dtype=np.uint8),
            hsv_range,
        )
        assert result is not None

    def test_is_valid_exercise_header(self) -> None:
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

        img = np.zeros((500, 300, 3), dtype=np.uint8)
        boxes = [
            BoundingBox(0, 50, 100, 20),
            BoundingBox(0, 200, 100, 20),
        ]
        exercises = ExerciseOrganizer()._split_into_exercises(img, boxes)
        assert len(exercises) == 2
        start_y = max(0, 50 - EXERCISE_PADDING)
        end_y = 200 - EXERCISE_PADDING
        assert exercises[0].shape[0] == end_y - start_y

    def test_crop_bottom_white_space_no_crop(self) -> None:
        img = np.ones((100, 100, 3), dtype=np.uint8) * 200
        result = ExerciseOrganizer()._crop_bottom_white_space(img)
        assert result.shape[0] == 100

    def test_crop_image_no_crop(self) -> None:
        with (
            patch(
                "practice_extraction.extractors.exercise_organizer.EXERCISE_CROP_TOP", 0
            ),
            patch(
                "practice_extraction.extractors.exercise_organizer.EXERCISE_CROP_BOTTOM",
                0,
            ),
            patch(
                "practice_extraction.extractors.exercise_organizer.EXERCISE_CROP_LEFT",
                0,
            ),
            patch(
                "practice_extraction.extractors.exercise_organizer.EXERCISE_CROP_RIGHT",
                0,
            ),
        ):
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            result = ExerciseOrganizer()._crop_image(img)
            assert result.shape == (100, 100, 3)

    def test_crop_image_with_crops(self) -> None:
        with (
            patch(
                "practice_extraction.extractors.exercise_organizer.EXERCISE_CROP_TOP",
                10,
            ),
            patch(
                "practice_extraction.extractors.exercise_organizer.EXERCISE_CROP_BOTTOM",
                20,
            ),
            patch(
                "practice_extraction.extractors.exercise_organizer.EXERCISE_CROP_LEFT",
                5,
            ),
            patch(
                "practice_extraction.extractors.exercise_organizer.EXERCISE_CROP_RIGHT",
                5,
            ),
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
        with (
            patch.object(
                organizer,
                "_extract_from_page",
                return_value=[np.zeros((100, 200, 3), dtype=np.uint8)],
            ),
            patch.object(
                organizer, "_save_exercises", return_value=[out_dir / "1" / "1.1.png"]
            ),
        ):
            results = organizer.organize(src_dir, out_dir)
            assert len(results) == 1

    def test_save_exercises(self, tmp_path) -> None:
        exercises = [np.zeros((100, 200, 3), dtype=np.uint8)]
        results = ExerciseOrganizer._save_exercises(exercises, tmp_path, 1)
        assert len(results) == 1
        assert results[0].parent.exists()
        assert results[0].name == "1.1.png"

    def test_save_exercises_raises_when_the_write_fails(self, tmp_path) -> None:
        """cv2.imwrite reports failure by returning False, never by raising."""
        exercises = [np.zeros((100, 200, 3), dtype=np.uint8)]

        with (
            patch("cv2.imwrite", return_value=False),
            pytest.raises(OSError, match="could not write exercise image"),
        ):
            ExerciseOrganizer._save_exercises(exercises, tmp_path, 1)


class TestHeaderDetectionOnSyntheticPages:
    """Detection tests against generated pages.

    The real pipeline finds exercises by the teal header box printed beside
    each one, so these build pages with those boxes rather than mocking
    OpenCV: the geometry constants are exactly what could silently break.
    """

    # Inside the configured HSV window for the book's teal headers.
    TEAL_HSV = (90, 200, 200)
    HEADER_WIDTH = 125
    HEADER_HEIGHT = 70
    # Chosen so that, after cropping, the search strip is wider than a header.
    PAGE_WIDTH = EXERCISE_CROP_LEFT + EXERCISE_CROP_RIGHT + 2000
    PAGE_HEIGHT = EXERCISE_CROP_TOP + EXERCISE_CROP_BOTTOM + 1200

    @classmethod
    def _teal_bgr(cls) -> np.ndarray:
        """Return the header colour in BGR, as OpenCV reads an image."""
        hsv = np.array([[cls.TEAL_HSV]], dtype=np.uint8)
        return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0][0]

    @classmethod
    def _page(
        cls, header_offsets: tuple[int, ...], size: int | None = None
    ) -> np.ndarray:
        """Build a white page with a teal header box at each vertical offset.

        Args:
            header_offsets: Header positions, in cropped-page coordinates.
            size: Header side length override, to make an invalid box.

        Returns:
            The page as a BGR image.
        """
        page = np.full((cls.PAGE_HEIGHT, cls.PAGE_WIDTH, 3), 255, dtype=np.uint8)
        width = size or cls.HEADER_WIDTH
        height = size or cls.HEADER_HEIGHT
        for offset in header_offsets:
            top = EXERCISE_CROP_TOP + offset
            left = EXERCISE_CROP_LEFT + 5
            page[top : top + height, left : left + width] = cls._teal_bgr()
        return page

    def test_detects_one_box_per_header_sorted_by_position(self) -> None:
        organizer = ExerciseOrganizer()
        page = organizer._crop_image(self._page((700, 100)))
        search_width = int(page.shape[1] * EXERCISE_SEARCH_WIDTH_RATIO)

        boxes = organizer._detect_exercise_headers(page[:, :search_width])

        assert len(boxes) == 2
        assert [box.y for box in boxes] == sorted(box.y for box in boxes)
        assert boxes[0].w == self.HEADER_WIDTH

    def test_ignores_boxes_of_the_wrong_size(self) -> None:
        organizer = ExerciseOrganizer()
        page = organizer._crop_image(self._page((100,), size=30))
        search_width = int(page.shape[1] * EXERCISE_SEARCH_WIDTH_RATIO)

        assert organizer._detect_exercise_headers(page[:, :search_width]) == []

    def test_extract_from_page_splits_at_each_header(self, tmp_path) -> None:
        path = tmp_path / "1.png"
        cv2.imwrite(str(path), self._page((100, 700)))

        exercises = ExerciseOrganizer()._extract_from_page(path)

        assert len(exercises) == 2
        assert all(image.shape[0] >= EXERCISE_MIN_HEIGHT for image in exercises)

    def test_extract_from_page_falls_back_to_the_whole_page(self, tmp_path) -> None:
        """A page with no header is still worth keeping, uncut."""
        path = tmp_path / "1.png"
        cv2.imwrite(str(path), self._page(()))

        exercises = ExerciseOrganizer()._extract_from_page(path)

        assert len(exercises) == 1
        assert exercises[0].shape[0] == self.PAGE_HEIGHT - (
            EXERCISE_CROP_TOP + EXERCISE_CROP_BOTTOM
        )

    def test_extract_from_page_rejects_an_unreadable_file(self, tmp_path) -> None:
        path = tmp_path / "not-an-image.png"
        path.write_bytes(b"nonsense")

        with pytest.raises(ValueError, match="Cannot read image"):
            ExerciseOrganizer()._extract_from_page(path)

    def test_organize_writes_one_file_per_exercise(self, tmp_path) -> None:
        pages = tmp_path / "pages"
        output = tmp_path / "out"
        pages.mkdir()
        cv2.imwrite(str(pages / "1.png"), self._page((100, 700)))

        created = ExerciseOrganizer().organize(pages, output)

        assert [path.name for path in created] == ["1.1.png", "1.2.png"]
        assert all(path.exists() for path in created)


class TestMaskMorphology:
    """Tests for the optional morphology passes on the colour mask."""

    def test_erode_without_dilate(self) -> None:
        organizer = ExerciseOrganizer()
        region = np.zeros((20, 20, 3), dtype=np.uint8)
        hsv_range = organizer._create_hsv_range(0, 0, 0, 180, 255, 255)

        mask = organizer._create_hsv_mask(
            region, hsv_range, kernel_size=3, dilate_iterations=0, erode_iterations=1
        )

        assert mask.shape == (20, 20)


class TestBottomWhiteSpace:
    """Tests for trimming the blank space under the last exercise."""

    def test_crops_when_content_ends_early(self) -> None:
        """Only the bottom third is searched, so the content sits inside it."""
        image = np.full((400, 200, 3), 255, dtype=np.uint8)
        image[300:310, :] = 0  # a line of content, then white to the bottom

        cropped = ExerciseOrganizer()._crop_bottom_white_space(image)

        assert cropped.shape[0] == 309 + BOTTOM_WHITE_MARGIN

    def test_keeps_the_image_when_content_reaches_the_bottom(self) -> None:
        image = np.full((400, 200, 3), 255, dtype=np.uint8)
        image[-5:, :] = 0

        assert ExerciseOrganizer()._crop_bottom_white_space(image).shape[0] == 400


class TestSplitRefusesUnusableSlices:
    """Tests for the guard against slivers between two adjacent headers.

    A slice's position becomes its exercise number on disk, so dropping one
    used to renumber every exercise below it -- and every later stage keys on
    that number, which is how a student came to be shown a crop holding a
    different sentence from the one they were asked to answer.
    """

    def test_a_slice_below_the_minimum_height_refuses_the_page(self) -> None:
        image = np.zeros((300, 100, 3), dtype=np.uint8)
        boxes = [BoundingBox(0, 10, 1, 1), BoundingBox(0, 20, 1, 1)]

        with pytest.raises(UnusableSlice, match="header 1 of 2"):
            ExerciseOrganizer()._split_into_exercises(image, boxes)

    def test_a_refused_page_writes_nothing_and_is_named(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The gap has to be visible to the stages that read these crops."""
        warnings: list[tuple[str, dict]] = []
        monkeypatch.setattr(
            exercise_organizer.logger,
            "warning",
            lambda event, **fields: warnings.append((event, fields)),
        )
        page = tmp_path / "12.png"
        organizer = ExerciseOrganizer()
        monkeypatch.setattr(
            organizer,
            "_extract_from_page",
            lambda _: (_ for _ in ()).throw(UnusableSlice("sliver")),
        )

        written = organizer._process_pages([page], tmp_path / "out")

        assert written == []
        assert ("page_refused", {"page": 12, "reason": "sliver"}) in warnings
        assert ("pages_need_attention", {"pages": [12], "count": 1}) in warnings
