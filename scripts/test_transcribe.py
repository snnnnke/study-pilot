"""验证本地 faster-whisper 转写链路（首次会下载 tiny 模型，约 75MB）。

用生成的 8kHz/16k 正弦波 WAV 验证模型加载与解码流程。
用法：
    .venv\\Scripts\\python.exe scripts\\test_transcribe.py
"""

from __future__ import annotations

import math
import os
import struct
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("STUDY_PILOT_HOME", str(ROOT / ".data" / "asr-test"))
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # 部分沙箱环境禁用 xet 可避免 symlink 检测失败
sys.path.insert(0, str(ROOT))


def make_wav(path: Path, seconds: float = 3.0, rate: int = 16000) -> None:
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            value = int(8000 * math.sin(2 * math.pi * 440 * i / rate))
            frames += struct.pack("<h", value)
        w.writeframes(bytes(frames))


def main() -> int:
    tmp = ROOT / ".data" / "asr-test"
    tmp.mkdir(parents=True, exist_ok=True)
    wav = tmp / "tone.wav"
    make_wav(wav)
    print(f"测试音频：{wav} ({wav.stat().st_size} bytes)")

    from core.transcribe import transcribe

    progresses = []

    def cb(p: int, m: str) -> None:
        progresses.append((p, m))
        print(f"  [{p:3d}%] {m}")

    t0 = time.time()
    text = transcribe(wav, model_size="tiny", device="cpu", language="zh", progress_cb=cb)
    elapsed = time.time() - t0
    print(f"\n转写完成，耗时 {elapsed:.1f}s，结果长度 {len(text)}")
    print(f"结果预览：{text[:200]!r}")
    print("链路验证通过 ✓（正弦波无语音，结果为空属正常）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
