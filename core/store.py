"""任务状态存储：每个任务一个 JSON 文件，无需数据库。"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

from .paths import jobs_dir

_LOCK = threading.RLock()


def new_id(prefix: str = "j") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _path(job_id: str):
    return jobs_dir() / f"{job_id}.json"


def create(files: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    """创建一个待执行任务。files: [{"name":..., "path":..., "kind":...}]"""
    job = {
        "id": new_id("j"),
        "status": "pending",
        "stage": "pending",
        "progress": 0,
        "message": "排队中…",
        "error": "",
        "files": files,
        "profile": profile,
        "result": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    with _LOCK:
        _path(job["id"]).write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return job


def get(job_id: str) -> dict[str, Any] | None:
    p = _path(job_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def update(job_id: str, **fields: Any) -> dict[str, Any] | None:
    with _LOCK:
        job = get(job_id)
        if job is None:
            return None
        job.update(fields)
        job["updated_at"] = _now()
        _path(job_id).write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return job


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with _LOCK:
        for p in jobs_dir().glob("j_*.json"):
            try:
                items.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
    items.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return items[:limit]


def delete(job_id: str) -> bool:
    p = _path(job_id)
    with _LOCK:
        if not p.exists():
            return False
        try:
            p.unlink()
        except OSError:
            return False
    return True
