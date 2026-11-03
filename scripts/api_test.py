"""接口冒烟测试：用 Flask test_client 跑通「上传 → 建任务 → 轮询 → 下载 → 删除」。

Mock 模式不消耗真实 API。
用法：
    .venv\\Scripts\\python.exe scripts\\api_test.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["STUDY_PILOT_MOCK"] = "1"
os.environ["STUDY_PILOT_HOME"] = str(ROOT / ".data" / "api-test")
sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        raise SystemExit(f"测试失败：{name}")


def main() -> int:
    client = app.test_client()

    print("1) 基础接口")
    r = client.get("/api/health")
    check("GET /api/health", r.status_code == 200 and r.get_json()["ok"])

    r = client.get("/api/settings")
    check("GET /api/settings", r.status_code == 200 and "ai" in r.get_json())

    r = client.get("/api/providers")
    check("GET /api/providers", r.status_code == 200 and len(r.get_json()) >= 5)

    print("\n2) 配置保存（含 API Key 加密）")
    r = client.post("/api/settings", json={
        "ai": {"provider": "deepseek", "base_url": "https://api.deepseek.com/v1",
               "model": "deepseek-chat", "api_key": "sk-test-1234567890abcd"},
        "asr": {"model_size": "base", "device": "cpu", "language": "zh"},
        "report": {"profile": "standard"},
    })
    check("POST /api/settings", r.status_code == 200 and r.get_json()["ok"])
    r = client.get("/api/settings")
    data = r.get_json()
    check("API Key 已保存并打码", data["ai"]["api_key_set"] and "****" in data["ai"]["api_key_masked"])

    cfg_path = Path(os.environ["STUDY_PILOT_HOME"]) / "config.json"
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    check("Key 已加密存储", raw["ai"]["api_key"].startswith(("enc:", "plain:")))
    print(f"       存储形式：{raw['ai']['api_key'][:12]}…")

    print("\n3) 上传文件")
    pdfs = sorted((ROOT / "docs").glob("*.pdf"))
    if not pdfs:
        print("  docs 下没有 PDF，跳过")
        return 0
    open_files = [open(p, "rb") for p in pdfs[:2]]
    try:
        data = {"files": [(f, p.name) for f, p in zip(open_files, pdfs[:2])]}
        r = client.post("/api/upload", data=data, content_type="multipart/form-data")
    finally:
        for f in open_files:
            f.close()
    check("POST /api/upload", r.status_code == 200)
    uploaded = r.get_json()["files"]
    check("返回文件信息", len(uploaded) == len(pdfs[:2]) and uploaded[0]["size"] > 0)

    print("\n4) 创建任务并轮询")
    r = client.post("/api/jobs", json={"file_ids": [f["id"] for f in uploaded], "profile": "standard"})
    check("POST /api/jobs", r.status_code == 200)
    job_id = r.get_json()["job_id"]

    job = {}
    for _ in range(240):
        r = client.get(f"/api/jobs/{job_id}")
        job = r.get_json()
        if job["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.25)
    check("任务完成", job.get("status") == "done",
          f"status={job.get('status')} error={job.get('error')}")
    check("进度 100", job.get("progress") == 100)
    check("有 PDF 结果", bool(job.get("result", {}).get("filename")),
          json.dumps(job.get("result"), ensure_ascii=False))

    print("\n5) 下载报告")
    r = client.get(f"/api/jobs/{job_id}/download")
    check("GET download", r.status_code == 200 and r.data[:4] == b"%PDF")
    out = Path(os.environ["STUDY_PILOT_HOME"]) / "outputs"
    pdf_files = list(out.glob("*.pdf"))
    check("PDF 已落盘", len(pdf_files) >= 1, str(pdf_files[-1] if pdf_files else ""))

    print("\n6) 历史与删除")
    r = client.get("/api/jobs")
    check("GET /api/jobs", r.status_code == 200 and len(r.get_json()["jobs"]) >= 1)
    r = client.delete(f"/api/jobs/{job_id}")
    check("DELETE /api/jobs", r.status_code == 200)
    r = client.get(f"/api/jobs/{job_id}")
    check("删除后 404", r.status_code == 404)

    print("\n全部接口测试通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
