"""Chooses the points the line will visit: many where the picture is dark, few where it is light."""
from __future__ import annotations

import random
from typing import Callable

MIN_DARK = 0.04  # lighter than this stays empty
OUTSIDE = -1.0  # a grid value for pixels beyond the art's outline
SPACING_RANGE = 10  # the widest spacing, as a multiple of the densest
DART_TRIES = 8  # candidates per densest-spacing square
RELAX_ROUNDS = 8
RELAX_PIXELS_PER_SPACING = 2.5
MAX_RELAX_GRID = 800
KEEP_FRACTION = 0.8  # relaxing may not bring two points closer than this part of the densest spacing


class Canceled(Exception):
    """A newer request replaced this one."""


Stop = Callable[[], None]


def never() -> None:
    return None


def estimate_points(dark: list, grid: int, side: float, spacing: float) -> int:
    """How many points the picture will need. Spacing goes with 1 / darkness."""
    total = sum(d * d for d in dark if d >= MIN_DARK)
    return int(0.75 * total * (side / grid) ** 2 / (spacing * spacing))


def _darts(dark: list, grid: int, side: float, spacing: float, stop: Stop) -> list:
    """Random candidates, kept when nothing is closer than the spacing their tone asks for.

    The line's ink per area goes with 1 / spacing, so spacing is the densest one over darkness.
    """
    rng = random.Random(1)
    widest = spacing * SPACING_RANGE
    cells: dict = {}
    points = []
    tries = int(DART_TRIES * side * side / (spacing * spacing))
    scale = grid / side
    for attempt in range(tries):
        if attempt % 4096 == 0:
            stop()
        x, y = rng.random() * side, rng.random() * side
        darkness = dark[min(grid - 1, int(y * scale)) * grid + min(grid - 1, int(x * scale))]
        if darkness < MIN_DARK:
            continue
        radius = min(widest, spacing / darkness)
        reach = int(radius / spacing) + 1
        cx, cy = int(x / spacing), int(y / spacing)
        limit = radius * radius
        free = True
        for i in range(cx - reach, cx + reach + 1):
            for j in range(cy - reach, cy + reach + 1):
                for qx, qy in cells.get((i, j), ()):
                    if (qx - x) ** 2 + (qy - y) ** 2 < limit:
                        free = False
                        break
                if not free:
                    break
            if not free:
                break
        if free:
            cells.setdefault((cx, cy), []).append((x, y))
            points.append((x, y))
    return points


def _relax(points: list, dark: list, grid: int, side: float, spacing: float, stop: Stop) -> list:
    """Weighted Lloyd rounds on a pixel grid: each point moves to the center of the ink around it."""
    size = max(32, min(MAX_RELAX_GRID, int(side / (spacing / RELAX_PIXELS_PER_SPACING))))
    weights = []
    for row in range(size):
        y = min(grid - 1, row * grid // size)
        for column in range(size):
            value = dark[y * grid + min(grid - 1, column * grid // size)]
            weights.append(0.0 if value == OUTSIDE else value * value + 1e-4)  # nothing may pull a point out
    pixel = side / size
    for _ in range(RELAX_ROUNDS):
        stop()
        best = [1e18] * (size * size)
        owner = [-1] * (size * size)
        grid_x = [p[0] / pixel for p in points]
        grid_y = [p[1] / pixel for p in points]
        frontier = []
        for index, (fx, fy) in enumerate(zip(grid_x, grid_y)):
            gx, gy = min(size - 1, int(fx)), min(size - 1, int(fy))
            cell = gy * size + gx
            gap = (gx - fx) ** 2 + (gy - fy) ** 2
            if gap < best[cell]:
                best[cell], owner[cell] = gap, index
                frontier.append(cell)
        while frontier:
            grown = []
            for cell in frontier:
                index = owner[cell]
                fx, fy = grid_x[index], grid_y[index]
                gy, gx = divmod(cell, size)
                for nx, ny in ((gx + 1, gy), (gx - 1, gy), (gx, gy + 1), (gx, gy - 1)):
                    if 0 <= nx < size and 0 <= ny < size:
                        target = ny * size + nx
                        gap = (nx - fx) ** 2 + (ny - fy) ** 2
                        if gap < best[target]:
                            best[target], owner[target] = gap, index
                            grown.append(target)
            frontier = grown
        total = [0.0] * len(points)
        sum_x = [0.0] * len(points)
        sum_y = [0.0] * len(points)
        for cell, index in enumerate(owner):
            gy, gx = divmod(cell, size)
            weight = weights[cell]
            total[index] += weight
            sum_x[index] += weight * gx
            sum_y[index] += weight * gy
        points = [
            (sum_x[i] / total[i] * pixel, sum_y[i] / total[i] * pixel) if total[i] > 0 else points[i]
            for i in range(len(points))
        ]
    return points


def _thin(points: list, distance: float) -> list:
    """Drops points closer than `distance` to one already kept."""
    limit = distance * distance
    cells: dict = {}
    kept = []
    for x, y in points:
        cx, cy = int(x / distance), int(y / distance)
        close = any(
            (qx - x) ** 2 + (qy - y) ** 2 < limit
            for i in range(cx - 1, cx + 2)
            for j in range(cy - 1, cy + 2)
            for qx, qy in cells.get((i, j), ())
        )
        if not close:
            cells.setdefault((cx, cy), []).append((x, y))
            kept.append((x, y))
    return kept


def place(dark: list, grid: int, side: float, spacing: float, stop: Stop = never) -> list:
    """Points in 0..side on both axes; `dark` holds grid x grid values 0..1, top row first."""
    points = _darts(dark, grid, side, spacing, stop)
    if len(points) < 2:
        return points
    return _thin(_relax(points, dark, grid, side, spacing, stop), spacing * KEEP_FRACTION)
