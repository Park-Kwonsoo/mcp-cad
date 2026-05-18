import os

import pytest

from mcp_cadquery_server.model_store import (
    get_model_next_version_path,
    list_models,
    load_latest_code,
    load_model,
    save_model,
)


@pytest.fixture
def tmp_models_dir(tmp_path):
    return str(tmp_path / "models")


def test_save_and_load_model(tmp_models_dir):
    model_id = "test_001"
    save_model(
        models_dir=tmp_models_dir,
        model_id=model_id,
        description="test box",
        code='import cadquery as cq\nresult = cq.Workplane("XY").box(10, 10, 5)\nshow_object(result)',
        stl_path="/tmp/test.stl",
    )

    meta = load_model(tmp_models_dir, model_id)

    assert meta["description"] == "test box"
    assert meta["latest_stl"] == "/tmp/test.stl"
    assert len(meta["versions"]) == 1
    assert meta["versions"][0]["version"] == 1


def test_save_multiple_versions(tmp_models_dir):
    model_id = "test_002"
    save_model(tmp_models_dir, model_id, "box", "code_v1", "/tmp/v1.stl")
    save_model(tmp_models_dir, model_id, "modified box", "code_v2", "/tmp/v2.stl")

    meta = load_model(tmp_models_dir, model_id)

    assert len(meta["versions"]) == 2
    assert meta["versions"][-1]["version"] == 2
    assert meta["latest_stl"] == "/tmp/v2.stl"


def test_load_model_latest_code(tmp_models_dir):
    model_id = "test_003"
    save_model(tmp_models_dir, model_id, "box", "code_v1", "/tmp/v1.stl")
    save_model(tmp_models_dir, model_id, "modified box", "code_v2", "/tmp/v2.stl")

    meta = load_model(tmp_models_dir, model_id)
    version_dir = os.path.join(tmp_models_dir, model_id)
    latest_code_path = os.path.join(version_dir, f"v{len(meta['versions'])}.py")

    with open(latest_code_path) as f:
        assert f.read() == "code_v2"
    assert load_latest_code(tmp_models_dir, model_id) == "code_v2"


def test_list_models_empty(tmp_models_dir):
    os.makedirs(tmp_models_dir, exist_ok=True)

    result = list_models(tmp_models_dir)

    assert result == []


def test_list_models_returns_all(tmp_models_dir):
    save_model(tmp_models_dir, "m1", "model 1", "code1", "/tmp/1.stl")
    save_model(tmp_models_dir, "m2", "model 2", "code2", "/tmp/2.stl")

    result = list_models(tmp_models_dir)
    ids = [model["model_id"] for model in result]

    assert "m1" in ids
    assert "m2" in ids


def test_load_nonexistent_model_raises(tmp_models_dir):
    with pytest.raises(FileNotFoundError):
        load_model(tmp_models_dir, "nonexistent")


def test_rejects_path_traversal_model_id(tmp_models_dir):
    with pytest.raises(ValueError):
        save_model(tmp_models_dir, "../outside", "bad", "code", "/tmp/bad.stl")


def test_get_next_version_path(tmp_models_dir):
    path = get_model_next_version_path(tmp_models_dir, "test_004", version=1)

    assert path.endswith("v1.py")
