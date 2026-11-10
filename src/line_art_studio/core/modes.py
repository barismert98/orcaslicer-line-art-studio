"""Every art style is one module with one interface: settings in, a Line out."""
from __future__ import annotations

from . import autotone, stipple, tsp
from .art import Line, Machine, Params, with_nozzle
from .image import GrayImage

GENERATORS = {"tsp": tsp.generate}
CHOICES = [
    {"id": "tsp", "label": "TSP line", "note": "One line that never crosses itself. Tone comes from how tightly it packs."},
]


def generate(params: Params, image: GrayImage | None, machine: Machine, stop: stipple.Stop = stipple.never) -> Line:
    params.validate(with_nozzle(params, machine))
    if params.auto_tone and image is not None:
        image = autotone.prepare(image)
    return GENERATORS[params.mode](params, image, machine, stop)
