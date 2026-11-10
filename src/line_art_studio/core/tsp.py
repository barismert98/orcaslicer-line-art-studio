"""TSP line art: points placed by tone, joined into one self-avoiding line of constant width."""
from __future__ import annotations

from . import shapes, stipple, tour
from .art import ArtError, Line, Machine, Params
from .image import GrayImage, tone

MAX_POINTS = 40000


def _reach(params: Params) -> tuple:
    """How far the line's center can go from the middle, along X and along Y."""
    width, height = shapes.extents(params.outline)
    return width / 2 - params.inset, height / 2 - params.inset


def _darkness(image: GrayImage, params: Params) -> tuple:
    """How much line each pixel wants, 0..1, and the grid side.

    The grid is the square around the shape, so the point and route code never needs to know the shape.
    """
    width, height = shapes.extents(params.outline)
    picture = image.center_crop(width / height)
    levels = [tone(v / 255.0, params.contrast, params.gamma) for v in range(256)]
    table = levels if params.invert else [1.0 - v for v in levels]
    grid = max(picture.width, picture.height)
    reach_x, reach_y = _reach(params)
    half = max(reach_x, reach_y)
    planes = shapes.half_planes(params.outline)
    cell = 2 * half / grid
    across = [-half + (column + 0.5) * cell for column in range(grid)]
    dark = []
    for row in range(grid):
        y = half - (row + 0.5) * cell
        room = shapes.span(planes, y, params.inset)
        picture_row = min(picture.height - 1, max(0, int((reach_y - y) / (2 * reach_y) * picture.height)))
        for x in across:
            if room is None or not room[0] <= x <= room[1]:
                dark.append(stipple.OUTSIDE)
            else:
                column = min(picture.width - 1, max(0, int((x + reach_x) / (2 * reach_x) * picture.width)))
                dark.append(table[picture.data[picture_row * picture.width + column]])
    return dark, grid


def _inside(points: list, half: float, params: Params) -> list:
    """Relaxing works on pixels, so a point can end just past the true outline."""
    planes = shapes.half_planes(params.outline)
    kept = []
    for x, y in points:
        room = shapes.span(planes, half - y, params.inset)
        if room is not None and room[0] <= x - half <= room[1]:
            kept.append((x, y))
    return kept


def generate(params: Params, image: GrayImage | None, _machine: Machine, stop: stipple.Stop = stipple.never) -> Line:
    """The line, centered on the origin with y up."""
    if image is None:
        raise ArtError("Pick an image first.")
    dark, grid = _darkness(image, params)
    half = max(_reach(params))
    side = 2 * half
    closest = params.spacing * params.line_width
    wanted = stipple.estimate_points(dark, grid, side, closest)
    if wanted > MAX_POINTS:
        raise ArtError(f"This picture needs about {wanted} points. Use a smaller size or a larger detail spacing.")
    placed = _inside(stipple.place(dark, grid, side, closest, stop), half, params)
    points = tour.route(placed, side, params.line_width, stop)
    if len(points) < 2:
        raise ArtError("The picture is too light to draw. Raise the contrast, or turn Invert off.")
    return Line([(x - half, half - y) for x, y in points], [params.line_width] * (len(points) - 1))
