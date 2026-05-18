import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List


MODELS_DIR = os.path.expanduser("~/.mcp/mcp-cad/models")
_MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_model_id(model_id: str) -> str:
    if not _MODEL_ID_PATTERN.fullmatch(model_id):
        raise ValueError(f"Invalid model_id: {model_id!r}")
    return model_id


def _model_dir(models_dir: str, model_id: str) -> str:
    validate_model_id(model_id)
    return os.path.join(models_dir, model_id)


def _meta_path(models_dir: str, model_id: str) -> str:
    return os.path.join(_model_dir(models_dir, model_id), "meta.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_meta(models_dir: str, model_id: str) -> Dict[str, Any]:
    path = _meta_path(models_dir, model_id)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model '{model_id}' not found in {models_dir}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_meta(models_dir: str, model_id: str, meta: Dict[str, Any]) -> None:
    path = _meta_path(models_dir, model_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def get_model_next_version_path(models_dir: str, model_id: str, version: int) -> str:
    return os.path.join(_model_dir(models_dir, model_id), f"v{version}.py")


def save_model(
    models_dir: str,
    model_id: str,
    description: str,
    code: str,
    stl_path: str,
) -> Dict[str, Any]:
    model_dir = _model_dir(models_dir, model_id)
    os.makedirs(model_dir, exist_ok=True)

    try:
        meta = _load_meta(models_dir, model_id)
    except FileNotFoundError:
        meta = {"model_id": model_id, "versions": []}

    now = _utc_now()
    version = len(meta["versions"]) + 1
    code_path = get_model_next_version_path(models_dir, model_id, version)

    with open(code_path, "w", encoding="utf-8") as f:
        f.write(code)

    meta["description"] = description
    meta["latest_stl"] = stl_path
    meta["updated_at"] = now
    meta.setdefault("created_at", now)
    meta["versions"].append(
        {
            "version": version,
            "code_path": code_path,
            "stl_path": stl_path,
            "created_at": now,
        }
    )

    _save_meta(models_dir, model_id, meta)
    return meta


def load_model(models_dir: str, model_id: str) -> Dict[str, Any]:
    return _load_meta(models_dir, model_id)


def load_latest_code(models_dir: str, model_id: str) -> str:
    meta = _load_meta(models_dir, model_id)
    latest = meta["versions"][-1]
    with open(latest["code_path"], encoding="utf-8") as f:
        return f.read()


def list_models(models_dir: str) -> List[Dict[str, Any]]:
    if not os.path.exists(models_dir):
        return []

    result = []
    for model_id in os.listdir(models_dir):
        try:
            meta_path = _meta_path(models_dir, model_id)
        except ValueError:
            continue
        if not os.path.exists(meta_path):
            continue
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        result.append(
            {
                "model_id": meta["model_id"],
                "description": meta.get("description", ""),
                "latest_stl": meta.get("latest_stl", ""),
                "version_count": len(meta.get("versions", [])),
                "updated_at": meta.get("updated_at", ""),
            }
        )

    return sorted(result, key=lambda item: item["updated_at"], reverse=True)
