"""Line Art Studio for OrcaSlicer 2.5."""
import base64
import json
import os
import re
import threading

import orca

from . import plate
from .core import art as art_module
from .core import modes, pipeline, placeholder, preview, shapes
from .core.image import GrayImage
from .core.stipple import Canceled
from .ui import PAGE_HTML

JOB_FILE = "job.json"
STATUS_FILE = "last_run.json"
BASE_NAME = placeholder.BASE_NAME
PREVIEW_SIZE = 640
PAGE_NAME = "Line Art Studio"
SLICING_NAME = "Line Art Studio G-code"


def storage_path(name):
    return os.path.join(orca.host.plugin.storage(), name)


def read_json(name):
    try:
        with open(storage_path(name), encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None


def write_json(name, data):
    with open(storage_path(name), "w", encoding="utf-8") as handle:
        json.dump(data, handle)


def preset_value(key):
    try:
        return orca.host.preset_bundle().full_config_value(key)
    except (RuntimeError, KeyError):
        return None


def current_layer_height():
    try:
        return float(preset_value("layer_height"))
    except (TypeError, ValueError):
        return 0.2


def stack_heights(params, layer_height):
    """Thickness of the base, the art and the whole print, given the slicer's first layer."""
    try:
        first = float(preset_value("initial_layer_print_height"))
    except (TypeError, ValueError):
        first = layer_height
    base = first + (params.base_layers - 1) * layer_height
    art = params.art_layers * layer_height
    return {"base": base, "art": art, "total": base + art}


def printer_state():
    return {"nozzle": art_module.machine_from_config(preset_value).nozzle, "layer_height": current_layer_height()}


def slicing_step_selected():
    return SLICING_NAME in str(preset_value("slicing_pipeline_plugin") or "")


def filament_slots():
    """The project's filaments, in slot order; slot numbers start at 1."""
    try:
        names = list(orca.host.preset_bundle().current_filament_preset_names())
    except (RuntimeError, AttributeError):
        names = []
    colors = re.findall(r"#[0-9A-Fa-f]{6}", str(preset_value("filament_colour") or ""))
    count = max(len(names), len(colors), 1)
    return [
        {
            "slot": index + 1,
            "name": names[index] if index < len(names) else f"Filament {index + 1}",
            "color": colors[index] if index < len(colors) else "#808080",
        }
        for index in range(count)
    ]


def running_version():
    return str(orca.host.app_info()["version"])


def base_on_plate():
    try:
        objects = orca.host.model().objects()
    except RuntimeError:
        return False
    return any(BASE_NAME in (obj.input_file or obj.name or "") for obj in objects)


def image_from_message(raw):
    return GrayImage.from_base64(raw["width"], raw["height"], raw["data"]) if raw else None


class LineArtPage(orca.pages.PagesPluginCapabilityBase):
    _generation = 0
    _worker = None
    _line_key = None
    _line = None

    def get_name(self):
        return PAGE_NAME

    def get_ui(self):
        return PAGE_HTML

    def get_icon(self):
        """OrcaSlicer strips the extension, adds .svg and uses an existing path as it is."""
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.svg").replace("\\", "/")

    def on_message(self, data):
        handlers = {
            "init": self._init,
            "preview": self._preview,
            "save": self._save,
            "status": self._status,
            "state": self._state,
        }
        handler = handlers.get(data.get("cmd"))
        if handler is None:
            return
        try:
            handler(data)
        except (art_module.ArtError, ValueError, OSError) as error:
            self.post_message({"type": "error", "message": str(error)})

    def _init(self, _data):
        machine = art_module.machine_from_config(preset_value)
        defaults = art_module.Params(
            nozzle=machine.nozzle,
            layer_height=current_layer_height(),
            line_width=round(machine.nozzle * 1.05, 2),
        )
        self.post_message({
            "type": "init",
            "modes": modes.CHOICES,
            "shapes": shapes.choices(),
            "limits": {**{name: list(limits) for name, limits in art_module.SLIDER_LIMITS.items()}, "min_side": art_module.MIN_SIZE},
            "params": defaults.to_dict(),
            "machine": {
                "nozzle": machine.nozzle,
                "filament": machine.filament_diameter,
                "layer_height": current_layer_height(),
                "max_flow": machine.max_volumetric,
                "bed": list(machine.bed),
                "pause": bool(machine.pause_gcode),
            },
            "filaments": filament_slots(),
            "selected": slicing_step_selected(),
            "on_plate": base_on_plate(),
        })
        self._status(None)

    def _state(self, _data):
        """What the checklist shows: read from the presets and the plate each time, never remembered."""
        self.post_message({
            "type": "state",
            "printer": printer_state(),
            "selected": slicing_step_selected(),
            "on_plate": base_on_plate(),
            "filaments": filament_slots(),
            "status": read_json(STATUS_FILE),
        })

    def _request(self, data):
        params = art_module.Params.from_dict(data["params"])
        slots = len(filament_slots())
        if max(params.base_filament, params.art_filament) > slots:
            raise art_module.ArtError(f"This project has {slots} filament(s). Add more in the filament list first.")
        return params, image_from_message(data.get("image"))

    def _preview(self, data):
        """Everything from the host is read here; the worker only computes and posts."""
        params, image = self._request(data)
        if image is None:
            raise art_module.ArtError("Pick an image first.")
        machine = art_module.machine_from_config(preset_value)
        layer_height = params.layer_height or current_layer_height()
        reply = {
            "type": "preview",
            "size": PREVIEW_SIZE,
            "outline": shapes.canvas_outline(params.outline),
            "stack": stack_heights(params, layer_height),
            "filaments": filament_slots(),
            "printer": printer_state(),
            "selected": slicing_step_selected(),
            "on_plate": base_on_plate(),
        }
        self._generation += 1
        generation = self._generation

        def stop():
            if generation != self._generation:
                raise Canceled()

        def work():
            try:
                key = art_module.route_key(params, image)
                line = self._line if key == self._line_key else modes.generate(params, image, machine, stop)
                art = art_module.build(params, line, machine, layer_height)
                coverage = preview.render(art, PREVIEW_SIZE)
                stop()
                self._line_key, self._line = key, line
                self.post_message({**reply, "data": base64.b64encode(coverage).decode("ascii"), "stats": art.stats()})
            except Canceled:
                pass
            except ValueError as error:  # ArtError and TourError included
                if generation == self._generation:
                    self.post_message({"type": "error", "message": str(error)})

        worker = threading.Thread(target=work, name="line-art-studio-route", daemon=True)
        try:
            worker.start()
            self._worker = worker
        except PermissionError:  # the user refused threads: slower, but it still works
            work()

    def _save(self, data):
        params, image = self._request(data)
        if image is None:
            raise art_module.ArtError("Pick an image first.")
        if art_module.route_key(params, image) != self._line_key:
            self.post_message({"type": "need_route"})
            return
        machine = art_module.machine_from_config(preset_value)
        art = art_module.build(params, self._line, machine, params.layer_height or current_layer_height())
        stack = stack_heights(params, art.layer_height)
        height = stack["total"]
        base = {
            "shape": params.shape,
            "extents": [params.width, params.height],
            "height": height,
            "filaments": [params.base_filament, params.art_filament],
        }
        previous = read_json(JOB_FILE) or {}
        job = pipeline.job_to_dict(params, self._line)
        job["base"] = base
        write_json(JOB_FILE, job)
        if params.two_filaments:
            bed = art.machine.bed
            content = placeholder.two_filament_3mf(
                params.outline,
                stack["base"],
                height,
                params.base_filament,
                params.art_filament,
                ((bed[0] + bed[2]) / 2, (bed[1] + bed[3]) / 2),
                running_version(),
            )
            path = storage_path(BASE_NAME + ".3mf")
        else:
            content = placeholder.base_stl(params.outline, height)
            path = storage_path(BASE_NAME + ".stl")
        with open(path, "wb") as handle:
            handle.write(content)
        if base_on_plate():
            state = "present" if previous.get("base") == base else "stale"
        else:
            state = "added" if plate.add_to_plate(path) else "manual"
        self.post_message({"type": "saved", "stl": path, "height": height, "plate": state})

    def _status(self, _data):
        self.post_message({"type": "status", "status": read_json(STATUS_FILE)})


class LineArtSlicing(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return SLICING_NAME

    def execute(self, ctx):
        if ctx.step != orca.slicing.Step.psGCodePostProcess:
            return orca.ExecutionResult.success("")
        try:
            with open(ctx.gcode_path, encoding="utf-8", newline="") as handle:
                text = handle.read()
            outcome = pipeline.process(text, read_json(JOB_FILE), ctx.config_value)
            if outcome.changed:
                with open(ctx.gcode_path, "w", encoding="utf-8", newline="") as handle:
                    handle.write(outcome.text)
        except (art_module.ArtError, ValueError, OSError) as error:
            write_json(STATUS_FILE, {"ok": False, "message": str(error)})
            return orca.ExecutionResult.failure(orca.PluginResult.RecoverableError, f"Line Art Studio: {error}")
        write_json(STATUS_FILE, {"ok": True, "changed": outcome.changed, "message": outcome.message})
        return orca.ExecutionResult.success(outcome.message)


@orca.plugin
class LineArtStudioPlugin(orca.base):
    def register_capabilities(self):
        orca.request_permissions(threading=True)
        orca.register_capability(LineArtPage)
        orca.register_capability(LineArtSlicing)
