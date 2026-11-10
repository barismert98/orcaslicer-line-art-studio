"""The art's outer shape: one polygon behind the base, the mask, the fit and the splice check."""
import io
import math
import re
import struct
import zipfile
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from core import art as A, modes, pipeline, placeholder, preview, shapes, splice, stipple, tsp
from core.image import GrayImage

MACHINE = A.Machine(max_volumetric=15.0, relative_e=True)
ALL_SHAPES = list(shapes.SHAPES)
TWO_SIDED = [name for name, shape in shapes.SHAPES.items() if shape.sides == 2]
WIDE, TALL = 90.0, 70.0
BAMBU = Path(__file__).resolve().parent / "fixtures" / "bambu_x1c_relative.gcode"


def params_for(shape, width=WIDE, height=TALL):
    return A.Params.from_dict({"shape": shape, "width": width, "height": height})


def gradient(size=64):
    return GrayImage(size, size, bytes(int(200 * x / (size - 1)) for _ in range(size) for x in range(size)))


def rim_of(shape):
    return params_for(shape).outline


def test_the_shapes_on_offer():
    assert ALL_SHAPES == ["square", "circle", "rectangle", "oval", "rounded_rectangle", "hexagon"]
    assert TWO_SIDED == ["rectangle", "oval", "rounded_rectangle"]


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_every_outline_is_convex_counter_clockwise_and_centered(shape):
    rim = rim_of(shape)
    turns = [
        (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        for a, b, c in zip(rim, rim[1:] + rim[:1], rim[2:] + rim[:2])
    ]
    assert min(turns) > -1e-9
    assert sum(x for x, _ in rim) == pytest.approx(0.0, abs=1e-6) and sum(y for _, y in rim) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("shape", TWO_SIDED)
def test_two_sided_shapes_take_both_lengths(shape):
    assert shapes.extents(rim_of(shape)) == pytest.approx((WIDE, TALL))


@pytest.mark.parametrize("shape", ["square", "circle"])
def test_equal_sided_shapes_follow_the_width(shape):
    params = params_for(shape)
    assert params.height == WIDE and shapes.extents(params.outline) == pytest.approx((WIDE, WIDE))


def test_a_hexagon_is_regular_flat_topped_and_measured_across_corners():
    params = params_for("hexagon")
    assert params.height == pytest.approx(WIDE * math.sqrt(3) / 2)
    assert shapes.extents(params.outline) == pytest.approx((WIDE, params.height))
    rim = params.outline
    sides = [math.dist(a, b) for a, b in zip(rim, rim[1:] + rim[:1])]
    assert len(rim) == 6 and max(sides) == pytest.approx(min(sides))


def test_a_rounded_rectangle_corner_is_a_share_of_the_shorter_side():
    width_at_top = shapes.span(shapes.half_planes(rim_of("rounded_rectangle")), TALL / 2 - 1e-6, 0.0)
    flat_top = width_at_top[1] - width_at_top[0]
    assert flat_top == pytest.approx(WIDE - 2 * shapes.CORNER_SHARE * TALL, abs=0.5)


def test_the_span_is_inset_by_a_true_distance():
    planes = shapes.half_planes(rim_of("rectangle"))
    assert shapes.span(planes, 0.0, 2.0) == pytest.approx((-WIDE / 2 + 2.0, WIDE / 2 - 2.0))
    assert shapes.span(planes, TALL / 2 - 1.0, 2.0) is None


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_the_line_stays_inside_the_shape_by_half_its_width(shape):
    params = params_for(shape)
    inset = params.margin + params.line_width / 2
    planes = shapes.half_planes(params.outline)
    line = modes.generate(params, gradient(), MACHINE)
    assert len(line.points) > 100
    for x, y in line.points:
        room = shapes.span(planes, y, inset - 1e-3)
        assert room is not None and room[0] <= x <= room[1]


def test_a_square_is_mapped_exactly_as_before_shapes_existed():
    params = replace(A.Params(), auto_tone=False, contrast=1.0)
    image = gradient()
    dark, grid = tsp._darkness(image, params)
    assert grid == image.width and dark == [1.0 - v / 255.0 for v in image.data]


def test_outside_the_shape_is_marked_so_relaxing_cannot_pull_points_there():
    params = params_for("circle")
    dark, grid = tsp._darkness(gradient(), params)
    assert dark[0] == stipple.OUTSIDE and dark[grid * grid // 2 + grid // 2] != stipple.OUTSIDE
    assert stipple.estimate_points([stipple.OUTSIDE] * 16, 4, 10.0, 1.0) == 0


def test_the_picture_is_fitted_to_the_art_not_stretched():
    image = GrayImage(4, 2, bytes(range(8)))
    assert image.center_crop(1.0).data == bytes([1, 2, 5, 6])
    assert image.center_crop(2.0) is image
    wide = GrayImage(4, 4, bytes(range(16))).center_crop(2.0)
    assert (wide.width, wide.height) == (4, 2)


def test_a_wide_rectangle_keeps_the_picture_s_left_on_the_left():
    params = params_for("rectangle")
    points = modes.generate(params, gradient(), MACHINE).points  # dark on the left of the gradient
    assert sum(1 for x, _ in points if x < 0) > 2 * sum(1 for x, _ in points if x > 0)


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_the_base_mesh_is_the_outline(shape):
    rim = rim_of(shape)
    data = placeholder.base_stl(rim, 1.0)
    count = struct.unpack_from("<I", data, 80)[0]
    assert count == 4 * len(rim)
    xs = [struct.unpack_from("<f", data, 84 + 50 * i + 12 + 12 * v)[0] for i in range(count) for v in range(3)]
    assert max(xs) - min(xs) == pytest.approx(shapes.extents(rim)[0], abs=1e-3)


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_each_part_of_the_two_filament_base_is_closed(shape):
    """Curved outlines came out empty in a real slice until the triangles shared their vertices."""
    data = placeholder.two_filament_3mf(rim_of(shape), 0.8, 1.0, 1, 2, (128.0, 128.0), "2.5.0")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        model = archive.read(f"3D/Objects/{placeholder.BASE_NAME}.model").decode()
    meshes = re.findall(r"<mesh>(.*?)</mesh>", model)
    assert len(meshes) == 2
    for body in meshes:
        vertices = re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"/>', body)
        triangles = [tuple(map(int, t)) for t in re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"/>', body)]
        assert len(set(vertices)) == len(vertices)
        edges = Counter(edge for a, b, c in triangles for edge in ((a, b), (b, c), (c, a)))
        assert all(count == 1 and edges[(end, start)] == 1 for (start, end), count in edges.items())


def top_layer(rim, shrink=0.4, diagonal_shrink=1.0):
    width, height = shapes.extents(rim)
    return splice.TopLayer(
        z=1.0, height=0.2, region_start=0, region_end=1, center=(128.0, 128.0),
        size=(width - shrink, height - shrink), diagonal=shapes.width_at_45(rim) - diagonal_shrink,
        upper=(), relative_e=True, tool=0, debt_start=0.0, e_end=0.0,
    )


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_the_splice_check_accepts_the_shape_it_was_given(shape):
    splice.check_base(top_layer(rim_of(shape)), rim_of(shape))


@pytest.mark.parametrize("wrong, right", [("circle", "square"), ("oval", "rectangle"), ("rectangle", "rounded_rectangle")])
def test_the_splice_check_tells_shapes_of_the_same_size_apart(wrong, right):
    with pytest.raises(splice.NotPlaceholder):
        splice.check_base(top_layer(rim_of(wrong)), rim_of(right))


def test_a_rectangle_turned_on_the_plate_is_refused():
    rim = rim_of("rectangle")
    turned = top_layer(rim)
    with pytest.raises(splice.NotPlaceholder):
        splice.check_base(replace(turned, size=turned.size[::-1]), rim)


def test_the_bed_check_uses_each_side():
    top = replace(top_layer(rim_of("rectangle")), center=(46.0, 128.0))
    splice.check_bed(top, (WIDE, TALL), MACHINE)
    with pytest.raises(ValueError):
        splice.check_bed(replace(top, center=(44.0, 128.0)), (WIDE, TALL), MACHINE)


def test_the_preview_centers_the_shape_in_its_square():
    params = params_for("rectangle")
    built = A.build(params, modes.generate(params, gradient(), MACHINE), MACHINE, 0.2)
    size = 90
    coverage = preview.render(built, size)
    empty_rows = (size - round(size * TALL / WIDE)) // 2
    assert not any(coverage[: (empty_rows - 1) * size]) and any(coverage[empty_rows * size + size:])


def test_the_canvas_outline_is_in_the_square_canvas():
    outline = shapes.canvas_outline(rim_of("rectangle"))
    ys = [y for _, y in outline]
    assert min(x for x, _ in outline) == pytest.approx(0.0)
    assert min(ys) == pytest.approx((1 - TALL / WIDE) / 2, abs=1e-4) and max(ys) == pytest.approx(1 - (1 - TALL / WIDE) / 2, abs=1e-4)


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_choices_describe_each_shape_for_the_page(shape):
    choice = next(c for c in shapes.choices() if c["id"] == shape)
    assert choice["label"] and choice["sides"] == shapes.SHAPES[shape].sides
    assert (choice["aspect"] is None) == (shapes.SHAPES[shape].sides == 2)
    assert all(0.0 <= value <= 1.0 for point in choice["outline"] for value in point)


def test_a_job_from_before_shapes_is_a_square_of_its_size():
    params = A.Params.from_dict({"size": 80.0})
    assert (params.shape, params.width, params.height) == ("square", 80.0, 80.0)


def test_a_saved_job_from_before_shapes_still_replaces_its_square():
    line = modes.generate(A.Params(width=60.0, height=60.0), gradient(), MACHINE)
    job = pipeline.job_to_dict(A.Params(width=60.0, height=60.0), line)
    for key in ("shape", "width", "height"):
        del job["params"][key]
    job["params"]["size"] = 60.0
    assert pipeline.process(BAMBU.read_text(encoding="utf-8"), job, {}.get).changed


def test_the_job_carries_the_shape():
    params = params_for("oval")
    saved = pipeline.job_to_dict(params, modes.generate(params, gradient(), MACHINE))
    loaded, _ = pipeline.job_from_dict(saved)
    assert (saved["params"]["shape"], loaded.shape, loaded.width, loaded.height) == ("oval", "oval", WIDE, TALL)


def test_the_shape_is_part_of_the_route_key():
    image = gradient()
    keys = {A.route_key(params, image) for params in (params_for("oval"), params_for("rectangle"), params_for("rectangle", WIDE, 80.0))}
    assert len(keys) == 3


def test_validation_refuses_unknown_shapes_and_short_sides():
    with pytest.raises(A.ArtError, match="shape"):
        params_for("star").validate(MACHINE)
    with pytest.raises(A.ArtError, match="at least"):
        params_for("rectangle", 150.0, 40.0).validate(MACHINE)
