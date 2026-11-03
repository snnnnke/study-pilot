"""本地语音转写：faster-whisper，完全离线。

- 首次使用会自动下载模型到数据目录（默认走 hf-mirror.com 镜像）。
- 支持 CPU / CUDA 自动检测；CPU 默认 int8 量化。
- 转写结果带 [mm:ss] 时间戳，方便报告引用出处。
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

from .errors import CancelledError, PipelineError
from .paths import models_dir

_MODEL_CACHE: dict[tuple, object] = {}
_MODEL_LOCK = threading.Lock()

# 各模型的大致体积（MB），用于提示用户
MODEL_SIZES = {
    "tiny": 75,
    "base": 145,
    "small": 466,
    "medium": 1500,
    "large-v3": 3100,
}

# 默认走国内可访问的 HuggingFace 镜像（用户可用 HF_ENDPOINT 环境变量覆盖）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


def _resolve_device(device: str) -> tuple[str, str]:
    """返回 (device, compute_type)。"""
    device = (device or "auto").lower()
    if device == "cpu":
        return "cpu", "int8"
    if device in ("cuda", "gpu"):
        return "cuda", "float16"
    # auto：CUDA 可用则用 GPU，否则 CPU
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def get_model(
    size: str = "small",
    device: str = "auto",
    progress_cb: Callable[[int, str], None] | None = None,
):
    """加载并缓存 Whisper 模型（同一配置只加载一次）。"""
    dev, compute_type = _resolve_device(device)
    key = (size, dev, compute_type)
    with _MODEL_LOCK:
        model = _MODEL_CACHE.get(key)
        if model is not None:
            return model
        from faster_whisper import WhisperModel

        # 允许直接传入本地模型目录（离线部署 / 手动下载模型）
        is_local = os.path.isdir(size)
        approx = 0 if is_local else MODEL_SIZES.get(size, 0)
        if progress_cb:
            if is_local:
                progress_cb(2, f"正在加载本地语音模型：{size} …")
            else:
                progress_cb(
                    2,
                    f"正在加载语音模型 {size}（首次使用需下载，约 {approx}MB，请耐心等待）…",
                )
        try:
            model = WhisperModel(
                size if is_local else size,
                device=dev,
                compute_type=compute_type,
                download_root=None if is_local else str(models_dir()),
            )
        except Exception as exc:
            raise PipelineError(
                f"语音模型 {size} 加载失败：{exc}\n"
                "请检查：① 网络是否可访问 HuggingFace（可设置环境变量 "
                "HF_ENDPOINT=https://hf-mirror.com）② 磁盘剩余空间是否充足 "
                "③ 是否可以在设置中换用更小的模型（base / tiny）。"
            ) from exc
        _MODEL_CACHE[key] = model
        return model


def _fmt_time(seconds: float) -> str:
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def transcribe(
    path: str | Path,
    model_size: str = "small",
    device: str = "auto",
    language: str = "auto",
    progress_cb: Callable[[int, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    """把音频/视频转成带时间戳的文字稿。"""
    model = get_model(size=model_size, device=device, progress_cb=progress_cb)

    lang = None if (not language or language == "auto") else language
    segments, info = model.transcribe(
        str(path),
        language=lang,
        vad_filter=True,
        beam_size=5,
    )
    duration = float(getattr(info, "duration", 0) or 0)
    total_sec = duration or 0

    pieces: list[str] = []
    last_ts = -120.0

    for seg in segments:
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError("转写已取消")
        text = (seg.text or "").strip()
        if not text:
            continue
        start = float(seg.start or 0)
        if start - last_ts >= 60:
            pieces.append(f"\n[{_fmt_time(start)}] ")
            last_ts = start
        pieces.append(text)
        if progress_cb:
            if total_sec > 0:
                pct = min(99, int(2 + 96 * float(seg.end or 0) / total_sec))
            else:
                pct = 50
            progress_cb(pct, f"语音转写中… 已处理到 {_fmt_time(start)}")

    return "".join(pieces).strip()
