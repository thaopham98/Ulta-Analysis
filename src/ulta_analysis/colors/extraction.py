"""Extract a representative color from one Ulta swatch image."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from io import BytesIO
import math
from statistics import median

from PIL import Image, ImageOps, UnidentifiedImageError


EXTRACTION_METHOD = "center_median_srgb_v1"


@dataclass(frozen=True)
class ColorMeasurement:
    image_sha256: str
    image_width: int
    image_height: int
    sample_pixel_count: int
    rgb_r: int
    rgb_g: int
    rgb_b: int
    hex_color: str
    lab_l: float
    lab_a: float
    lab_b: float
    rgb_spread: float
    extraction_method: str = EXTRACTION_METHOD

    def to_dict(self) -> dict:
        return asdict(self)


def measure_swatch_bytes(
    content: bytes,
    *,
    crop_fraction: float = 0.20,
    white_threshold: int = 245,
    minimum_foreground_fraction: float = 0.05,
) -> ColorMeasurement:
    """Measure median center-crop sRGB and convert it to CIE Lab (D65)."""
    if not content:
        raise ValueError("Swatch image is empty")
    if not 0 < crop_fraction <= 1:
        raise ValueError("crop_fraction must be greater than 0 and at most 1")
    if not 0 <= white_threshold <= 255:
        raise ValueError("white_threshold must be between 0 and 255")
    if not 0 <= minimum_foreground_fraction <= 1:
        raise ValueError("minimum_foreground_fraction must be between 0 and 1")

    ## opens raw bytes using `PIL.Image`
    try:
        with Image.open(BytesIO(content)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGBA") # open, normalize EXIF tags and convert to RGBA (red, green, blue, alpha) alpha is color opacity
            image.load()
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError("Downloaded content is not a readable image") from error

    ## Center cropping: Get the center pixel and get its color space
    width, height = image.size
    if width < 1 or height < 1:
        raise ValueError("Swatch image has invalid dimensions")

    crop_width = max(1, round(width * crop_fraction))
    crop_height = max(1, round(height * crop_fraction))
    left = (width - crop_width) // 2
    top = (height - crop_height) // 2
    crop = image.crop((left, top, left + crop_width, top + crop_height))

    rgba_bytes = crop.tobytes()
    opaque_pixels = [
        (rgba_bytes[index], rgba_bytes[index + 1], rgba_bytes[index + 2])
        for index in range(0, len(rgba_bytes), 4)
        if rgba_bytes[index + 3] > 15
    ]
    if not opaque_pixels:
        raise ValueError("Center crop contains no visible pixels")

    non_white = [
        pixel
        for pixel in opaque_pixels
        if not all(channel >= white_threshold for channel in pixel)
    ]
    minimum_foreground = max(
        1,
        math.ceil(len(opaque_pixels) * minimum_foreground_fraction),
    )
    sampled = non_white if len(non_white) >= minimum_foreground else opaque_pixels

    red = int(median(pixel[0] for pixel in sampled))
    green = int(median(pixel[1] for pixel in sampled))
    blue = int(median(pixel[2] for pixel in sampled))
    lab_l, lab_a, lab_b = srgb_to_lab(red, green, blue)
    spread = math.sqrt(
        sum(
            (pixel[0] - red) ** 2
            + (pixel[1] - green) ** 2
            + (pixel[2] - blue) ** 2
            for pixel in sampled
        )
        / len(sampled)
    )

    return ColorMeasurement(
        image_sha256=hashlib.sha256(content).hexdigest(),
        image_width=width,
        image_height=height,
        sample_pixel_count=len(sampled),
        rgb_r=red,
        rgb_g=green,
        rgb_b=blue,
        hex_color=f"#{red:02x}{green:02x}{blue:02x}",
        lab_l=round(lab_l, 2),
        lab_a=round(lab_a, 2),
        lab_b=round(lab_b, 2),
        rgb_spread=round(spread, 2),
    )


def srgb_to_lab(red: int, green: int, blue: int) -> tuple[float, float, float]:
    """Convert 8-bit sRGB to CIE L*a*b* using the D65 reference white."""
    for channel in (red, green, blue):
        if not 0 <= channel <= 255:
            raise ValueError("RGB channels must be between 0 and 255")

    linear = [_linearize_srgb(channel / 255.0) for channel in (red, green, blue)]
    red_linear, green_linear, blue_linear = linear
    x = (
        red_linear * 0.4124564
        + green_linear * 0.3575761
        + blue_linear * 0.1804375
    )
    y = (
        red_linear * 0.2126729
        + green_linear * 0.7151522
        + blue_linear * 0.0721750
    )
    z = (
        red_linear * 0.0193339
        + green_linear * 0.1191920
        + blue_linear * 0.9503041
    )

    fx = _lab_curve(x / 0.95047)
    fy = _lab_curve(y / 1.00000)
    fz = _lab_curve(z / 1.08883)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)

## function with formula to convert median sRGB to CIE Lab
def _linearize_srgb(value: float) -> float:
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _lab_curve(value: float) -> float:
    delta = 6 / 29
    if value > delta**3:
        return value ** (1 / 3)
    return value / (3 * delta**2) + 4 / 29
