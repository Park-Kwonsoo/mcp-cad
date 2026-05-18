#!/usr/bin/env python3
"""Long-lived CadQuery worker process.

The worker reads one JSON job per line from stdin and writes one JSON response
per line to stdout. Logs are written to stderr so stdout stays machine-readable.
"""

import json
import logging
import sys
import traceback
from typing import Any, Dict

from runner_core import execute_cadquery_job


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - CadQueryWorker - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)


def _error_result(exc: BaseException) -> Dict[str, Any]:
    return {
        "success": False,
        "results": [],
        "exception_str": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }


def _write_response(response: Dict[str, Any]) -> None:
    print(json.dumps(response, ensure_ascii=False), flush=True)


def main() -> None:
    log.info("CadQuery worker started.")
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        job_id = None
        try:
            job = json.loads(line)
            job_id = job.get("job_id")
            if job.get("type") == "shutdown":
                _write_response({"job_id": job_id, "result": {"success": True, "results": [], "exception_str": None}})
                break

            result = execute_cadquery_job(job)
            _write_response({"job_id": job_id, "result": result})
        except Exception as exc:
            log.exception("Worker failed while processing a job.")
            _write_response({"job_id": job_id, "result": _error_result(exc)})

    log.info("CadQuery worker stopped.")


if __name__ == "__main__":
    main()
