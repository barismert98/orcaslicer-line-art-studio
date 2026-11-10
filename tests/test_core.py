"""Invariants on the line and its G-code. No orca import in the code under test."""
import math
import re
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest

from core import art as A, autotone, gcode, modes, pipeline, preview, shapes, splice, stipple, tour, tsp
from core.gcode import END_MARK, START_MARK
from core.image import GrayImage, tone

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BAMBU = FIXTURES / "bambu_x1c_relative.gcode"
KLIPPER = FIXTURES / "klipper_absolute.gcode"
MACHINE = A.Machine(max_volumetric=15.0, relative_e=True)
WORD = re.compile(r"([XYZEF])([-+]?[0-9]*\.?[0-9]+)")
PARAMS = A.Params(width=60.0, height=60.0)


def gradient(size=64):
    return GrayImage(size, size, bytes(int(255 * x / (size - 1)) for _ in range(size) for x in range(size)))


def flat(value, size=16):
    return GrayImage(size, size, bytes([value]) * (size * size))


def route(params, image, machine, *stop):
    return modes.generate(params, image, machine, *stop).points


@lru_cache(maxsize=None)
def whole():
    return modes.generate(PARAMS, gradient(), MACHINE)


def line():
    return tuple(whole().points)


def art(params=PARAMS, machine=MACHINE, layer=0.2):
    return A.build(params, whole(), machine, layer)


def job(params=PARAMS):
    return pipeline.job_to_dict(params, whole())


def parse(block):
    moves = []
    for text in block:
        words = {k: float(v) for k, v in WORD.findall(text.split(";")[0])}
        if text.startswith("G1"):
            moves.append(words)
    return moves


def run(block, relative):
    position = 0.0
    deltas = []
    x = y = None
    for words in parse(block):
        x = words.get("X", x)
        y = words.get("Y", y)
        if "E" not in words:
            deltas.append((x, y, None, words))
            continue
        delta = words["E"] if relative else words["E"] - position
        position = position + delta if relative else words["E"]
        deltas.append((x, y, delta, words))
    return deltas


def extrusion_section(entries):
    moving = [i for i, e in enumerate(entries) if e[2] and e[2] > 0 and ("X" in e[3] or "Y" in e[3])]
    return entries[moving[0] : moving[-1] + 1]


def test_line_stays_on_the_base():
    half = PARAMS.width / 2 - PARAMS.inset
    assert len(line()) > 100
    assert all(abs(x) <= half + 1e-9 and abs(y) <= half + 1e-9 for x, y in line())


def test_line_is_one_stroke_with_no_repeated_points():
    assert len(set(line())) == len(line())
    assert min(math.dist(a, b) for a, b in zip(line(), line()[1:])) > 0


def test_line_never_crosses_itself():
    assert tour.crossings(list(line())) == []


def test_strands_keep_a_line_width_apart():
    assert tour.crowded(list(line()), PARAMS.line_width) == set()


def test_same_input_gives_the_same_line():
    assert tuple(route(PARAMS, gradient(), MACHINE)) == line()


def test_dark_side_gets_more_line():
    # x grows to the right; the gradient is dark on the left.
    points = line()
    left = sum(1 for x, _ in points if x < 0)
    assert left > 2 * (len(points) - left)


def test_ink_follows_tone():
    """Ink goes with 1 / spacing, so the darker half must not be merely denser in points."""
    dark = route(PARAMS, flat(40), MACHINE)
    mid = route(PARAMS, flat(140), MACHINE)
    length = lambda p: sum(math.dist(a, b) for a, b in zip(p, p[1:]))  # noqa: E731
    assert 1.5 < length(dark) / length(mid) < 3.5


def test_image_top_is_positive_y():
    image = GrayImage(32, 32, bytes(0 if row < 16 else 255 for row in range(32) for _ in range(32)))
    points = route(PARAMS, image, MACHINE)
    assert sum(1 for _, y in points if y > 0) > 0.9 * len(points)


def test_invert_flips_the_picture():
    points = route(replace(PARAMS, invert=True), gradient(), MACHINE)
    right = sum(1 for x, _ in points if x > 0)
    assert right > 2 * (len(points) - right)


def test_white_picture_is_refused():
    with pytest.raises(A.ArtError, match="too light"):
        route(PARAMS, flat(255), MACHINE)


def test_huge_black_picture_is_refused():
    with pytest.raises(A.ArtError, match="points"):
        route(replace(PARAMS, width=250.0, height=250.0), flat(0), MACHINE)


def test_cancel_stops_the_work():
    def stop():
        raise stipple.Canceled()

    with pytest.raises(stipple.Canceled):
        route(PARAMS, gradient(), MACHINE, stop)


def test_route_key_ignores_printer_values_only():
    image = gradient()
    key = A.route_key(PARAMS, image)
    assert A.route_key(replace(PARAMS, speed=10.0, art_layers=3, layer_height=0.1), image) == key
    assert A.route_key(replace(PARAMS, line_width=0.4), image) != key
    assert A.route_key(PARAMS, flat(10, 64)) != key


def test_clean_uncrosses():
    bow = [(0, 0), (10, 10), (10, 0), (0, 10)]
    fixed = tour.clean(bow, 0.4)
    assert tour.crossings(fixed) == [] and sorted(fixed) == sorted(bow)


def test_clean_removes_a_point_too_close_to_another_strand():
    # A far excursion comes back to touch the first segment.
    path = [(0, 0), (20, 0), (20, 10), (10, 0.2), (0, 10)]
    fixed = tour.clean(path, 0.4)
    assert (10, 0.2) not in fixed and tour.crowded(fixed, 0.4) == set()


def test_width_is_constant():
    a = art()
    assert set(a.widths) == {PARAMS.line_width} and len(a.widths) == len(a.points) - 1


def test_speed_respects_the_volumetric_limit():
    a = art(machine=replace(MACHINE, max_volumetric=2.0))
    assert a.stats()["max_flow"] <= 2.0 + 1e-9 and a.speed == pytest.approx(2.0 / (0.42 * 0.2))


@pytest.mark.parametrize(
    "bad",
    [{"width": 50.0, "height": 50.0}, {"line_width": 0.1}, {"line_width": 0.9}, {"spacing": 1.0}, {"art_layers": 0}, {"nozzle": 2.0}, {"layer_height": 0.5}, {"gamma": 0.0}],
)
def test_bad_inputs_are_refused(bad):
    with pytest.raises(A.ArtError):
        route(replace(PARAMS, **bad), gradient(), MACHINE)


def narrow_picture(size=64):
    """Everything between levels 100 and 150, as a washed-out photo would be."""
    return GrayImage(size, size, bytes(100 + 50 * x // (size - 1) for _ in range(size) for x in range(size)))


def test_auto_tone_stretches_the_real_range():
    prepared = autotone.prepare(narrow_picture())
    assert min(prepared.data) <= 8 and max(prepared.data) >= 247


def test_auto_tone_ignores_a_few_outliers():
    data = bytearray(narrow_picture().data)
    data[:8], data[-8:] = bytes(8), bytes([255]) * 8
    prepared = autotone.prepare(GrayImage(64, 64, bytes(data)))
    assert min(prepared.data[1000:3000]) < 40 and max(prepared.data[1000:3000]) > 215


def test_auto_tone_leaves_a_flat_picture_alone():
    assert autotone.prepare(flat(140)).data == flat(140).data


def test_auto_tone_sharpens_an_edge():
    size = 100
    levels = [20] * 5 + [90] * 45 + [170] * 45 + [230] * 5  # the outer bands keep the edge inside the range
    row = autotone.prepare(GrayImage(size, size, bytes(levels) * size)).data[50 * size:51 * size]
    assert row[49] < row[25] and row[50] > row[75]


def test_auto_tone_is_on_by_default_and_changes_the_line():
    assert A.Params().auto_tone
    on = route(replace(PARAMS, auto_tone=True), narrow_picture(), MACHINE)
    off = route(replace(PARAMS, auto_tone=False), narrow_picture(), MACHINE)
    assert on != off


def test_turning_auto_tone_off_gives_the_line_from_before_it_existed():
    params = replace(PARAMS, auto_tone=False)
    assert modes.generate(params, narrow_picture(), MACHINE).points == tsp.generate(params, narrow_picture(), MACHINE).points


def test_auto_tone_is_part_of_the_route_key():
    image = narrow_picture()
    assert A.route_key(replace(PARAMS, auto_tone=True), image) != A.route_key(replace(PARAMS, auto_tone=False), image)


def test_auto_tone_is_saved_in_the_job():
    saved = job(replace(PARAMS, auto_tone=False))
    assert saved["params"]["auto_tone"] is False
    assert pipeline.job_from_dict(job())[0].auto_tone is PARAMS.auto_tone


def test_a_job_from_before_auto_tone_is_treated_as_off_and_keeps_its_line():
    older = job()
    del older["params"]["auto_tone"]
    params, loaded = pipeline.job_from_dict(older)
    assert params.auto_tone is False
    assert all(math.dist(a, b) < 0.001 for a, b in zip(loaded.points, line()))
    assert pipeline.process(BAMBU.read_text(encoding="utf-8"), older, {}.get).changed


@pytest.mark.parametrize("name, value", [("contrast", 0.05), ("contrast", 9.0), ("gamma", 0.05), ("gamma", 9.0)])
def test_tone_settings_are_limited(name, value):
    with pytest.raises(A.ArtError):
        replace(PARAMS, **{name: value}).validate(MACHINE)


@pytest.mark.parametrize("name, limits", list(A.SLIDER_LIMITS.items()))
def test_the_limits_shown_on_the_page_are_the_ones_validated(name, limits):
    replace(PARAMS, **{name: limits[0]}).validate(MACHINE)
    replace(PARAMS, **{name: limits[1]}).validate(MACHINE)


def test_defaults_are_the_ones_chosen_on_the_benchmark():
    defaults = A.Params()
    assert (defaults.spacing, defaults.contrast, defaults.auto_tone) == (1.3, 1.25, True)


def test_tone():
    assert tone(0.5, 1, 2) == pytest.approx(0.25)
    assert tone(0.0, 2, 1) == 0.0 and tone(1.0, 2, 1) == 1.0


@pytest.mark.parametrize("relative", [True, False])
def test_gcode_is_one_extruding_run(relative):
    a = art(machine=replace(MACHINE, relative_e=relative))
    block = gcode.emit(a, 100.0, 100.0, 1.0, relative, e_after=7.5)
    assert block[0] == START_MARK and block[-1] == END_MARK
    entries = run(block, relative)
    section = extrusion_section(entries)
    assert all(e[2] is not None and e[2] > 0 for e in section) and len(section) == len(a.widths)
    assert sum(1 for e in entries if e[2] is not None and e[2] < 0) == 2
    for entry, amount in zip(section, gcode.extrusion_lengths(a)):
        assert entry[2] == pytest.approx(amount, abs=2e-5)
    assert all(abs(x - 100) <= 30 and abs(y - 100) <= 30 for x, y, _, _ in section)


@pytest.mark.parametrize("relative", [True, False])
def test_line_layers_retrace_without_travel(relative):
    a = art(machine=replace(MACHINE, relative_e=relative))
    block = gcode.emit(a, 100.0, 100.0, 1.0, relative, upper_layers=((1.2, ["; layer two"]),))
    section = [e for e in extrusion_section(run(block, relative)) if "Z" not in e[3] and "X" in e[3]]
    assert "; layer two" in block and len(section) == 2 * len(a.widths) and all(e[2] > 0 for e in section)


def test_pause_goes_before_travel():
    machine = replace(MACHINE, pause_gcode="M400 U1")
    block = gcode.emit(art(machine=machine), 100, 100, 1.0, True, pause=True)
    assert block.index("M400 U1") < next(i for i, l in enumerate(block) if l.startswith("G1 X"))


def test_job_round_trip():
    params, loaded = pipeline.job_from_dict(job())
    assert params == PARAMS and len(loaded.points) == len(line())
    assert all(math.dist(a, b) < 0.001 for a, b in zip(loaded.points, line()))
    assert loaded.widths == pytest.approx(whole().widths, abs=0.001)


def test_job_carries_mode_and_format_version():
    saved = job()
    assert saved["mode"] == "tsp" and saved["version"] == pipeline.JOB_VERSION


def test_a_job_from_before_the_format_change_asks_for_a_new_save():
    with pytest.raises(A.ArtError, match="older version"):
        pipeline.process(BAMBU.read_text(encoding="utf-8"), {"version": 1, "params": {}, "route": []}, {}.get)


@pytest.mark.parametrize("mode", list(modes.GENERATORS))
def test_every_mode_has_the_same_interface(mode):
    made = modes.GENERATORS[mode](PARAMS, gradient(), MACHINE)
    assert isinstance(made, A.Line) and len(made.widths) == len(made.points) - 1


def test_core_has_no_orca_import_and_modes_stay_out_of_the_output_step():
    core = Path(pipeline.__file__).parent
    for path in core.glob("*.py"):
        assert "import orca" not in path.read_text(encoding="utf-8")
    for name in ("gcode.py", "pipeline.py", "splice.py", "preview.py"):
        assert "tsp" not in (core / name).read_text(encoding="utf-8")


def test_another_plugins_base_of_the_same_size_is_left_alone():
    text = BAMBU.read_text(encoding="utf-8").replace("line_art_studio_base", "flow_line_art_disc")
    outcome = pipeline.process(text, job(), {}.get)
    assert not outcome.changed and outcome.text == text and "no object named" in outcome.message


def test_machine_from_config():
    values = {
        "nozzle_diameter": "0.6", "filament_diameter": "1.75,2.85", "printable_area": "0x0,200x0,200x180,0x180",
        "use_relative_e_distances": "0", "machine_pause_gcode": "PAUSE\\nM400",
    }
    m = A.machine_from_config(values.get, tool=1)
    assert m.nozzle == 0.6 and m.filament_diameter == 2.85 and m.bed == (0, 0, 200, 180) and not m.relative_e
    assert m.pause_gcode == "PAUSE\nM400"


@pytest.mark.parametrize("path,relative", [(BAMBU, True), (KLIPPER, False)])
def test_locate_real_square_slices(path, relative):
    top = splice.locate(path.read_text(encoding="utf-8").split("\n"))
    assert top.relative_e is relative and top.height == 0.2
    assert top.size == pytest.approx((60.0, 60.0), abs=1.0)
    splice.check_base(top, shapes.outline("square", 60.0, 60.0))


def test_shape_check_refuses_a_disc():
    top = splice.locate(BAMBU.read_text(encoding="utf-8").split("\n"))
    with pytest.raises(splice.NotPlaceholder, match="shape"):
        splice.check_base(replace(top, diagonal=60.0), shapes.outline("square", 60.0, 60.0))


@pytest.mark.parametrize("path", [BAMBU, KLIPPER])
def test_real_slice_end_to_end(path):
    text = path.read_text(encoding="utf-8")
    config = {"printable_area": "0x0,256x0,256x256,0x256"}
    outcome = pipeline.process(text, job(), config.get)
    assert outcome.changed and splice.is_done(outcome.text)
    lines = outcome.text.split("\n")
    start, end = lines.index(START_MARK), lines.index(END_MARK)
    top = splice.locate(text.split("\n"))
    assert lines[end + 1] == text.split("\n")[top.region_end]
    assert lines[start + 1].startswith("; layer height 0.2")
    assert pipeline.process(outcome.text, job(), config.get).text == outcome.text


@pytest.mark.parametrize("change,word", [({"layer_height": 0.16}, "layer height"), ({"nozzle": 0.6, "line_width": 0.6}, "nozzle")])
def test_slice_refuses_a_mismatch(change, word):
    with pytest.raises(A.ArtError, match=word):
        pipeline.process(BAMBU.read_text(encoding="utf-8"), job(replace(PARAMS, **change)), {"nozzle_diameter": "0.4"}.get)


def test_other_print_is_left_alone():
    text = BAMBU.read_text(encoding="utf-8")
    outcome = pipeline.process(text, job(replace(PARAMS, width=100.0, height=100.0)), {}.get)
    assert not outcome.changed and outcome.text == text and "Line Art Studio base" in outcome.message


def test_two_filaments_skip_the_pause_and_check_the_tool():
    text = BAMBU.read_text(encoding="utf-8")
    config = {"machine_pause_gcode": "M400 U1", "nozzle_diameter": "0.4"}
    assert "M400 U1" in pipeline.process(text, job(), config.get).text
    with pytest.raises(A.ArtError, match="filament 1"):
        pipeline.process(text, job(replace(PARAMS, base_filament=2, art_filament=3)), config.get)


def test_bed_check():
    with pytest.raises(ValueError, match="printable area"):
        pipeline.process(BAMBU.read_text(encoding="utf-8"), job(), {"printable_area": "0x0,10x0,10x10,0x10"}.get)


def test_preview_size_and_ink():
    rendered = preview.render(art(), 200)
    assert len(rendered) == 200 * 200
    left = sum(sum(rendered[row * 200 : row * 200 + 100]) for row in range(200))
    right = sum(sum(rendered[row * 200 + 100 : row * 200 + 200]) for row in range(200))
    assert left > 1.5 * right
