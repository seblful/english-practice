"""Draw the launcher icon and the splash screens."""

from pathlib import Path

from PIL import Image, ImageDraw

# Sampled from the book cover the bot uses as its avatar.
BRAND = (69, 130, 195)
ACCENT = (247, 193, 45)
INK = (255, 255, 255)

LIGHT_GROUND = (250, 250, 252)
DARK_GROUND = (18, 20, 24)

OUT = Path(__file__).resolve().parent.parent / "src" / "assets"

ICON_SIZE = 1024
SPLASH_SIZE = 1152
# How much of the splash the mark takes up.
SPLASH_MARK_SHARE = 0.42


def _tick(draw: ImageDraw.ImageDraw, size: int) -> None:
    """Draw a thick rounded check mark, centred and slightly above middle."""
    stroke = int(size * 0.105)
    short_start = (size * 0.255, size * 0.470)
    corner = (size * 0.430, size * 0.645)
    long_end = (size * 0.760, size * 0.315)

    draw.line([short_start, corner], fill=INK, width=stroke, joint="curve")
    draw.line([corner, long_end], fill=INK, width=stroke, joint="curve")
    # Round the ends: PIL's lines are butt-capped.
    for point in (short_start, corner, long_end):
        radius = stroke / 2
        draw.ellipse(
            [
                point[0] - radius,
                point[1] - radius,
                point[0] + radius,
                point[1] + radius,
            ],
            fill=INK,
        )


def icon(size: int = ICON_SIZE) -> Image.Image:
    """Return the launcher icon: brand field, white tick, accent baseline."""
    image = Image.new("RGB", (size, size), BRAND)
    draw = ImageDraw.Draw(image)
    _tick(draw, size)

    bar_height = int(size * 0.055)
    draw.rounded_rectangle(
        [size * 0.255, size * 0.745, size * 0.760, size * 0.745 + bar_height],
        radius=bar_height / 2,
        fill=ACCENT,
    )
    return image


def splash(background: tuple[int, int, int], size: int = SPLASH_SIZE) -> Image.Image:
    """Return a splash image: the icon mark centred on a flat ground."""
    image = Image.new("RGB", (size, size), background)
    mark = icon(int(size * SPLASH_MARK_SHARE))

    corners = Image.new("L", mark.size, 0)
    ImageDraw.Draw(corners).rounded_rectangle(
        [0, 0, mark.width - 1, mark.height - 1],
        radius=int(mark.width * 0.24),
        fill=255,
    )
    image.paste(mark, ((size - mark.width) // 2, (size - mark.height) // 2), corners)
    return image


def main() -> None:
    """Write the icon and both splash screens into the assets directory."""
    OUT.mkdir(parents=True, exist_ok=True)
    icon().save(OUT / "icon.png")
    splash(LIGHT_GROUND).save(OUT / "splash_android.png")
    splash(DARK_GROUND).save(OUT / "splash_android_dark.png")
    print("wrote", ", ".join(path.name for path in sorted(OUT.iterdir())))


if __name__ == "__main__":
    main()
