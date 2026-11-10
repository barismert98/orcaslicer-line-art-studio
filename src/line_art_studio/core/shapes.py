"""The art's outer shape. One convex polygon drives the base mesh, the mask, the picture fit and the splice check.

Only convex shapes are offered: a straight line between two points inside a convex outline stays inside it,
and the route has no way to go around a dent. They are also symmetric, because the slicing step centers the
art on the bounding box of the base it finds.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

CURVE_SEGMENTS = 180
CORNER_SEGMENTS = 24
CORNER_SHARE = 0.15  # corner radius of a rounded rectangle, over its shorter side
HEXAGON_ASPECT = 2 / math.sqrt(3)  # across corners over across flats
HEXAGON_SIDES = 6
_ICON_SIZE = 1.0
_ICON_TALL = 0.7  # the height of a two-sided shape's picture in the picker, over its width
_LEVEL = 1e-12  # an edge this close to horizontal bounds no x
_DIGITS = 5  # the page only draws these, and rounding keeps them inside 0..1


def _square(width: float, _height: float) -> list:
    half = width / 2
    return [(-half, -half), (half, -half), (half, half), (-half, half)]


def _rectangle(width: float, height: float) -> list:
    half_x, half_y = width / 2, height / 2
    return [(-half_x, -half_y), (half_x, -half_y), (half_x, half_y), (-half_x, half_y)]


def _oval(width: float, height: float) -> list:
    half_x, half_y = width / 2, height / 2
    return [
        (half_x * math.cos(2 * math.pi * i / CURVE_SEGMENTS), half_y * math.sin(2 * math.pi * i / CURVE_SEGMENTS))
        for i in range(CURVE_SEGMENTS)
    ]


def _circle(width: float, _height: float) -> list:
    return _oval(width, width)


def _rounded_rectangle(width: float, height: float) -> list:
    radius = CORNER_SHARE * min(width, height)
    half_x, half_y = width / 2 - radius, height / 2 - radius
    corners = ((half_x, -half_y, -90.0), (half_x, half_y, 0.0), (-half_x, half_y, 90.0), (-half_x, -half_y, 180.0))
    return [
        (cx + radius * math.cos(math.radians(start + 90.0 * i / CORNER_SEGMENTS)),
         cy + radius * math.sin(math.radians(start + 90.0 * i / CORNER_SEGMENTS)))
        for cx, cy, start in corners
        for i in range(CORNER_SEGMENTS + 1)
    ]


def _hexagon(width: float, _height: float) -> list:
    """Flat on top, so `width` runs across two corners."""
    radius = width / 2
    return [
        (radius * math.cos(2 * math.pi * i / HEXAGON_SIDES), radius * math.sin(2 * math.pi * i / HEXAGON_SIDES))
        for i in range(HEXAGON_SIDES)
    ]


@dataclass(frozen=True)
class Shape:
    label: str
    sides: int  # 1: width alone sets the size, 2: width and height are both entered
    aspect: float | None  # width over height when it is fixed
    build: Callable[[float, float], list]


SHAPES = {
    "square": Shape("Square", 1, 1.0, _square),
    "circle": Shape("Circle", 1, 1.0, _circle),
    "rectangle": Shape("Rectangle", 2, None, _rectangle),
    "oval": Shape("Oval", 2, None, _oval),
    "rounded_rectangle": Shape("Rounded rectangle", 2, None, _rounded_rectangle),
    "hexagon": Shape("Hexagon", 1, HEXAGON_ASPECT, _hexagon),
}


def resolved_height(shape: str, width: float, height: float) -> float:
    """A fixed-aspect shape's height follows its width, whatever was saved."""
    known = SHAPES.get(shape)
    return width / known.aspect if known and known.aspect else height


def outline(shape: str, width: float, height: float) -> list:
    """Counter-clockwise polygon around the origin, y up."""
    return SHAPES[shape].build(width, height)


def extents(rim: list) -> tuple:
    xs, ys = zip(*rim)
    return max(xs) - min(xs), max(ys) - min(ys)


def width_at_45(rim: list) -> float:
    """The wider of the two diagonal widths; the splice measures the same on the sliced layer."""
    across_sum = max(x + y for x, y in rim) - min(x + y for x, y in rim)
    across_diff = max(x - y for x, y in rim) - min(x - y for x, y in rim)
    return max(across_sum, across_diff) / math.sqrt(2)


def half_planes(rim: list) -> list:
    """One (nx, ny, c) per edge: a point is inside by d when nx * x + ny * y >= c + d."""
    planes = []
    for (ax, ay), (bx, by) in zip(rim, rim[1:] + rim[:1]):
        length = math.hypot(bx - ax, by - ay)
        nx, ny = -(by - ay) / length, (bx - ax) / length
        planes.append((nx, ny, nx * ax + ny * ay))
    return planes


def span(planes: list, y: float, inset: float) -> tuple | None:
    """The range of x that is inside by `inset` on the row at y, or None when the row misses."""
    low, high = -math.inf, math.inf
    for nx, ny, c in planes:
        room = c + inset - ny * y
        if abs(nx) < _LEVEL:
            if room > 0:
                return None
        elif nx > 0:
            low = max(low, room / nx)
        else:
            high = min(high, room / nx)
    return (low, high) if low <= high else None


def canvas_outline(rim: list) -> list:
    """The outline in 0..1 of a square canvas holding the shape centered, top left origin, y down."""
    side = max(extents(rim))
    return [[round(x / side + 0.5, _DIGITS), round(0.5 - y / side, _DIGITS)] for x, y in rim]


def _icon_outline(shape: Shape) -> list:
    """The outline in 0..1 of its own bounding box, top left origin, y down."""
    width = _ICON_SIZE
    height = width / shape.aspect if shape.aspect else _ICON_TALL
    rim = shape.build(width, height)
    return [[round(x / width + 0.5, _DIGITS), round(0.5 - y / height, _DIGITS)] for x, y in rim]


def choices() -> list:
    """What the page needs to offer the shapes."""
    return [
        {"id": name, "label": shape.label, "sides": shape.sides, "aspect": shape.aspect, "outline": _icon_outline(shape)}
        for name, shape in SHAPES.items()
    ]
