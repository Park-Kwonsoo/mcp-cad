from mcp_cadquery_server.services import ai_models
from mcp_cadquery_server.services.model_store import load_latest_code, save_model
from mcp_cadquery_server.config import ServerConfig
from mcp_cadquery_server.context import AppContext
from mcp_cadquery_server.schemas.ai_models import GenerateModelArgs, ListModelsArgs, ModifyModelArgs
from mcp_cadquery_server.services.worker_pool import CadQueryWorkerPool


GENERATED_CODE = "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)\nshow_object(result)"
MODIFIED_CODE = "import cadquery as cq\nresult = cq.Workplane('XY').box(2, 2, 1)\nshow_object(result)"


def _execution_result(result_id):
    return {
        "success": True,
        "results": [
            {
                "result_id": result_id,
                "success": True,
                "shapes_count": 1,
                "error": None,
            }
        ],
    }


def _app_context(tmp_path, models_dir):
    return AppContext(
        config=ServerConfig(
            models_dir=models_dir,
            ai_workspace_dir=str(tmp_path / "workspace"),
            anthropic_model="test-model",
        ),
        shape_results={},
        worker_pool=CadQueryWorkerPool(),
    )


def test_generate_model_saves_model_metadata(monkeypatch, tmp_path):
    models_dir = str(tmp_path / "models")
    app_context = _app_context(tmp_path, models_dir)
    monkeypatch.setattr(ai_models, "generate_cadquery_code", lambda description, image_path=None, model=None: GENERATED_CODE)
    monkeypatch.setattr(
        ai_models,
        "handle_execute_cadquery_script",
        lambda app_context, args, request_id: _execution_result(f"{request_id}_0"),
    )
    monkeypatch.setattr(
        ai_models,
        "handle_export_shape",
        lambda app_context, args, request_id: {"success": True, "filename": str(tmp_path / "model_001.stl")},
    )

    result = ai_models.handle_generate_model(
        app_context,
        GenerateModelArgs(description="small box", model_id="model_001"),
        request_id="generate",
    )

    assert result["success"] is True
    assert result["model_id"] == "model_001"
    assert result["version"] == 1
    assert load_latest_code(models_dir, "model_001") == GENERATED_CODE


def test_modify_model_appends_version(monkeypatch, tmp_path):
    models_dir = str(tmp_path / "models")
    save_model(models_dir, "model_001", "small box", GENERATED_CODE, "/tmp/v1.stl")
    app_context = _app_context(tmp_path, models_dir)
    monkeypatch.setattr(ai_models, "modify_cadquery_code", lambda code, instruction, model=None: MODIFIED_CODE)
    monkeypatch.setattr(
        ai_models,
        "handle_execute_cadquery_script",
        lambda app_context, args, request_id: _execution_result(f"{request_id}_0"),
    )
    monkeypatch.setattr(
        ai_models,
        "handle_export_shape",
        lambda app_context, args, request_id: {"success": True, "filename": str(tmp_path / "model_001.stl")},
    )

    result = ai_models.handle_modify_model(
        app_context,
        ModifyModelArgs(model_id="model_001", instruction="make it wider"),
        request_id="modify",
    )

    assert result["success"] is True
    assert result["version"] == 2
    assert load_latest_code(models_dir, "model_001") == MODIFIED_CODE


def test_modify_model_missing_model_returns_error(monkeypatch, tmp_path):
    app_context = _app_context(tmp_path, str(tmp_path / "models"))

    result = ai_models.handle_modify_model(
        app_context,
        ModifyModelArgs(model_id="missing", instruction="make it wider"),
        request_id="modify",
    )

    assert result["success"] is False
    assert "not found" in result["message"]


def test_list_models_returns_store_contents(monkeypatch, tmp_path):
    models_dir = str(tmp_path / "models")
    save_model(models_dir, "model_001", "small box", GENERATED_CODE, "/tmp/v1.stl")
    app_context = _app_context(tmp_path, models_dir)

    result = ai_models.handle_list_models(app_context, ListModelsArgs())

    assert result["success"] is True
    assert result["count"] == 1
    assert result["models"][0]["model_id"] == "model_001"
