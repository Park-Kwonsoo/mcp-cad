import json
import sys
import textwrap

from src.mcp_cadquery_server.worker_pool import CadQueryWorkerPool


def test_worker_pool_reuses_persistent_worker(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    worker_script = tmp_path / "fake_worker.py"
    worker_script.write_text(
        textwrap.dedent(
            """
            import json
            import os
            import sys

            for raw in sys.stdin:
                job = json.loads(raw)
                if job.get("type") == "shutdown":
                    print(json.dumps({"job_id": job.get("job_id"), "result": {"success": True, "results": [], "exception_str": None}}), flush=True)
                    break

                result = {
                    "success": True,
                    "results": [{"name": job["result_id"], "type": "Fake", "intermediate_path": None}],
                    "exception_str": None,
                    "pid": os.getpid(),
                    "parameters": job.get("parameters", {}),
                }
                print(json.dumps({"job_id": job.get("job_id"), "result": result}), flush=True)
            """
        ),
        encoding="utf-8",
    )

    pool = CadQueryWorkerPool(max_workers_per_workspace=1, worker_path=str(worker_script))
    try:
        first = pool.execute(
            str(workspace),
            sys.executable,
            {
                "workspace_path": str(workspace),
                "script_content": "show_object(None)",
                "parameters": {"length": 1},
                "result_id": "one",
            },
        )
        second = pool.execute(
            str(workspace),
            sys.executable,
            {
                "workspace_path": str(workspace),
                "script_content": "show_object(None)",
                "parameters": {"length": 2},
                "result_id": "two",
            },
        )
    finally:
        pool.close()

    assert first["success"] is True
    assert second["success"] is True
    assert first["pid"] == second["pid"]
    assert first["parameters"] == {"length": 1}
    assert second["parameters"] == {"length": 2}
