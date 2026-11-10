"""Static checks of the tab's sliders. tools/orca_mock loads the page; the browser check executes it."""
import re
from pathlib import Path

import pytest
from orca import harness

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "src" / "line_art_studio"
PAGE = "Line Art Studio"
SLIDER_FIELDS = {"spacing", "contrast", "gamma"}
BOUND_ATTRIBUTE = re.compile(r"\b(?:min|max)=")
LITERAL_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
MOTION = re.compile(r"\b(?:transition|animation)\b")


@pytest.fixture(autouse=True)
def clean():
    harness.reset()
    yield


@pytest.fixture
def page():
    return harness.load(ENTRY).capability(PAGE).get_ui()


def tags(page, pattern):
    return re.findall(rf"<input\b[^>]*{pattern}[^>]*>", page)


def range_inputs(page):
    return tags(page, r'type="range"')


def slider_row(page, field):
    rows = re.findall(r'<div class="ol-field ol-slider-row">.*?</div>', page, re.S)
    matching = [row for row in rows if f'id="{field}"' in row]
    assert len(matching) == 1, f"{field} needs exactly one slider row"
    return matching[0]


def slider_rules(page):
    return [rule for rule in re.findall(r"[^{}]+\{[^{}]*\}", page) if ".ol-slider" in rule]


def field_list(page):
    match = re.search(r"var fields = \[(.*?)\];", page)
    assert match, "the script keeps its field list"
    return re.findall(r'"(\w+)"', match.group(1))


def script_function(page, opening):
    start = page.index(opening)
    end = page.index("\n}", start)
    return page[start:end]


def tone_card(page):
    match = re.search(r"<details\b[^>]*>\s*<summary>Tone.*?</details>", page, re.S)
    assert match, "the tone settings stay in their card"
    return match.group(0)


def test_only_the_values_tuned_by_eye_get_a_slider(page):
    ids = {re.search(r'id="(\w+)_slider"', tag).group(1) for tag in range_inputs(page)}
    assert ids == SLIDER_FIELDS


@pytest.mark.parametrize("field", sorted(SLIDER_FIELDS))
def test_slider_shares_a_row_with_its_number_field(page, field):
    row = slider_row(page, field)
    assert f'id="{field}_slider"' in row
    assert 'class="ol-slider"' in row
    assert f'<label for="{field}">' in row
    assert "aria-label=" in row


@pytest.mark.parametrize("field", sorted(SLIDER_FIELDS))
def test_limits_are_not_written_into_the_page(page, field):
    assert not BOUND_ATTRIBUTE.search(tags(page, f'id="{field}"')[0])
    assert not BOUND_ATTRIBUTE.search(tags(page, f'id="{field}_slider"')[0])


def test_limits_are_read_from_init_before_the_params_are_shown(page):
    init = page[page.index('m.type === "init"'):page.index('m.type === "state"')]
    assert "applyLimits(m.limits)" in init
    assert init.index("applyLimits(m.limits)") < init.index("setParams(m.params)")


def test_a_dragged_slider_goes_through_the_debounce(page):
    wiring = script_function(page, "function wireSlider(")
    assert "request()" in wiring
    assert "compute()" not in wiring


def test_automatic_tone_is_a_labeled_checkbox_in_the_tone_settings(page):
    card = tone_card(page)
    assert re.search(r'Automatic tone\s*<input id="auto_tone" type="checkbox">', card)
    assert re.search(r'class="ol-muted"[^>]*>[^<]*light-to-dark range[^<]*sharpens', card)


def test_params_carry_automatic_tone(page):
    assert "auto_tone" in field_list(page)


def test_tone_starts_open_because_it_is_tuned_constantly(page):
    assert re.match(r"<details\b[^>]*\bopen\b", tone_card(page))


def test_slider_style_is_shared_and_cannot_widen_its_row(page):
    from_shared = next(rule for rule in slider_rules(page) if re.search(r"\.ol-slider\s*\{", rule))
    assert re.search(r"min-width:\s*0", from_shared)
    assert re.search(r"flex:\s*1 1 0", from_shared)


def test_slider_style_uses_only_theme_colors_and_does_not_move(page):
    rules = slider_rules(page)
    assert rules, "the shared style holds the slider rules"
    for rule in rules:
        assert not LITERAL_COLOR.search(rule), rule
        assert not MOTION.search(rule), rule
