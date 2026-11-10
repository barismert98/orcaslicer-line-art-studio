"""The base the user slices. Its top layers are replaced by the art."""
from __future__ import annotations

import io
import struct
import zipfile

BASE_NAME = "line_art_studio_base"  # the slicer writes this into the G-code as the object name


def _prism(rim: list, bottom: float, top: float) -> list:
    triangles = []
    for a, b in zip(rim, rim[1:] + rim[:1]):
        triangles.append(((0.0, 0.0, bottom), (*b, bottom), (*a, bottom)))
        triangles.append(((0.0, 0.0, top), (*a, top), (*b, top)))
        triangles.append(((*a, bottom), (*b, bottom), (*b, top)))
        triangles.append(((*a, bottom), (*b, top), (*a, top)))
    return triangles


def base_stl(rim: list, height: float) -> bytes:
    """Binary STL of a closed prism standing on z = 0, for a print in one filament."""
    triangles = _prism(rim, 0.0, height)
    out = bytearray(b"Line Art Studio placeholder".ljust(80, b"\0"))
    out += struct.pack("<I", len(triangles))
    for triangle in triangles:
        out += struct.pack("<3f", 0.0, 0.0, 0.0)
        for vertex in triangle:
            out += struct.pack("<3f", *vertex)
        out += b"\0\0"
    return bytes(out)


def _shared_vertices(triangles: list) -> tuple:
    """Vertices without repeats, and the triangles as indices into them.

    OrcaSlicer's 3MF route keeps a mesh as written, and its slicer joins triangles through
    shared vertices. Loose triangles shorter than 2 mm are lost when it closes the outlines.
    """
    index: dict = {}
    cells = [tuple(index.setdefault(vertex, len(index)) for vertex in triangle) for triangle in triangles]
    return list(index), cells


def _mesh_object(object_id: int, triangles: list) -> str:
    vertices, indexed = _shared_vertices(triangles)
    points = "".join(f'<vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in vertices)
    cells = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in indexed)
    return f'<object id="{object_id}" p:UUID="{_uuid(object_id)}" type="model"><mesh><vertices>{points}</vertices><triangles>{cells}</triangles></mesh></object>'


def _uuid(number: int) -> str:
    return f"{number:08x}-81cb-4c03-9d28-80fed5dfa1dc"


def two_filament_3mf(
    rim: list,
    base_height: float,
    total_height: float,
    base_filament: int,
    art_filament: int,
    position: tuple,
    app_version: str,
) -> bytes:
    """A 3MF of one object in two stacked parts, each assigned to its own filament (1-based).

    It holds no project settings, so OrcaSlicer takes only its geometry and part filaments
    and keeps the current presets. `app_version` must be the running version: an older
    tag makes OrcaSlicer show a message about old project files.
    """
    bottom, top = _prism(rim, 0.0, base_height), _prism(rim, base_height, total_height)
    namespaces = (
        'unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
        'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"'
    )
    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    objects_path = f"/3D/Objects/{BASE_NAME}.model"
    root = (
        f"{header}<model {namespaces}>"
        '<metadata name="Application">BambuStudio-02.08.01.55</metadata>'
        f'<metadata name="OrcaSlicer">{app_version}</metadata>'
        '<metadata name="BambuStudio:3mfVersion">1</metadata>'
        f'<resources><object id="3" p:UUID="{_uuid(3)}" type="model"><components>'
        f'<component p:path="{objects_path}" objectid="1" p:UUID="{_uuid(11)}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
        f'<component p:path="{objects_path}" objectid="2" p:UUID="{_uuid(12)}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
        f'</components></object></resources><build p:UUID="{_uuid(20)}">'
        f'<item objectid="3" p:UUID="{_uuid(21)}" transform="1 0 0 0 1 0 0 0 1 {position[0]:.3f} {position[1]:.3f} 0" printable="1"/>'
        "</build></model>\n"
    )
    meshes = (
        f"{header}<model {namespaces}>"
        '<metadata name="BambuStudio:3mfVersion">1</metadata>'
        f"<resources>{_mesh_object(1, bottom)}{_mesh_object(2, top)}</resources><build/></model>\n"
    )
    part = '<part id="{id}" subtype="normal_part"><metadata key="name" value="{name}"/><metadata key="extruder" value="{filament}"/></part>'
    settings = (
        f'{header}<config><object id="3"><metadata key="name" value="{BASE_NAME}"/>'
        f'<metadata key="extruder" value="{base_filament}"/>'
        + part.format(id=1, name="Base", filament=base_filament)
        + part.format(id=2, name="Art", filament=art_filament)
        + "</object></config>\n"
    )
    files = {
        "[Content_Types].xml": (
            f'{header}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>\n'
        ),
        "_rels/.rels": (
            f'{header}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>\n'
        ),
        "3D/3dmodel.model": root,
        "3D/_rels/3dmodel.model.rels": (
            f'{header}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Target="{objects_path}" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>\n'
        ),
        objects_path[1:]: meshes,
        "Metadata/model_settings.config": settings,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
