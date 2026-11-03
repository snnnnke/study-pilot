"""手动下载 faster-whisper 模型文件（离线部署 / 受限网络环境使用）。

用法：
    .venv\\Scripts\\python.exe scripts\\fetch_model.py tiny [输出目录]

默认从 HF_ENDPOINT（默认 https://hf-mirror.com）下载到
<项目>/.data/models-<size>，下载完成后可在设置中通过
「把模型目录路径填到模型大小」使用，或直接把目录名传给 transcribe。
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}

FILES = [
    "config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.txt",
    "preprocessor_config.json",
]


def download(size: str, out_dir: Path) -> Path:
    endpoint = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com").rstrip("/")
    repo = REPOS.get(size)
    if not repo:
        raise SystemExit(f"未知模型：{size}，可选：{', '.join(REPOS)}")
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        dest = out_dir / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  跳过（已存在）：{name}")
            continue
        url = f"{endpoint}/{repo}/resolve/main/{name}"
        print(f"  下载：{url}")
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
                    )
                },
            )
            with urllib.request.urlopen(request, timeout=180) as resp, dest.open("wb") as fh:
                shutil.copyfileobj(resp, fh)
        except Exception as exc:
            raise SystemExit(f"下载失败：{name} -> {exc}")
        print(f"    -> {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")

    print(f"\n完成：{out_dir}")
    return out_dir


def main() -> int:
    size = sys.argv[1] if len(sys.argv) > 1 else "tiny"
    if len(sys.argv) > 2:
        out = Path(sys.argv[2])
    else:
        out = ROOT / ".data" / f"models-{size}"
    print(f"== 下载 faster-whisper 模型 {size} ==")
    download(size, out)
    print("\n在 transcribe() 中把 model_size 设为该目录路径即可离线使用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
