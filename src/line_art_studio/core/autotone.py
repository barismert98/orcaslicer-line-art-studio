"""Automatic tone preparation: a line has few tones to give, so the picture must use all of them."""
from __future__ import annotations

from itertools import accumulate

from .image import GrayImage

OUTLIER_SHARE = 0.01  # of the pixels at each end, so a few specks cannot set the range
MIN_LEVEL_RANGE = 16  # a narrower range is a flat picture, and stretching would only amplify noise
FULL_LEVEL = 255
SHARPEN_RADIUS_SHARE = 0.03  # of the picture's side: wide enough to lift shapes, not film grain
SHARPEN_AMOUNT = 1.4
BLUR_PASSES = 3  # three box blurs are close to a Gaussian


def _level_range(image: GrayImage) -> tuple:
    """The darkest and lightest levels left once the outliers at each end are set aside."""
    counts = [0] * (FULL_LEVEL + 1)
    for value in image.data:
        counts[value] += 1
    allowance = len(image.data) * OUTLIER_SHARE
    low = next(level for level, total in enumerate(accumulate(counts)) if total > allowance)
    high = FULL_LEVEL - next(level for level, total in enumerate(accumulate(reversed(counts))) if total > allowance)
    return low, high


def _stretched(image: GrayImage, low: int, high: int) -> GrayImage:
    table = bytes(min(max(round((level - low) * FULL_LEVEL / (high - low)), 0), FULL_LEVEL) for level in range(FULL_LEVEL + 1))
    return GrayImage(image.width, image.height, image.data.translate(table))


def _box_blur_rows(rows: list, radius: int) -> list:
    window = 2 * radius + 1
    blurred = []
    for row in rows:
        padded = [row[0]] * (radius + 1) + list(row) + [row[-1]] * radius  # edges repeat, so they do not darken
        running = list(accumulate(padded))
        blurred.append([(end - start) / window for start, end in zip(running, running[window:])])
    return blurred


def _blurred(image: GrayImage, radius: int) -> list:
    rows = [image.data[y * image.width:(y + 1) * image.width] for y in range(image.height)]
    for _ in range(BLUR_PASSES):
        rows = _box_blur_rows(rows, radius)
        rows = _box_blur_rows(list(zip(*rows)), radius)
        rows = list(zip(*rows))
    return [value for row in rows for value in row]


def _sharpened(image: GrayImage) -> GrayImage:
    radius = max(1, round(min(image.width, image.height) * SHARPEN_RADIUS_SHARE))
    data = bytes(
        min(max(round(value + SHARPEN_AMOUNT * (value - soft)), 0), FULL_LEVEL)
        for value, soft in zip(image.data, _blurred(image, radius))
    )
    return GrayImage(image.width, image.height, data)


def prepare(image: GrayImage) -> GrayImage:
    """The picture stretched across its real light-to-dark range, then locally sharpened."""
    low, high = _level_range(image)
    if high - low < MIN_LEVEL_RANGE:
        return image
    return _sharpened(_stretched(image, low, high))
