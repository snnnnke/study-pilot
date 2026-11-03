"""任务流水线：解析 → 转写 → AI 总结 → PDF 渲染。

每个任务在独立后台线程中执行，通过 store 更新进度，前端轮询读取。
"""

from __future__ import annotations

import threading
import time
import traceback

from . import extractors, llm, report, store
from .config import load_config
from .errors import CancelledError, PipelineError
from .paths import outputs_dir, logs_dir
from .transcribe import transcribe


def _count_pages(pdf_path: str) -> int:
    try:
        import pymupdf

        with pymupdf.open(str(pdf_path)) as doc:
            return doc.page_count
    except Exception:
        return 0


def _log(job_id: str, text: str) -> None:
    try:
        p = logs_dir() / f"{job_id}.log"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%H:%M:%S')}] {text}\n")
    except Exception:
        pass


def run_job(job_id: str, cancel_event: threading.Event) -> None:
    """执行一个任务。异常一律吞掉并写入任务状态，避免线程崩溃。"""
    job = store.get(job_id)
    if job is None:
        return

    def progress(pct: int, msg: str, stage: str | None = None) -> None:
        if cancel_event.is_set():
            return
        fields: dict = {
            "status": "running",
            "progress": max(0, min(99, int(pct))),
            "message": msg,
        }
        if stage:
            fields["stage"] = stage
        store.update(job_id, **fields)

    try:
        cfg = load_config()
        files: list[dict] = job.get("files") or []
        total = max(1, len(files))
        _log(job_id, f"任务开始，共 {len(files)} 个文件")

        # ---------------- 1. 解析 / 转写
        docs: list[tuple[str, str]] = []
        for i, f in enumerate(files):
            if cancel_event.is_set():
                raise CancelledError()

            name = f.get("name") or "资料"
            kind = f.get("kind") or extractors.kind_for(name)
            base = 2 + 30 * i / total

            if kind == "media":
                progress(base, f"正在转写音视频「{name}」…", "transcribe")
                asr = cfg.get("asr", {})

                def asr_progress(p: int, m: str, _i=i, _base=base) -> None:
                    progress(
                        int(_base + 28 * (p / 100) / total),
                        m,
                        "transcribe",
                    )

                text = transcribe(
                    f["path"],
                    model_size=asr.get("model_path") or asr.get("model_size", "small"),
                    device=asr.get("device", "auto"),
                    language=asr.get("language", "auto"),
                    progress_cb=asr_progress,
                    cancel_event=cancel_event,
                )
                if not text.strip():
                    raise PipelineError(f"「{name}」没有转写出文字，可能是纯音乐或无语音内容。")
                docs.append((name, text))
                _log(job_id, f"转写完成：{name}，{len(text)} 字")
            else:
                progress(base, f"正在解析「{name}」…", "extract")
                doc = extractors.extract(f["path"], name)
                for w in doc.warnings:
                    _log(job_id, f"警告：{w}")
                if not doc.text.strip():
                    raise PipelineError(f"「{name}」没有提取到文字，无法总结。")
                docs.append((name, doc.text))
                _log(job_id, f"解析完成：{name}，{doc.chars} 字")

        if cancel_event.is_set():
            raise CancelledError()
        if not docs:
            raise PipelineError("没有可处理的文件。")

        # ---------------- 2. AI 总结
        progress(33, "正在用 AI 提取知识结构…", "analyze")

        def analyze_progress(p: int, m: str) -> None:
            progress(max(33, p), m, "analyze")

        profile = job.get("profile") or "standard"
        if profile not in ("quick", "standard", "deep"):
            profile = "standard"
        result = llm.analyze(
            docs,
            cfg,
            profile=profile,
            progress_cb=analyze_progress,
            cancel_event=cancel_event,
        )

        if cancel_event.is_set():
            raise CancelledError()

        # ---------------- 3. 渲染 PDF
        progress(85, "正在生成 PDF 排版…", "render")
        title = result.get("title") or "学习报告"
        slug = report.safe_filename(title)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_name = f"学伴报告_{slug}_{ts}.pdf"
        out_path = outputs_dir() / out_name

        report.build_report(result, [f.get("name", "") for f in files], out_path)
        pages = _count_pages(str(out_path))
        _log(job_id, f"PDF 生成完成：{out_path}（{pages} 页）")

        # ---------------- 4. 完成
        store.update(
            job_id,
            status="done",
            stage="done",
            progress=100,
            message="报告已生成",
            result={
                "download_url": f"/api/jobs/{job_id}/download",
                "filename": out_name,
                "title": title,
                "pages": pages,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )

    except CancelledError:
        _log(job_id, "任务被取消")
        store.update(job_id, status="cancelled", message="任务已取消")
    except PipelineError as exc:
        _log(job_id, f"失败：{exc}")
        store.update(job_id, status="failed", message="生成失败", error=str(exc))
    except Exception as exc:  # 未预期异常
        detail = f"{type(exc).__name__}: {exc}"
        _log(job_id, f"未预期异常：\n{traceback.format_exc()}")
        store.update(job_id, status="failed", message="生成失败", error=detail)
