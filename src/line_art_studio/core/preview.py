"""Rasterizes the real toolpath, so the preview shows what will be extruded."""
from __future__ import annotations

import math

from . import shapes
from .art import Art


def render(art: Art, size: int = 360) -> bytes:
    """Coverage 0..255 per pixel, row by row, top row first; 255 is solid line."""
    scale = size / max(shapes.extents(art.params.outline))
    half = size / 2
    buffer = bytearray(size * size)
    for (ax, ay), (bx, by), width in zip(art.points, art.points[1:], art.widths):
        steps = max(1, math.ceil(math.hypot(bx - ax, by - ay) * scale))
        radius = width / 2 * scale
        reach = math.ceil(radius + 1)
        for s in range(steps + 1):
            t = s / steps
            px = half + (ax + (bx - ax) * t) * scale
            py = half - (ay + (by - ay) * t) * scale
            x0, y0 = int(px), int(py)
            for iy in range(max(y0 - reach, 0), min(y0 + reach + 1, size)):
                row = iy * size
                dy = iy + 0.5 - py
                for ix in range(max(x0 - reach, 0), min(x0 + reach + 1, size)):
                    dx = ix + 0.5 - px
                    amount = radius + 0.5 - math.sqrt(dx * dx + dy * dy)
                    if amount <= 0:
                        continue
                    value = 255 if amount >= 1 else int(amount * 255)
                    if value > buffer[row + ix]:
                        buffer[row + ix] = value
    return bytes(buffer)
