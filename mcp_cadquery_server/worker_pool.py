"""Persistent CadQuery worker process pool."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .state import _MODULE_DIR, log


DEFAULT_JOB_TIMEOUT_SECONDS = float(os.environ.get("MCP_CADQUERY_WORKER_TIMEOUT", "300"))
DEFAULT_WORKERS_PER_WORKSPACE = max(1, int(os.environ.get("MCP_CADQUERY_WORKERS_PER_WORKSPACE", "1")))


class WorkerProcessError(RuntimeError):
    """Raised when the persistent worker infrastructure fails."""


class CadQueryWorkerProcess:
    def __init__(self, workspace_path: str, python_exe: str, worker_path: str, worker_index: int):
        self.workspace_path = workspace_path
        self.python_exe = python_exe
        self.worker_path = worker_path
        self.worker_index = worker_index
        self.process: Optional[subprocess.Popen[str]] = None
        self._responses: "queue.Queue[str]" = queue.Queue()
        self._io_lock = threading.Lock()
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None

    @property
    def label(self) -> str:
        return f"{os.path.basename(self.workspace_path)}#{self.worker_index}"

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> None:
        if self.is_alive():
            return

        self.process = subprocess.Popen(
            [self.python_exe, self.worker_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=self.workspace_path,
            env=os.environ.copy(),
            bufsize=1,
        )
        self._responses = queue.Queue()
        self._stdout_thread = threading.Thread(target=self._read_stdout, name=f"cq-worker-stdout-{self.label}", daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, name=f"cq-worker-stderr-{self.label}", daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()
        log.info("Started persistent CadQuery worker %s with PID %s", self.label, self.process.pid)

    def execute(self, payload: Dict[str, Any], timeout: float = DEFAULT_JOB_TIMEOUT_SECONDS) -> Dict[str, Any]:
        with self._io_lock:
            self.start()
            if not self.process or not self.process.stdin:
                raise WorkerProcessError(f"CadQuery worker {self.label} is not writable.")

            job_id = payload.get("job_id") or str(uuid.uuid4())
            payload = dict(payload)
            payload["job_id"] = job_id
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()

            try:
                raw_response = self._responses.get(timeout=timeout)
            except queue.Empty as exc:
                self.stop(kill=True)
                raise TimeoutError(f"CadQuery worker {self.label} timed out after {timeout} seconds.") from exc

            if raw_response == "":
                exit_code = self.process.poll() if self.process else None
                raise WorkerProcessError(f"CadQuery worker {self.label} exited before responding. Exit code: {exit_code}")

            try:
                response = json.loads(raw_response)
            except json.JSONDecodeError as exc:
                raise WorkerProcessError(f"CadQuery worker {self.label} returned invalid JSON: {raw_response[:200]}") from exc

            if response.get("job_id") != job_id:
                raise WorkerProcessError(
                    f"CadQuery worker {self.label} returned response for unexpected job ID {response.get('job_id')!r}."
                )

            result = response.get("result")
            if not isinstance(result, dict):
                raise WorkerProcessError(f"CadQuery worker {self.label} returned a malformed result.")
            return result

    def stop(self, kill: bool = False) -> None:
        process = self.process
        if not process:
            return
        try:
            if process.poll() is None and process.stdin and not kill:
                shutdown_id = str(uuid.uuid4())
                process.stdin.write(json.dumps({"type": "shutdown", "job_id": shutdown_id}) + "\n")
                process.stdin.flush()
                process.terminate()
            elif process.poll() is None:
                process.kill()
        finally:
            self.process = None

    def _read_stdout(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            self._responses.put(line.rstrip("\n"))
        self._responses.put("")

    def _read_stderr(self) -> None:
        assert self.process and self.process.stderr
        for line in self.process.stderr:
            text = line.rstrip()
            if text:
                log.debug("[CadQueryWorker %s] %s", self.label, text)


@dataclass
class _WorkspaceWorkerGroup:
    workspace_path: str
    python_exe: str
    worker_path: str
    max_workers: int
    workers: List[CadQueryWorkerProcess] = field(default_factory=list)
    idle: List[CadQueryWorkerProcess] = field(default_factory=list)
    condition: threading.Condition = field(default_factory=lambda: threading.Condition(threading.Lock()))

    def acquire(self) -> CadQueryWorkerProcess:
        with self.condition:
            while True:
                self.workers = [worker for worker in self.workers if worker.is_alive() or worker in self.idle]
                self.idle = [worker for worker in self.idle if worker in self.workers]

                if self.idle:
                    return self.idle.pop()

                if len(self.workers) < self.max_workers:
                    worker = CadQueryWorkerProcess(
                        self.workspace_path,
                        self.python_exe,
                        self.worker_path,
                        len(self.workers),
                    )
                    self.workers.append(worker)
                    return worker

                self.condition.wait()

    def release(self, worker: CadQueryWorkerProcess) -> None:
        with self.condition:
            if worker.is_alive() and worker not in self.idle:
                self.idle.append(worker)
            self.condition.notify()

    def close(self) -> None:
        with self.condition:
            workers = list(self.workers)
            self.workers.clear()
            self.idle.clear()
            self.condition.notify_all()
        for worker in workers:
            worker.stop()


class CadQueryWorkerPool:
    def __init__(
        self,
        max_workers_per_workspace: int = DEFAULT_WORKERS_PER_WORKSPACE,
        worker_path: Optional[str] = None,
    ):
        self.max_workers_per_workspace = max(1, max_workers_per_workspace)
        self.worker_path = worker_path or os.path.join(_MODULE_DIR, "cadquery_worker.py")
        self._groups: Dict[Tuple[str, str], _WorkspaceWorkerGroup] = {}
        self._lock = threading.Lock()

    def execute(self, workspace_path: str, python_exe: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not os.path.exists(self.worker_path):
            raise WorkerProcessError(f"CadQuery worker not found at {self.worker_path}")

        group = self._get_group(workspace_path, python_exe)
        worker = group.acquire()
        try:
            return worker.execute(payload)
        finally:
            group.release(worker)

    def close(self) -> None:
        with self._lock:
            groups = list(self._groups.values())
            self._groups.clear()
        for group in groups:
            group.close()

    def close_workspace(self, workspace_path: str) -> None:
        with self._lock:
            keys = [key for key in self._groups if key[0] == workspace_path]
            groups = [self._groups.pop(key) for key in keys]
        for group in groups:
            group.close()

    def _get_group(self, workspace_path: str, python_exe: str) -> _WorkspaceWorkerGroup:
        key = (workspace_path, python_exe)
        with self._lock:
            group = self._groups.get(key)
            if group is None:
                group = _WorkspaceWorkerGroup(
                    workspace_path=workspace_path,
                    python_exe=python_exe,
                    worker_path=self.worker_path,
                    max_workers=self.max_workers_per_workspace,
                )
                self._groups[key] = group
            return group


cadquery_worker_pool = CadQueryWorkerPool()
