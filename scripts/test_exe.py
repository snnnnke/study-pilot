"""端到端验证打包后的 exe：上传 → 建任务 → 轮询 → 下载 PDF。

需要 exe 以 Mock 模式运行在 127.0.0.1:8766，例如：
    $env:STUDY_PILOT_MOCK="1"; StudyPilot.exe --no-browser --port 8766
用法：
    .venv\\Scripts\\python.exe scripts\\test_exe.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("STUDY_PILOT_BASE", "http://127.0.0.1:8766")


def upload(pdf: Path) -> dict:
    boundary = uuid.uuid4().hex
    body = bytearray()
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="files"; filename="test.pdf"\r\n'
    body += b"Content-Type: application/pdf\r\n\r\n"
    body += pdf.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        BASE + "/api/upload",
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def post_json(path: str, obj: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(obj).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def get_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    pdf = sorted((ROOT / "docs").glob("*.pdf"))[0]
    print(f"测试文件：{pdf.name}")

    up = upload(pdf)
    print(f"上传成功：{len(up['files'])} 个文件")
    job = post_json("/api/jobs", {
        "file_ids": [f["id"] for f in up["files"]],
        "profile": "standard",
    })
    job_id = job["job_id"]
    print(f"任务：{job_id}")

    job_data = {}
    for _ in range(240):
        job_data = get_json(f"/api/jobs/{job_id}")
        if job_data["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.25)

    print(f"状态：{job_data.get('status')} 进度：{job_data.get('progress')} 错误：{job_data.get('error')}")
    if job_data.get("status") != "done":
        return 1

    out_dir = ROOT / ".data" / "exe-test"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "exe-report.pdf"
    with urllib.request.urlopen(BASE + f"/api/jobs/{job_id}/download", timeout=60) as resp:
        out.write_bytes(resp.read())

    data = out.read_bytes()
    print(f"下载：{out}（{len(data) / 1024:.0f} KB，页数 {job_data['result']['pages']}）")
    if data[:4] != b"%PDF":
        print("PDF 文件头不正确")
        return 1
    print("打包 exe 端到端验证通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
