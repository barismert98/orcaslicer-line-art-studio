"""Runs against tools/orca_mock: a strict stand-in, not OrcaSlicer itself."""
import base64
import json
import re
import zipfile
from pathlib import Path

import pytest
from orca import harness
import orca

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "src" / "line_art_studio"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BAMBU = FIXTURES / "bambu_x1c_relative.gcode"
PAGE = "Line Art Studio"
SLICING = "Line Art Studio G-code"


@pytest.fixture(autouse=True)
def clean():
    harness.reset()
    yield


@pytest.fixture
def loaded():
    return harness.load(ENTRY)


def config_for(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^; ([a-z_0-9]+) = (.*)$", line)
        if match:
            values.setdefault(match.group(1), match.group(2))
    return values


def gradient(size=32):
    data = bytes(int(255 * x / (size - 1)) for _ in range(size) for x in range(size))
    return {"width": size, "height": size, "data": base64.b64encode(data).decode()}


def params(**extra):
    return {"size": 60.0, "line_width": 0.42, **extra}


def plate_holds(*objects):
    harness.set_host(model=lambda: harness.fake("orca.host.Model", objects=lambda: list(objects)))


def use_config(config):
    harness.set_host(preset_bundle=lambda: harness.fake("orca.host.PresetBundle", full_config_value=config.get))


def page_call(loaded, data):
    page = loaded.capability(PAGE)
    with harness._callback():
        page.on_message(data)
    if page._worker is not None:
        page._worker.join(60)
    return harness.posted[-1]


def preview_job(loaded, config, **extra):
    use_config(config)
    return page_call(loaded, {"cmd": "preview", "params": params(**extra), "image": gradient()})


def save_job(loaded, config, on_plate=False, added=True, **extra):
    preview_job(loaded, config, **extra)
    objects = []
    if on_plate:
        objects.append(harness.fake("orca.host.ModelObject", name="line_art_studio_base.stl", input_file=r"C:\\x\\line_art_studio_base.stl"))
    harness.set_host(model=lambda: harness.fake("orca.host.Model", objects=lambda: objects))
    sent = []

    def fake_add(path):
        sent.append(path)
        return added

    loaded.module.plate.add_to_plate = fake_add
    reply = page_call(loaded, {"cmd": "save", "params": params(**extra), "image": gradient()})
    reply["sent"] = sent
    return reply


def two_filament_config():
    return {**config_for(BAMBU), "filament_colour": "#FFFFFF;#101010"}


def test_registers_capabilities_and_asks_for_threads(loaded):
    assert sorted(c.get_name() for c in loaded.capabilities) == [PAGE, SLICING]
    assert any(p["threading"] for p in loaded.permissions)


def test_tab_icon_points_at_a_packaged_svg(loaded):
    icon = loaded.capability(PAGE).get_icon()
    assert icon.endswith("/icon.svg") and "\\" not in icon
    assert Path(icon).is_file() and Path(icon).read_text(encoding="utf-8").startswith("<svg")


def test_page_has_bridge_and_no_flow_controls(loaded):
    page = loaded.capability(PAGE).get_ui()
    assert "orca.postMessage" in page
    for gone in ("width_min", "width_max", "Flow multiplier", "hilbert"):
        assert gone not in page


def test_page_is_the_workbench_with_the_family_style(loaded):
    page = loaded.capability(PAGE).get_ui()
    assert "/*ONELINE_CSS*/" not in page and "--ol-surface" in page
    for part in ('id="checks"', 'id="lastSlice"', 'id="previewBox"', 'id="save"', "<details"):
        assert part in page
    fields = re.search(r"var fields = (\[.*?\]);", page).group(1)
    for name in json.loads(fields):
        assert f'id="{name}"' in page


def test_the_style_block_is_the_package_s_own_copy():
    assert (ENTRY / "oneline_ui.py").is_file()
    assert "from .oneline_ui import CSS" in (ENTRY / "ui.py").read_text(encoding="utf-8")


def test_init_lists_the_real_styles(loaded):
    use_config(config_for(BAMBU))
    plate_holds()
    with harness._callback():
        loaded.capability(PAGE).on_message({"cmd": "init"})
    init = next(m for m in harness.posted if m["type"] == "init")
    assert [m["id"] for m in init["modes"]] == list(loaded.module.modes.GENERATORS)
    assert init["params"]["mode"] == "tsp" and init["selected"] is False and init["on_plate"] is False


def test_init_sends_the_validated_limits_and_auto_tone_on(loaded):
    use_config(config_for(BAMBU))
    plate_holds()
    with harness._callback():
        loaded.capability(PAGE).on_message({"cmd": "init"})
    init = next(m for m in harness.posted if m["type"] == "init")
    core = loaded.module.art_module
    assert init["limits"] == {**{name: list(limits) for name, limits in core.SLIDER_LIMITS.items()}, "min_side": core.MIN_SIZE}
    assert [shape["id"] for shape in init["shapes"]] == list(loaded.module.shapes.SHAPES)
    assert init["params"]["auto_tone"] is True


def test_preview_reports_the_real_outline(loaded):
    plate_holds()
    reply = preview_job(loaded, config_for(BAMBU), shape="circle", width=70.0, height=70.0)
    assert len(reply["outline"]) == loaded.module.shapes.CURVE_SEGMENTS
    assert min(x for x, _ in reply["outline"]) == pytest.approx(0.0, abs=0.01)


def test_saving_an_oval_writes_a_matching_base_and_job(loaded):
    plate_holds()
    extra = {"shape": "oval", "width": 90.0, "height": 70.0}
    reply = save_job(loaded, config_for(BAMBU), **extra)
    with harness._callback():
        saved = json.loads((Path(orca.host.plugin.storage()) / "job.json").read_text(encoding="utf-8"))
    assert saved["params"]["shape"] == "oval" and saved["base"]["extents"] == [90.0, 70.0]
    assert Path(reply["stl"]).is_file()


def test_state_reads_the_presets_and_the_plate_each_time(loaded):
    config = {**config_for(BAMBU), "layer_height": "0.16", "slicing_pipeline_plugin": SLICING}
    use_config(config)
    plate_holds()
    state = page_call(loaded, {"cmd": "state"})
    assert state["type"] == "state" and state["selected"] is True and state["on_plate"] is False
    assert state["printer"]["layer_height"] == pytest.approx(0.16) and state["status"] is None
    config["layer_height"] = "0.2"
    config["slicing_pipeline_plugin"] = ""
    plate_holds(harness.fake("orca.host.ModelObject", name="line_art_studio_base.stl", input_file="line_art_studio_base.stl"))
    state = page_call(loaded, {"cmd": "state"})
    assert state["selected"] is False and state["on_plate"] is True
    assert state["printer"]["layer_height"] == pytest.approx(0.2)


def test_preview_carries_the_checklist_state(loaded):
    plate_holds()
    reply = preview_job(loaded, config_for(BAMBU))
    assert reply["selected"] is False and reply["on_plate"] is False


def test_init_offers_printer_values(loaded):
    use_config(config_for(BAMBU))
    with harness._callback():
        loaded.capability(PAGE).on_message({"cmd": "init"})
    sent = next(m for m in harness.posted if m["type"] == "init")["params"]
    assert sent["nozzle"] == pytest.approx(0.4) and sent["layer_height"] == pytest.approx(0.2)
    assert sent["line_width"] == pytest.approx(0.42) and sent["width"] == 150.0 and sent["shape"] == "square"


def test_preview_runs_on_a_worker_and_returns_the_picture(loaded):
    reply = preview_job(loaded, config_for(BAMBU))
    assert reply["type"] == "preview" and reply["stats"]["points"] > 100
    assert len(base64.b64decode(reply["data"])) == reply["size"] ** 2
    assert loaded.capability(PAGE)._worker is not None


def test_preview_reuses_the_line_when_only_printer_values_change(loaded):
    config = config_for(BAMBU)
    preview_job(loaded, config)
    page = loaded.capability(PAGE)
    first = page._line
    preview_job(loaded, config, speed=20.0)
    assert page._line is first


def test_a_newer_preview_replaces_the_older_one(loaded):
    use_config(config_for(BAMBU))
    page = loaded.capability(PAGE)
    message = {"cmd": "preview", "params": params(), "image": gradient()}
    with harness._callback():
        page.on_message(message)
        old = page._worker
        page.on_message({**message, "params": params(size=70.0)})
    old.join(60)
    page._worker.join(60)
    previews = [m for m in harness.posted if m["type"] == "preview"]
    assert len(previews) == 1 and page._line_key is not None


def test_refused_threads_still_compute(loaded, monkeypatch):
    def refuse(self):
        raise PermissionError("no threads")

    monkeypatch.setattr(loaded.module.threading.Thread, "start", refuse)
    reply = preview_job(loaded, config_for(BAMBU))
    assert reply["type"] == "preview"


def test_page_reports_bad_settings(loaded):
    reply = preview_job(loaded, config_for(BAMBU), line_width=2.0)
    assert reply["type"] == "error"


def test_preview_without_image_asks_for_one(loaded):
    use_config(config_for(BAMBU))
    assert page_call(loaded, {"cmd": "preview", "params": params(), "image": None})["type"] == "error"


def test_save_without_a_line_asks_the_page_to_compute(loaded):
    use_config(config_for(BAMBU))
    reply = page_call(loaded, {"cmd": "save", "params": params(), "image": gradient()})
    assert reply["type"] == "need_route"


def test_save_adds_base_to_plate(loaded):
    reply = save_job(loaded, config_for(BAMBU))
    assert reply["plate"] == "added" and reply["sent"] == [reply["stl"]]
    assert reply["height"] == pytest.approx(1.0)
    assert Path(reply["stl"]).stat().st_size == 84 + 16 * 50


def test_save_does_not_duplicate_base(loaded):
    config = config_for(BAMBU)
    save_job(loaded, config)
    reply = save_job(loaded, config, on_plate=True)
    assert reply["plate"] == "present" and reply["sent"] == []


def test_save_reports_stale_base(loaded):
    config = config_for(BAMBU)
    save_job(loaded, config)
    reply = save_job(loaded, config, on_plate=True, size=70.0)
    assert reply["plate"] == "stale" and reply["sent"] == []


def test_save_falls_back_to_manual(loaded):
    assert save_job(loaded, config_for(BAMBU), added=False)["plate"] == "manual"


def test_two_filaments_write_a_two_part_3mf(loaded):
    harness.set_host(app_info=lambda: {"version": "2.5.0"})
    reply = save_job(loaded, two_filament_config(), base_filament=1, art_filament=2, art_layers=2, layer_height=0.2)
    assert reply["plate"] == "added" and reply["stl"].endswith(".3mf") and reply["height"] == pytest.approx(1.2)
    with zipfile.ZipFile(reply["stl"]) as archive:
        settings = archive.read("Metadata/model_settings.config").decode()
        meshes = archive.read("3D/Objects/line_art_studio_base.model").decode()
        assert "Metadata/project_settings.config" not in archive.namelist()
    assert re.findall(r'<part id="(\d)".*?key="extruder" value="(\d)"', settings) == [("1", "1"), ("2", "2")]
    assert '<object id="2"' in meshes


def test_unknown_filament_slot_is_refused(loaded):
    config = config_for(BAMBU) | {"filament_colour": "#FFFFFF"}
    assert preview_job(loaded, config, art_filament=3)["type"] == "error"


def test_slicing_replaces_the_top_layer_from_the_saved_line(loaded, tmp_path):
    config = config_for(BAMBU)
    save_job(loaded, config)
    target = tmp_path / "plate.gcode"
    target.write_bytes(BAMBU.read_bytes())
    result = loaded.run_slicing(SLICING, gcode_path=str(target), config_value=config.get)
    assert result.status == orca.PluginResult.Success
    text = target.read_text(encoding="utf-8")
    assert "; LINE_ART_STUDIO_START" in text and "; EXECUTABLE_BLOCK_END" in text
    reply = page_call(loaded, {"cmd": "status"})
    assert reply["status"]["ok"] and reply["status"]["changed"]
    first = target.read_bytes()
    loaded.run_slicing(SLICING, gcode_path=str(target), config_value=config.get)
    assert target.read_bytes() == first


def test_slicing_ignores_other_steps(loaded, tmp_path):
    target = tmp_path / "plate.gcode"
    target.write_text("x")
    result = loaded.run_slicing(SLICING, step=orca.slicing.Step.posSlice, gcode_path=str(target))
    assert result.status == orca.PluginResult.Success and target.read_text() == "x"


def test_slicing_leaves_other_prints_alone(loaded, tmp_path):
    config = config_for(BAMBU)
    save_job(loaded, config, size=80.0)
    target = tmp_path / "plate.gcode"
    target.write_bytes(BAMBU.read_bytes())
    result = loaded.run_slicing(SLICING, gcode_path=str(target), config_value=config.get)
    assert result.status == orca.PluginResult.Success and target.read_bytes() == BAMBU.read_bytes()
    assert "Not the Line Art Studio base" in result.message


def test_slicing_without_job_does_nothing(loaded, tmp_path):
    target = tmp_path / "plate.gcode"
    target.write_bytes(BAMBU.read_bytes())
    result = loaded.run_slicing(SLICING, gcode_path=str(target), config_value=lambda k: None)
    assert result.status == orca.PluginResult.Success and target.read_bytes() == BAMBU.read_bytes()
