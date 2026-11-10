"""From a saved job and a sliced file to the edited file."""
from __future__ import annotations

from dataclasses import dataclass, replace as dc_replace

from . import art as art_module
from . import gcode, placeholder, shapes, splice


@dataclass(frozen=True)
class Outcome:
    text: str
    changed: bool
    message: str


JOB_VERSION = 1


def job_to_dict(params: art_module.Params, line: art_module.Line) -> dict:
    return {
        "version": JOB_VERSION,
        "mode": params.mode,
        "params": params.to_dict(),
        "points": [round(value, 3) for point in line.points for value in point],
        "widths": [round(width, 3) for width in line.widths],
    }


def job_from_dict(data: dict) -> tuple:
    if "points" not in data:
        raise art_module.ArtError("The saved job is from an older version. Press the save button again, then slice.")
    flat = data["points"]
    return art_module.Params.from_dict(data["params"]), art_module.Line(list(zip(flat[::2], flat[1::2])), data["widths"])


def process(text: str, job: dict | None, get_config) -> Outcome:
    """Raises ArtError or ValueError when the base matches but the art cannot be built."""
    if job is None:
        return Outcome(text, False, "No saved job; G-code left as it is.")
    if splice.is_done(text):
        return Outcome(text, False, "Already processed.")
    params, line = job_from_dict(job)
    lines = text.split("\n")
    try:
        splice.check_own_object(lines, placeholder.BASE_NAME)
        top = splice.locate(lines, params.art_layers)
        splice.check_base(top, params.outline)
    except splice.NotPlaceholder as reason:
        return Outcome(text, False, f"Not the Line Art Studio base: {reason}. G-code left as it is.")

    machine = dc_replace(art_module.machine_from_config(get_config, top.tool), relative_e=top.relative_e)
    if params.layer_height and abs(params.layer_height - top.height) > 0.005:
        raise art_module.ArtError(
            f"The job uses a {params.layer_height:g} mm layer height but this slice uses {top.height:g} mm. "
            "Change the process preset's layer height, or the job's, and slice again."
        )
    if params.two_filaments and top.tool + 1 != params.art_filament:
        raise art_module.ArtError(
            f"The art layers use filament {top.tool + 1}, but the job asks for filament {params.art_filament}. "
            "Delete the base from the plate, press the save button again, and slice."
        )
    if params.nozzle and abs(params.nozzle - machine.nozzle) > 0.001:
        raise art_module.ArtError(
            f"The job is for a {params.nozzle:g} mm nozzle but the printer preset uses {machine.nozzle:g} mm."
        )
    splice.check_bed(top, shapes.extents(params.outline), machine)
    art = art_module.build(params, line, machine, top.height)
    block = gcode.emit(
        art,
        top.center[0],
        top.center[1],
        top.z,
        top.relative_e,
        debt_before=top.debt_start,
        e_after=top.e_end,
        pause=params.color_change == "pause" and not params.two_filaments,
        upper_layers=top.upper,
    )
    stats = art.stats()
    message = (
        f"Replaced the top {params.art_layers} layer(s) with a {stats['length_mm'] / 1000:.1f} m line from Z{top.z:g}, "
        f"{stats['time_s'] / 60:.0f} min."
    )
    return Outcome("\n".join(splice.replace(lines, top, block)), True, message)
