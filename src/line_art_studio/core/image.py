"""Grayscale image buffer with tone control and bilinear sampling."""
from __future__ import annotations

import base64
from dataclasses import dataclass


@dataclass(frozen=True)
class GrayImage:
    width: int
    height: int
    data: bytes  # one byte per pixel, row by row, top row first

    def __post_init__(self):
        if self.width < 1 or self.height < 1:
            raise ValueError("image has no pixels")
        if len(self.data) != self.width * self.height:
            raise ValueError("image data does not match its size")

    @classmethod
    def from_base64(cls, width: int, height: int, data: str) -> "GrayImage":
        return cls(int(width), int(height), base64.b64decode(data))

    def to_base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    def center_crop(self, aspect: float) -> "GrayImage":
        """The largest centered part with this width over height."""
        width = min(self.width, max(1, round(self.height * aspect)))
        height = min(self.height, max(1, round(width / aspect)))
        if (width, height) == (self.width, self.height):
            return self
        left = (self.width - width) // 2
        top = (self.height - height) // 2
        rows = (self.data[(top + y) * self.width + left:(top + y) * self.width + left + width] for y in range(height))
        return GrayImage(width, height, b"".join(rows))

    def sample(self, u: float, v: float) -> float:
        """Brightness 0..1 at u, v in 0..1; v grows downward."""
        x = min(max(u, 0.0), 1.0) * (self.width - 1)
        y = min(max(v, 0.0), 1.0) * (self.height - 1)
        x0, y0 = int(x), int(y)
        x1, y1 = min(x0 + 1, self.width - 1), min(y0 + 1, self.height - 1)
        fx, fy = x - x0, y - y0
        d, w = self.data, self.width
        top = d[y0 * w + x0] * (1 - fx) + d[y0 * w + x1] * fx
        bottom = d[y1 * w + x0] * (1 - fx) + d[y1 * w + x1] * fx
        return (top * (1 - fy) + bottom * fy) / 255.0


def tone(value: float, contrast: float, gamma: float) -> float:
    """Contrast around mid-gray, then gamma. Input and output are 0..1."""
    v = min(max(0.5 + (value - 0.5) * contrast, 0.0), 1.0)
    return v ** gamma
