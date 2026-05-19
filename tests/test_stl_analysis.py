import pytest

from mcp_cadquery_server.domain.stl_analysis import move_stl_hole_centers, solidify_stl_mesh
from mcp_cadquery_server.domain.stl_io import read_stl_triangles


CUBE_STL = """solid cube
  facet normal 0 0 -1
    outer loop
      vertex 0 0 0
      vertex 1 1 0
      vertex 1 0 0
    endloop
  endfacet
  facet normal 0 0 -1
    outer loop
      vertex 0 0 0
      vertex 0 1 0
      vertex 1 1 0
    endloop
  endfacet
  facet normal 0 0 1
    outer loop
      vertex 0 0 1
      vertex 1 0 1
      vertex 1 1 1
    endloop
  endfacet
  facet normal 0 0 1
    outer loop
      vertex 0 0 1
      vertex 1 1 1
      vertex 0 1 1
    endloop
  endfacet
  facet normal 0 -1 0
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 1 0 1
    endloop
  endfacet
  facet normal 0 -1 0
    outer loop
      vertex 0 0 0
      vertex 1 0 1
      vertex 0 0 1
    endloop
  endfacet
  facet normal 0 1 0
    outer loop
      vertex 0 1 0
      vertex 1 1 1
      vertex 1 1 0
    endloop
  endfacet
  facet normal 0 1 0
    outer loop
      vertex 0 1 0
      vertex 0 1 1
      vertex 1 1 1
    endloop
  endfacet
  facet normal -1 0 0
    outer loop
      vertex 0 0 0
      vertex 0 0 1
      vertex 0 1 1
    endloop
  endfacet
  facet normal -1 0 0
    outer loop
      vertex 0 0 0
      vertex 0 1 1
      vertex 0 1 0
    endloop
  endfacet
  facet normal 1 0 0
    outer loop
      vertex 1 0 0
      vertex 1 1 1
      vertex 1 0 1
    endloop
  endfacet
  facet normal 1 0 0
    outer loop
      vertex 1 0 0
      vertex 1 1 0
      vertex 1 1 1
    endloop
  endfacet
endsolid cube
"""


def test_solidify_stl_mesh_exports_step(tmp_path):
    source_path = tmp_path / "cube.stl"
    output_path = tmp_path / "cube.step"
    source_path.write_text(CUBE_STL)

    result = solidify_stl_mesh(
        file_path=str(source_path),
        output_path=str(output_path),
        output_format="step",
        require_watertight=True,
    )

    assert result["success"] is True
    assert result["output_file"] == str(output_path)
    assert result["output_format"] == "step"
    assert result["conversion"]["triangle_count"] == 12
    assert result["conversion"]["component_count"] == 1
    assert output_path.exists()
    assert output_path.stat().st_size > 0


HOLE_EDGE_STL = """solid hole_edge
  facet normal 0 0 0
    outer loop
      vertex 1 0 0
      vertex 1 0 1
      vertex 2 0 0
    endloop
  endfacet
  facet normal 0 0 0
    outer loop
      vertex 0 1 0
      vertex 0 1 1
      vertex 0 2 0
    endloop
  endfacet
endsolid hole_edge
"""


def test_move_stl_hole_centers_moves_only_selected_hole_vertices(tmp_path):
    source_path = tmp_path / "source.stl"
    output_path = tmp_path / "moved.stl"
    source_path.write_text(HOLE_EDGE_STL)

    result = move_stl_hole_centers(
        file_path=str(source_path),
        output_path=str(output_path),
        holes=[
            {
                "current_center": {"x": 0, "y": 0, "z": 0},
                "new_center": {"x": 5, "y": 10, "z": 0},
                "radius": 1,
                "axis": "z",
                "radial_tolerance": 0.0001,
            }
        ],
    )

    triangles, _ = read_stl_triangles(str(output_path))
    vertices = {vertex for triangle in triangles for vertex in triangle}

    assert result["success"] is True
    assert result["holes"][0]["selected_vertex_occurrence_count"] == 4
    assert result["holes"][0]["selected_unique_vertex_count"] == 4
    assert (6.0, 10.0, 0.0) in vertices
    assert (6.0, 10.0, 1.0) in vertices
    assert (5.0, 11.0, 0.0) in vertices
    assert (5.0, 11.0, 1.0) in vertices
    assert (2.0, 0.0, 0.0) in vertices
    assert (0.0, 2.0, 0.0) in vertices


def test_move_stl_hole_centers_rejects_empty_selection_by_default(tmp_path):
    source_path = tmp_path / "source.stl"
    output_path = tmp_path / "moved.stl"
    source_path.write_text(HOLE_EDGE_STL)

    with pytest.raises(ValueError, match="selected no STL vertices"):
        move_stl_hole_centers(
            file_path=str(source_path),
            output_path=str(output_path),
            holes=[
                {
                    "current_center": {"x": 99, "y": 99, "z": 0},
                    "new_center": {"x": 100, "y": 100, "z": 0},
                    "radius": 1,
                    "axis": "z",
                }
            ],
        )

    assert not output_path.exists()
