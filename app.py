"""学伴 StudyPilot 启动入口。

启动本地 Flask 服务并自动打开浏览器；仅监听 127.0.0.1，不对外暴露。
用法：
    python app.py                 # 自动选择端口并打开浏览器
    python app.py --no-browser    # 不自动打开浏览器
    python app.py --port 9000     # 指定端口
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import socket
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from core import config, extractors, paths, store
from core.errors import PipelineError
from core.paths import outputs_dir, uploads_dir, web_dir
from core.pipeline import run_job

APP_VERSION = "1.0.0"

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 * 1024  # 单次上传上限 4GB
app.config["JSON_AS_ASCII"] = False

# 上传文件登记表：file_id -> {name, path, kind, size}
_UPLOADS: dict[str, dict[str, Any]] = {}
_UPLOADS_LOCK = threading.Lock()

# 任务取消信号：job_id -> Event
_CANCELS: dict[str, threading.Event] = {}
_CANCELS_LOCK = threading.Lock()

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="study-pilot")

SUPPORTED_EXTS = {
    *extractors.DOC_EXTENSIONS,
    *extractors.LEGACY_EXTENSIONS,
    *extractors.MEDIA_EXTENSIONS,
}


# ---------------------------------------------------------------- 工具

def _json_error(message: str, code: int = 400):
    return jsonify({"ok": False, "error": message}), code


def _save_upload(file) -> dict[str, Any]:
    from werkzeug.utils import secure_filename

    filename = file.filename or "未命名"
    # 只保留文件名部分，防路径穿越
    filename = os.path.basename(filename.replace("\\", "/")) or "未命名"
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise PipelineError(f"不支持的文件格式：{filename}")

    file_id = store.new_id("f")
    safe_stem = secure_filename(Path(filename).stem)[:40] or "file"
    dest = uploads_dir() / f"{file_id}_{safe_stem}{ext}"
    file.save(str(dest))
    size = dest.stat().st_size
    info = {
        "id": file_id,
        "name": filename,
        "path": str(dest),
        "kind": extractors.kind_for(filename),
        "size": size,
    }
    with _UPLOADS_LOCK:
        _UPLOADS[file_id] = info
    return info


def _resolve_upload(file_id: str) -> dict[str, Any] | None:
    with _UPLOADS_LOCK:
        info = _UPLOADS.get(file_id)
    if info and Path(info["path"]).exists():
        return info
    # 服务重启后内存表丢失，尝试按前缀恢复
    for p in uploads_dir().glob(f"{file_id}_*"):
        return {
            "id": file_id,
            "name": p.name[len(file_id) + 1:],
            "path": str(p),
            "kind": extractors.kind_for(p.name),
            "size": p.stat().st_size,
        }
    return None


# ---------------------------------------------------------------- 静态资源

@app.get("/")
def index():
    return send_from_directory(str(web_dir()), "index.html")


@app.get("/<path:filename>")
def static_files(filename: str):
    target = web_dir() / filename
    if not target.is_file():
        abort(404)
    return send_from_directory(str(web_dir()), filename)


# ---------------------------------------------------------------- API：健康 / 配置

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "version": APP_VERSION, "app": "学伴 StudyPilot"})


@app.get("/api/providers")
def providers():
    return jsonify(config.PROVIDERS)


@app.get("/api/settings")
def get_settings():
    cfg = config.load_config()
    return jsonify(config.public_settings(cfg))


@app.post("/api/settings")
def save_settings():
    body = request.get_json(silent=True) or {}
    cfg = config.load_config()

    ai = body.get("ai") or {}
    for key in ("provider", "base_url", "model", "temperature", "extra_headers"):
        if key in ai:
            cfg["ai"][key] = ai[key]
    if ai.get("api_key"):  # 空字符串表示不修改
        cfg["ai"]["api_key"] = config.encrypt_secret(str(ai["api_key"]))

    asr = body.get("asr") or {}
    for key in ("model_size", "model_path", "device", "language"):
        if key in asr:
            cfg["asr"][key] = asr[key]

    report_cfg = body.get("report") or {}
    for key in ("profile",):
        if key in report_cfg:
            cfg["report"][key] = report_cfg[key]

    server = body.get("server") or {}
    for key in ("port",):
        if key in server:
            cfg["server"][key] = server[key]

    saved = config.save_config(cfg)
    return jsonify({"ok": True, "settings": config.public_settings(saved)})


@app.post("/api/settings/test")
def test_settings():
    body = request.get_json(silent=True) or {}
    cfg = config.load_config()

    base_url = (body.get("base_url") or cfg["ai"].get("base_url") or "").strip()
    model = (body.get("model") or cfg["ai"].get("model") or "").strip()
    api_key = (body.get("api_key") or "").strip() or config.get_api_key(cfg)

    if not base_url:
        return jsonify({"ok": False, "error": "请先填写接口地址 base_url"}), 200
    if not model:
        return jsonify({"ok": False, "error": "请先填写模型名称"}), 200

    start = time.time()
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=base_url,
            api_key=api_key or "sk-no-key-required",
            timeout=25,
            max_retries=0,
        )
        try:
            client.models.list()
        except Exception:
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                timeout=25,
            )
        latency = int((time.time() - start) * 1000)
        return jsonify({"ok": True, "latency_ms": latency})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 200


# ---------------------------------------------------------------- API：上传

@app.post("/api/upload")
def upload():
    files = request.files.getlist("files")
    if not files:
        return _json_error("没有收到文件")
    results = []
    try:
        for f in files:
            results.append(_save_upload(f))
    except PipelineError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        return _json_error(f"文件保存失败：{exc}")
    return jsonify({"files": [
        {"id": r["id"], "name": r["name"], "size": r["size"], "kind": r["kind"]}
        for r in results
    ]})


# ---------------------------------------------------------------- API：任务

@app.post("/api/jobs")
def create_job():
    body = request.get_json(silent=True) or {}
    file_ids = body.get("file_ids") or []
    profile = str(body.get("profile") or "standard")
    if profile not in ("quick", "standard", "deep"):
        profile = "standard"
    if not file_ids:
        return _json_error("请先上传至少一个文件")

    files: list[dict] = []
    for fid in file_ids:
        info = _resolve_upload(str(fid))
        if info is None:
            return _json_error(f"文件不存在或已过期：{fid}")
        files.append({"name": info["name"], "path": info["path"], "kind": info["kind"]})

    job = store.create(files, profile)
    event = threading.Event()
    with _CANCELS_LOCK:
        _CANCELS[job["id"]] = event
    _EXECUTOR.submit(run_job, job["id"], event)
    return jsonify({"job_id": job["id"]})


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    """对外返回的任务信息：隐藏本机文件路径。"""
    data = dict(job)
    data["files"] = [
        {"name": f.get("name", ""), "kind": f.get("kind", "")}
        for f in (job.get("files") or [])
    ]
    return data


@app.get("/api/jobs")
def list_jobs():
    return jsonify({"jobs": [_public_job(j) for j in store.list_jobs(20)]})


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        return _json_error("任务不存在", 404)
    return jsonify(_public_job(job))


@app.post("/api/jobs/<job_id>/cancel")
def cancel_job(job_id: str):
    with _CANCELS_LOCK:
        event = _CANCELS.get(job_id)
    if event is not None:
        event.set()
    job = store.get(job_id)
    if job is None:
        return _json_error("任务不存在", 404)
    if job.get("status") in ("pending", "running"):
        store.update(job_id, status="cancelled", message="任务已取消")
    return jsonify({"ok": True})


@app.get("/api/jobs/<job_id>/download")
def download(job_id: str):
    job = store.get(job_id)
    if job is None:
        return _json_error("任务不存在", 404)
    result = job.get("result") or {}
    filename = result.get("filename")
    if not filename:
        return _json_error("报告还未生成", 404)
    pdf_path = outputs_dir() / filename
    if not pdf_path.exists():
        return _json_error("报告文件已丢失，请重新生成", 404)
    return send_file(
        str(pdf_path),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@app.delete("/api/jobs/<job_id>")
def delete_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        return _json_error("任务不存在", 404)
    # 删除产出 PDF
    result = job.get("result") or {}
    if result.get("filename"):
        try:
            (outputs_dir() / result["filename"]).unlink(missing_ok=True)
        except Exception:
            pass
    # 删除上传的原始文件
    for f in job.get("files") or []:
        try:
            Path(f["path"]).unlink(missing_ok=True)
        except Exception:
            pass
    store.delete(job_id)
    with _CANCELS_LOCK:
        _CANCELS.pop(job_id, None)
    return jsonify({"ok": True})


# ---------------------------------------------------------------- 错误处理

@app.errorhandler(413)
def too_large(_e):
    return _json_error("文件太大，单次上传上限为 4GB", 413)


@app.errorhandler(404)
def not_found(_e):
    return _json_error("接口不存在", 404)


@app.errorhandler(500)
def server_error(_e):
    return _json_error("服务器内部错误", 500)


# ---------------------------------------------------------------- 启动

def _find_free_port(start: int = 8765, host: str = "127.0.0.1") -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError("找不到可用的本地端口")


def main() -> None:
    parser = argparse.ArgumentParser(description="学伴 StudyPilot")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    parser.add_argument("--port", type=int, default=0, help="端口（0 表示自动选择）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    if args.port:
        port = args.port
    else:
        cfg = config.load_config()
        preferred = int(cfg.get("server", {}).get("port") or 8765)
        port = _find_free_port(preferred, args.host)

    url = f"http://{args.host}:{port}"
    print("=" * 56)
    print("  学伴 StudyPilot 已启动")
    print(f"  访问地址：{url}")
    print("  关闭本窗口即可退出程序")
    print("=" * 56)

    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host=args.host, port=port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
