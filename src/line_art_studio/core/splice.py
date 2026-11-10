"""Finds the top layer of a sliced base and replaces its object extrusions."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from . import shapes
from .art import Machine
from .gcode import START_MARK

_LAYER_MARKS = ("; CHANGE_LAYER", ";LAYER_CHANGE")
_FEATURE_RE = re.compile(r"^(?:; FEATURE: |;TYPE:)(.+?)\s*$")
_NOT_OBJECT = {"custom", "prime tower", "wipe tower"}
_REGION_STOPS = ("; stop printing object", "EXCLUDE_OBJECT_END", "; filament end gcode", "; MACHINE_END_GCODE_START", "; EXECUTABLE_BLOCK_END")
_WORD_RE = re.compile(r"([A-Z])([-+]?[0-9]*\.?[0-9]+)")
_SIZE_TOLERANCE = 1.5
_OBJECT_MARKS = ("; printing object", "EXCLUDE_OBJECT_START")
_DIAGONAL_TOLERANCE = 2.5  # mm: wall centerlines round the corners off a little


class NotPlaceholder(Exception):
    """This G-code is not the placeholder base of the saved job."""


@dataclass(frozen=True)
class TopLayer:
    z: float
    height: float
    region_start: int
    region_end: int
    center: tuple
    size: tuple
    diagonal: float
    upper: tuple
    relative_e: bool
    tool: int
    debt_start: float
    e_end: float


def _words(line: str) -> dict:
    code = line.split(";", 1)[0]
    return {letter: float(value) for letter, value in _WORD_RE.findall(code)}


def _layer_values(lines: list, start: int) -> tuple:
    z = height = None
    for line in lines[start + 1 : start + 6]:
        if line.startswith(("; Z_HEIGHT:", ";Z:")):
            z = float(line.split(":", 1)[1])
        elif line.startswith(("; LAYER_HEIGHT:", ";HEIGHT:")):
            height = float(line.split(":", 1)[1])
    if z is None or height is None:
        raise NotPlaceholder("the top layer has no height information")
    return z, height


def _arc_points(x0: float, y0: float, words: dict, clockwise: bool) -> list:
    cx, cy = x0 + words.get("I", 0.0), y0 + words.get("J", 0.0)
    x1, y1 = words.get("X", x0), words.get("Y", y0)
    start = math.atan2(y0 - cy, x0 - cx)
    end = math.atan2(y1 - cy, x1 - cx)
    sweep = end - start
    if clockwise and sweep >= 0:
        sweep -= 2 * math.pi
    if not clockwise and sweep <= 0:
        sweep += 2 * math.pi
    radius = math.hypot(x0 - cx, y0 - cy)
    count = max(4, int(abs(sweep) / (math.pi / 32)))
    return [(cx + radius * math.cos(start + sweep * i / count), cy + radius * math.sin(start + sweep * i / count)) for i in range(1, count + 1)]


def _first_object_feature(lines: list, layer: int) -> int | None:
    for i in range(layer + 1, len(lines)):
        match = _FEATURE_RE.match(lines[i])
        if match and match.group(1).strip().lower() not in _NOT_OBJECT:
            return i
    return None


def _marker_lines(lines: list, mark: int) -> list:
    """The comment lines that announce a layer, kept so an art layer still counts as one."""
    end = mark
    while lines[end].startswith(";"):
        end += 1
    return lines[mark:end]


def locate(lines: list, count: int = 1) -> TopLayer:
    """Walks the file once, tracking E state, and describes the top `count` layers as one region."""
    marks = [i for i, l in enumerate(lines) if l.startswith(_LAYER_MARKS)]
    if not marks:
        raise NotPlaceholder("no layer markers found")
    if len(marks) <= count:
        raise NotPlaceholder(f"the print has too few layers for {count} art layers")
    chosen = marks[-count:]
    z, height = _layer_values(lines, chosen[0])
    upper = []
    for mark in chosen[1:]:
        upper_z, upper_height = _layer_values(lines, mark)
        if abs(upper_height - height) > 0.001:
            raise NotPlaceholder("the art layers do not share one layer height")
        upper.append((upper_z, _marker_lines(lines, mark)))

    region_start = _first_object_feature(lines, chosen[0])
    top_start = _first_object_feature(lines, chosen[-1])
    region_end = None
    if top_start is not None:
        for i in range(top_start + 1, len(lines)):
            match = _FEATURE_RE.match(lines[i])
            if lines[i].startswith(_REGION_STOPS) or (match and match.group(1).strip().lower() in _NOT_OBJECT):
                region_end = i
                break
    if region_start is None or region_end is None:
        raise NotPlaceholder("the top layer has no object extrusions")

    relative = True
    tool = 0
    e_abs = 0.0        # the value the file's own counter holds
    pos = high = 0.0   # filament position independent of G92
    x = y = 0.0
    minx = miny = math.inf
    maxx = maxy = -math.inf
    min_sum = min_diff = math.inf
    max_sum = max_diff = -math.inf
    debt_start = 0.0
    e_end = 0.0

    for i, line in enumerate(lines):
        if i == region_start:
            debt_start = high - pos
        if i == region_end:
            e_end = e_abs
            break
        code = line.split(";", 1)[0].strip()
        if not code:
            continue
        head = code.split(None, 1)[0]
        if head == "M82":
            relative = False
        elif head == "M83":
            relative = True
        elif head[0] == "T" and head[1:].isdigit() and int(head[1:]) < 64:  # T255, T1000 are not tools
            tool = int(head[1:])
        elif head == "G92":
            words = _words(code)
            if "E" in words:
                e_abs = words["E"]
        elif head in ("G0", "G1", "G2", "G3"):
            words = _words(code)
            nx, ny = words.get("X", x), words.get("Y", y)
            delta = 0.0
            if "E" in words:
                delta = words["E"] if relative else words["E"] - e_abs
                e_abs = e_abs + delta if relative else words["E"]
                pos += delta
                high = max(high, pos)
            if i > top_start and delta > 0 and ("X" in words or "Y" in words):
                points = _arc_points(x, y, words, head == "G2") if head in ("G2", "G3") else [(nx, ny)]
                if head == "G1":
                    points.append((x, y))
                for px, py in points:
                    minx, maxx = min(minx, px), max(maxx, px)
                    miny, maxy = min(miny, py), max(maxy, py)
                    min_sum, max_sum = min(min_sum, px + py), max(max_sum, px + py)
                    min_diff, max_diff = min(min_diff, px - py), max(max_diff, px - py)
            x, y = nx, ny

    if minx is math.inf:
        raise NotPlaceholder("the top layer has no extrusion moves")
    return TopLayer(
        z=z,
        height=height,
        region_start=region_start,
        region_end=region_end,
        center=((minx + maxx) / 2, (miny + maxy) / 2),
        size=(maxx - minx, maxy - miny),
        diagonal=max(max_sum - min_sum, max_diff - min_diff) / math.sqrt(2),
        upper=tuple(upper),
        relative_e=relative,
        tool=tool,
        debt_start=max(0.0, debt_start),
        e_end=e_end,
    )


def is_done(text: str) -> bool:
    return START_MARK in text


def check_own_object(lines: list, name: str) -> None:
    """Other plugins of this family can be selected too, and may use a base of the same size."""
    if not any(line.startswith(_OBJECT_MARKS) and name in line for line in lines):
        raise NotPlaceholder(f"no object named {name} in this print")


def check_base(top: TopLayer, rim: list) -> None:
    """Confirms the size and the shape of the base, so the line never hangs past its edge."""
    width, height = shapes.extents(rim)
    if abs(top.size[0] - width) > _SIZE_TOLERANCE or abs(top.size[1] - height) > _SIZE_TOLERANCE:
        raise NotPlaceholder(f"top layer is {top.size[0]:.1f} x {top.size[1]:.1f} mm, expected {width:.1f} x {height:.1f} mm")
    if abs(top.diagonal - shapes.width_at_45(rim)) > _DIAGONAL_TOLERANCE:
        raise NotPlaceholder(f"the top layer does not have the shape of the expected {width:.1f} x {height:.1f} mm base")


def check_bed(top: TopLayer, extents: tuple, machine: Machine) -> None:
    half_x, half_y = extents[0] / 2, extents[1] / 2
    cx, cy = top.center
    minx, miny, maxx, maxy = machine.bed
    if cx - half_x < minx or cy - half_y < miny or cx + half_x > maxx or cy + half_y > maxy:
        raise ValueError("The base reaches outside the printable area.")


def replace(lines: list, top: TopLayer, block: list) -> list:
    return lines[: top.region_start] + block + lines[top.region_end :]
