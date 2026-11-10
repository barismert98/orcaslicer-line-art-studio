"""Static checks of the tab's frame shape picker. tools/orca_mock loads the page; the browser check executes it."""
import re
from pathlib import Path

import pytest
from orca import harness

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "src" / "line_art_studio"
PAGE = "Line Art Studio"
SHAPE_ID_LITERAL = re.compile(r"""["'](?:square|circle|rectangle|oval|rounded\w*|hexagon)["']""")
BOUND_ATTRIBUTE = re.compile(r"\b(?:min|max)=")
LITERAL_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
MOTION = re.compile(r"\b(?:transition|animation)\b")
SIZE_HINT = "Faces need about 150 mm. Below 100 mm only bold shapes read well."
LONGEST_PICTURE_SIDE = "600"


@pytest.fixture(autouse=True)
def clean():
    harness.reset()
    yield


@pytest.fixture
def page():
    return harness.load(ENTRY).capability(PAGE).get_ui()


def field_list(page):
    match = re.search(r"var fields = \[(.*?)\];", page)
    assert match, "the script keeps its field list"
    return re.findall(r'"(\w+)"', match.group(1))


def script_function(page, name):
    start = page.index(f"function {name}(")
    end = page.index("\n}", start)
    return page[start:end]


def script(page):
    return page[page.index("<script>"):page.index("</script>")]


def init_branch(page):
    return page[page.index('m.type === "init"'):page.index('m.type === "state"')]


def number_input(page, field):
    tags = re.findall(rf'<input id="{field}"[^>]*>', page)
    assert len(tags) == 1, f"{field} needs exactly one input"
    return tags[0]


def shape_rules(page):
    return [rule for rule in re.findall(r"[^{}]+\{[^{}]*\}", page) if ".ol-shape" in rule]


def test_params_send_shape_and_both_sides_instead_of_size(page):
    fields = field_list(page)
    assert "size" not in fields
    assert {"shape", "width", "height"} <= set(fields)


def test_the_old_size_field_is_gone(page):
    assert 'id="size"' not in page


def test_shape_ids_come_from_the_plugin(page):
    assert not SHAPE_ID_LITERAL.search(script(page))


def test_picker_is_built_from_the_init_reply_before_params_are_shown(page):
    init = init_branch(page)
    assert "m.shapes" in init
    assert init.index("m.shapes") < init.index("setParams(m.params)")


@pytest.mark.parametrize("field", ["width", "height"])
def test_side_limits_are_not_written_into_the_page(page, field):
    assert not BOUND_ATTRIBUTE.search(number_input(page, field))


def test_shortest_side_is_read_from_the_limits(page):
    assert "min_side" in script_function(page, "applyLimits")


def test_height_row_hides_for_a_one_sided_shape(page):
    assert re.search(r'<label class="ol-field" id="heightRow"[^>]*>', page)
    assert re.search(r'el\("heightRow"\)\.hidden\s*=', script(page))


def test_one_sided_height_follows_the_width_through_the_aspect(page):
    assert re.search(r"\.width\s*/\s*shape\.aspect", script_function(page, "artHeight"))


def test_half_typed_sides_are_never_sent(page):
    value = script_function(page, "fieldValue")
    assert re.search(r'f === "height"\) return artHeight\(\)', value)
    assert re.search(r'f === "width"\) return sides\.width', value)


def test_size_hint_stays(page):
    assert SIZE_HINT in page


def test_crop_follows_the_art_aspect(page):
    assert "artAspect()" in script_function(page, "cropBox")
    assert not re.search(r"\bb\.side\b", script(page))


def test_picture_longer_side_is_capped(page):
    assert f"PICTURE_LONGEST_SIDE = {LONGEST_PICTURE_SIDE}" in script(page)
    assert "PICTURE_LONGEST_SIDE" in script_function(page, "encode")


def test_crop_shows_what_will_not_print(page):
    overlay = script_function(page, "overlayShape")
    assert 'fill("evenodd")' in overlay
    assert "shape.outline" in overlay
    assert "overlayShape(" in script_function(page, "drawCrop")


def test_crop_outline_is_visible_before_a_picture_is_chosen(page):
    assert "if (!source) return" not in script_function(page, "drawCrop")


def test_preview_uses_the_outline_from_the_reply(page):
    assert re.search(r"drawPreview\(m\.size, m\.data, m\.outline\)", page)
    assert "destination-in" in script_function(page, "shapePreview")


def test_a_frame_filling_its_box_gets_no_overlay(page):
    assert "fillsBox(shape.outline)" in script_function(page, "overlayShape")
    assert "fillsBox(outline)" in script_function(page, "drawPreview")


def test_a_shape_change_crops_again_and_uses_the_debounce(page):
    choose = script_function(page, "chooseShape")
    assert "reframe()" in choose
    assert "compute()" not in choose
    reframe = script_function(page, "reframe")
    assert "encode()" in reframe
    assert "request()" in script_function(page, "encode")


def test_picker_buttons_are_named_for_screen_readers_and_touch(page):
    build = script_function(page, "buildShapePicker")
    assert 'setAttribute("aria-label"' in build
    assert 'setAttribute("aria-pressed"' in script_function(page, "showShape")
    assert "title" in build


def test_picker_wraps_rather_than_widens_the_column(page):
    grid = next(rule for rule in shape_rules(page) if re.search(r"\.ol-shapes\s*\{", rule))
    assert re.search(r"repeat\(auto-fit,\s*minmax\(", grid)


def test_picker_style_uses_only_theme_colors_and_does_not_move(page):
    rules = shape_rules(page)
    assert rules, "the shared style holds the picker rules"
    for rule in rules:
        assert not LITERAL_COLOR.search(rule), rule
        assert not MOTION.search(rule), rule


def test_save_stays_outside_the_scrolling_controls(page):
    controls = page[page.index('<div class="controls">'):page.index('<div class="stagewrap">')]
    assert 'id="shapes"' in controls
    assert 'id="save"' not in controls
