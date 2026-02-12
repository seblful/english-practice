"""Image OCR extractor using Mistral OCR API."""

import base64
import os
from pathlib import Path

from mistralai import Mistral
from tqdm import tqdm


class ImageOcrExtractor:
    """Extracts text from images via Mistral OCR and saves to markdown."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "mistral-ocr-latest",
    ) -> None:
        """Initialize the extractor.

        Args:
            api_key: Mistral API key. If None, uses MISTRAL_API_KEY from environment.
            model: OCR model name (e.g. from config mistral.ocr_model).
        """
        self._api_key = api_key or os.environ.get("MISTRAL_API_KEY")
        self._model = model
        self._client: Mistral | None = None

    def _get_client(self) -> Mistral:
        """Return the Mistral client, creating it on first use."""
        if self._api_key is None or self._api_key == "":
            raise ValueError(
                "MISTRAL_API_KEY must be set in environment or passed as api_key"
            )
        if self._client is None:
            self._client = Mistral(api_key=self._api_key)
        return self._client

    def encode_image(self, image_path: Path) -> str:
        """Encode an image file to a data URL (base64).

        Args:
            image_path: Path to the image file.

        Returns:
            Data URL string (e.g. data:image/png;base64,...).
        """
        raw = image_path.read_bytes()
        b64 = base64.b64encode(raw).decode("utf-8")
        suffix = image_path.suffix.lower()
        media_type = (
            "image/jpeg"
            if suffix in (".jpg", ".jpeg")
            else f"image/{suffix[1:] or 'png'}"
        )
        return f"data:{media_type};base64,{b64}"

    def ocr(self, image_path: Path) -> str:
        """Run OCR on an image and return extracted text as markdown.

        Args:
            image_path: Path to the image file.

        Returns:
            Extracted text as markdown.
        """
        client = self._get_client()
        data_url = self.encode_image(image_path)

        res = client.ocr.process(
            model=self._model,
            document={
                "image_url": {"url": data_url},
                "type": "image_url",
            },
        )
        if res.pages:
            return res.pages[0].markdown or ""
        return ""

    def ocr_and_save(
        self, image_path: Path, output_path: Path | None = None
    ) -> Path:
        """Extract text from an image and save to a markdown file.

        Args:
            image_path: Path to the image file.
            output_path: Path for the markdown file. If None, uses same directory
                and stem with .md extension (e.g. 1.png -> 1.md).

        Returns:
            The path where the markdown was written.
        """
        if output_path is None:
            output_path = image_path.parent / f"{image_path.stem}.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = self.ocr(image_path)
        output_path.write_text(text, encoding="utf-8")
        return output_path

    def ocr_dir(
        self,
        images_dir: Path,
        pattern: str = "*.png",
        output_dir: Path | None = None,
    ) -> list[Path]:
        """Run OCR on all matching images in a directory (resumable).

        Skips images whose output .md already exists. Uses tqdm for progress.

        Args:
            images_dir: Directory containing image files.
            pattern: Glob pattern for image files (e.g. "*.png").
            output_dir: Directory for markdown files. If None, writes next to
                each image (same path with .md extension).

        Returns:
            List of output markdown paths that were written.
        """
        image_paths = sorted(
            images_dir.glob(pattern),
            key=lambda p: (int(p.stem),) if p.stem.isdigit() else (float("inf"), p.stem),
        )
        remaining: list[tuple[Path, Path]] = []
        for img_path in image_paths:
            if output_dir is not None:
                out_path = output_dir / f"{img_path.stem}.md"
            else:
                out_path = img_path.parent / f"{img_path.stem}.md"
            if not out_path.exists():
                remaining.append((img_path, out_path))

        written: list[Path] = []
        for img_path, out_path in tqdm(remaining, desc="OCR images"):
            written.append(self.ocr_and_save(img_path, out_path))
        return written
