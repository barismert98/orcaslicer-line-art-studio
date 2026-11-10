"""Job parameters, machine values, and the line they produce."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from typing import Callable

from . import shapes
from .image import GrayImage

MODES = ("tsp",)
COLOR_CHANGES = ("none", "pause")
MIN_SIZE = 60.0
ROUTE_FIELDS = ("mode", "shape", "width", "height", "line_width", "spacing", "invert", "gamma", "contrast", "margin", "auto_tone")
SLIDER_LIMITS = {"spacing": (1.3, 4.0), "contrast": (0.1, 4.0), "gamma": (0.1, 4.0)}


class ArtError(ValueError):
    """A problem the user can fix by changing a setting."""


@dataclass(frozen=True)
class Machine:
    nozzle: float = 0.4
    filament_diameter: float = 1.75
    flow_ratio: float = 1.0
    max_volumetric: float = 15.0
    retract_length: float = 0.8
    retract_speed: float = 30.0
    deretract_speed: float = 30.0
    z_hop: float = 0.4
    travel_speed: float = 200.0
    relative_e: bool = True
    pause_gcode: str = ""
    bed: tuple[float, float, float, float] = (0.0, 0.0, 256.0, 256.0)  # min x, min y, max x, max y

    @property
    def filament_area(self) -> float:
        return math.pi * (self.filament_diameter / 2) ** 2


def _first(value, tool: int) -> str:
    parts = str(value).split(",")
    return parts[min(tool, len(parts) - 1)].strip()


def machine_from_config(get: Callable[[str], object], tool: int = 0) -> Machine:
    """Read a Machine from a resolved config getter; missing keys keep their defaults."""
    base = Machine()

    def number(key: str, default: float) -> float:
        raw = get(key)
        if raw in (None, ""):
            return default
        try:
            return float(_first(raw, tool))
        except ValueError:
            return default

    bed = base.bed
    area = get("printable_area")
    if area:
        xs, ys = zip(*(tuple(float(c) for c in p.split("x")) for p in str(area).split(",")))
        bed = (min(xs), min(ys), max(xs), max(ys))
    relative = get("use_relative_e_distances")
    pause = get("machine_pause_gcode")
    return Machine(
        nozzle=number("nozzle_diameter", base.nozzle),
        filament_diameter=number("filament_diameter", base.filament_diameter),
        flow_ratio=number("filament_flow_ratio", base.flow_ratio),
        max_volumetric=number("filament_max_volumetric_speed", base.max_volumetric),
        retract_length=number("retraction_length", base.retract_length),
        retract_speed=number("retraction_speed", base.retract_speed),
        deretract_speed=number("deretraction_speed", base.deretract_speed) or number("retraction_speed", base.retract_speed),
        z_hop=number("z_hop", base.z_hop),
        travel_speed=number("travel_speed", base.travel_speed),
        relative_e=str(relative) not in ("0", "false") if relative is not None else True,
        pause_gcode=str(pause).replace("\\n", "\n") if pause else "",
        bed=bed,
    )


@dataclass(frozen=True)
class Params:
    mode: str = "tsp"
    shape: str = "square"
    width: float = 150.0  # extent along X; see core/shapes.py for what it means per shape
    height: float = 150.0  # extent along Y
    line_width: float = 0.42
    spacing: float = 1.3  # the closest two points may be, as a multiple of the line width
    invert: bool = False  # for a light line on a dark base
    gamma: float = 1.0
    contrast: float = 1.25
    speed: float = 40.0
    margin: float = 0.4
    base_layers: int = 4
    color_change: str = "pause"
    art_layers: int = 1
    nozzle: float = 0.0  # 0: the printer preset's nozzle
    layer_height: float = 0.0  # 0: whatever the slice uses
    base_filament: int = 1  # 1-based slot in the project
    art_filament: int = 1
    auto_tone: bool = True

    @property
    def two_filaments(self) -> bool:
        return self.base_filament != self.art_filament

    @property
    def outline(self) -> list:
        return shapes.outline(self.shape, self.width, self.height)

    @property
    def inset(self) -> float:
        """How far the line's center stays inside the outline."""
        return self.margin + self.line_width / 2

    @classmethod
    def from_dict(cls, data: dict) -> "Params":
        fields = cls.__dataclass_fields__
        converted = {}
        for key, value in data.items():
            if key in fields:
                kind = {"str": str, "bool": bool, "int": int, "float": float}[fields[key].type]
                converted[key] = kind(value)
        converted.setdefault("auto_tone", False)  # what jobs from before the setting were made with
        if "size" in data and "width" not in data:  # jobs from before shapes hold one size, for a square
            converted["width"] = converted["height"] = float(data["size"])
        if "width" in converted:
            converted["height"] = shapes.resolved_height(
                converted.get("shape", cls.shape), converted["width"], converted.get("height", cls.height)
            )
        return cls(**converted)

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self, machine: Machine) -> None:
        if self.mode not in MODES:
            raise ArtError(f"Unknown mode: {self.mode}")
        if self.color_change not in COLOR_CHANGES:
            raise ArtError(f"Unknown color change: {self.color_change}")
        if self.shape not in shapes.SHAPES:
            raise ArtError(f"Unknown shape: {self.shape}")
        if min(shapes.extents(self.outline)) < MIN_SIZE:
            raise ArtError(f"Each side of the art must be at least {MIN_SIZE:g} mm.")
        if not 0.5 * machine.nozzle <= self.line_width <= 1.5 * machine.nozzle:
            raise ArtError(
                f"Line width must be between {0.5 * machine.nozzle:.2f} and {1.5 * machine.nozzle:.2f} mm for this nozzle."
            )
        for name, label in (("spacing", "Detail spacing"), ("contrast", "Contrast"), ("gamma", "Gamma")):
            low, high = SLIDER_LIMITS[name]
            if not low <= getattr(self, name) <= high:
                raise ArtError(f"{label} must be between {low:g} and {high:g}.")
        if self.speed <= 0:
            raise ArtError("Speed must be positive.")
        if self.base_layers < 1:
            raise ArtError("The base needs at least one layer.")
        if self.base_filament < 1 or self.art_filament < 1:
            raise ArtError("Filament numbers start at 1.")
        if not 1 <= self.art_layers <= 10:
            raise ArtError("Art layers must be between 1 and 10.")
        if self.nozzle and not 0.1 <= self.nozzle <= 1.2:
            raise ArtError("Nozzle diameter must be between 0.1 and 1.2 mm.")
        if self.layer_height and not 0.04 <= self.layer_height <= 0.8 * machine.nozzle:
            raise ArtError(f"Layer height must be between 0.04 and {0.8 * machine.nozzle:.2f} mm for this nozzle.")


@dataclass(frozen=True)
class Line:
    """What every art style produces."""

    points: list  # centered on the origin, y up
    widths: list  # one per segment, len(points) - 1


@dataclass(frozen=True)
class Art:
    points: list  # centered on the origin
    widths: list  # one per segment, len(points) - 1
    layer_height: float
    speed: float  # mm/s, constant along the line
    params: Params
    machine: Machine

    def lengths(self) -> list:
        return [math.dist(a, b) for a, b in zip(self.points, self.points[1:])]

    def stats(self) -> dict:
        total = sum(self.lengths()) * self.params.art_layers
        lengths = self.lengths()
        width = max(self.widths)
        volume = sum(w * l for w, l in zip(self.widths, lengths)) * self.layer_height * self.params.art_layers
        return {
            "points": len(self.points),
            "length_mm": total,
            "volume_mm3": volume,
            "filament_mm": volume / self.machine.filament_area,
            "time_s": total / self.speed,
            "width": width,
            "speed": self.speed,
            "max_flow": width * self.layer_height * self.speed,
        }


def with_nozzle(params: Params, machine: Machine) -> Machine:
    return replace(machine, nozzle=params.nozzle) if params.nozzle else machine


def route_key(params: Params, image: GrayImage) -> str:
    """Same key, same line. Printer values such as speed or layer height do not change the line."""
    fields = json.dumps({name: getattr(params, name) for name in ROUTE_FIELDS}, sort_keys=True).encode()
    return hashlib.sha1(fields + b"|%d|" % image.width + image.data).hexdigest()


def limited_speed(params: Params, line: Line, machine: Machine, layer_height: float) -> float:
    """Constant speed that keeps flow within the volumetric limit at the widest point."""
    return min(params.speed, machine.max_volumetric / (max(line.widths) * layer_height))


def build(params: Params, line: Line, machine: Machine, layer_height: float) -> Art:
    machine = with_nozzle(params, machine)
    params.validate(machine)
    if layer_height <= 0:
        raise ArtError("Layer height must be positive.")
    if len(line.points) < 2:
        raise ArtError("The saved line is empty. Save the job again.")
    return Art(list(line.points), list(line.widths), layer_height, limited_speed(params, line, machine, layer_height), params, machine)
