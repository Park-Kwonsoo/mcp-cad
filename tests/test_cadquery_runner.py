from __future__ import annotations

import sys
from pathlib import Path

from mcp_cadquery_server.services import cadquery_runner


def _clear_cadquery_modules(monkeypatch):
    for module_name in list(sys.modules):
        if module_name == "cadquery" or module_name.startswith("cadquery."):
            monkeypatch.delitem(sys.modules, module_name, raising=False)


def _write_fake_cadquery_package(fake_site: Path) -> None:
    fake_cadquery = fake_site / "cadquery"
    fake_cadquery.mkdir(parents=True)
    (fake_cadquery / "__init__.py").write_text(
        """
from pathlib import Path

class Assembly:
    def toCompound(self):
        return self

class _Exporters:
    def export(self, shape, path, exportType=None):
        Path(path).write_text(f"{exportType}:{shape}", encoding="utf-8")

exporters = _Exporters()
""".lstrip(),
        encoding="utf-8",
    )
    (fake_cadquery / "cqgi.py").write_text(
        """
from types import SimpleNamespace

class _Model:
    def build(self):
        return SimpleNamespace(
            success=True,
            exception=None,
            results=[SimpleNamespace(shape="fake-shape", options={"name": "shape_0"})],
        )

def parse(script_content):
    return _Model()
""".lstrip(),
        encoding="utf-8",
    )


def test_execute_job_imports_external_cadquery_when_services_dir_is_on_sys_path(monkeypatch, tmp_path):
    fake_site = tmp_path / "fake_site"
    _write_fake_cadquery_package(fake_site)

    _clear_cadquery_modules(monkeypatch)
    services_dir = Path(cadquery_runner.__file__).resolve().parent
    monkeypatch.syspath_prepend(str(fake_site))
    monkeypatch.syspath_prepend(str(services_dir))

    result = cadquery_runner.execute_cadquery_job(
        {
            "workspace_path": str(tmp_path),
            "script_content": "import cadquery as cq\nshow_object(object())",
            "parameters": {},
            "result_id": "shadow-repro",
            "results_dir": str(tmp_path / "results"),
        }
    )

    assert result["success"] is True
    assert result["exception_str"] is None
    assert result["results"][0]["intermediate_path"].endswith("shape_0.brep")
    assert str(fake_site) in sys.modules["cadquery"].__file__


def test_execute_job_imports_external_cadquery_when_workspace_contains_cadquery_module(monkeypatch, tmp_path):
    fake_site = tmp_path / "fake_site"
    _write_fake_cadquery_package(fake_site)

    (tmp_path / "cadquery.py").write_text(
        'raise RuntimeError("workspace cadquery shadow imported")\n',
        encoding="utf-8",
    )

    _clear_cadquery_modules(monkeypatch)
    monkeypatch.syspath_prepend(str(fake_site))

    result = cadquery_runner.execute_cadquery_job(
        {
            "workspace_path": str(tmp_path),
            "script_content": "import cadquery as cq\nshow_object(object())",
            "parameters": {},
            "result_id": "workspace-shadow-repro",
            "results_dir": str(tmp_path / "results"),
        }
    )

    assert result["success"] is True
    assert result["exception_str"] is None
    assert result["results"][0]["intermediate_path"].endswith("shape_0.brep")
    assert str(fake_site) in sys.modules["cadquery"].__file__
