"""一键打包脚本：调用 PyInstaller 生成 dist/StudyPilot，并压缩为 zip。

用法：
    .venv\\Scripts\\python.exe build.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

try:  # 控制台编码兼容（GBK 环境下避免特殊字符报错）
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def sha_(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    print("== 学伴 StudyPilot 打包 ==")

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未检测到 PyInstaller，正在安装…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller"]
        )

    for name in ("build", "dist"):
        shutil.rmtree(ROOT / name, ignore_errors=True)

    print("\n正在打包（可能需要几分钟）…")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "study-pilot.spec", "--noconfirm"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print("打包失败，请检查上面的错误信息。")
        return result.returncode

    dist = ROOT / "dist" / "StudyPilot"
    exe = dist / "StudyPilot.exe"
    if not exe.exists():
        print("未找到 StudyPilot.exe，打包可能不完整。")
        return 1

    total = sum(p.stat().st_size for p in dist.rglob("*") if p.is_file())
    print(f"\n产物目录：{dist}")
    print(f"解压后大小：{total / 1024 / 1024:.1f} MB")

    zip_path = ROOT / "StudyPilot-win64.zip"
    if zip_path.exists():
        zip_path.unlink()
    print("\n正在压缩…")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(dist.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(dist.parent))

    print(f"压缩包：{zip_path}")
    print(f"压缩后大小：{zip_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"SHA256：{sha_(zip_path)}")
    print("\n完成 ✓ 解压 StudyPilot-win64.zip 后双击 StudyPilot/StudyPilot.exe 即可使用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
