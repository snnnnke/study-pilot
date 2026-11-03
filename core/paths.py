"""路径管理：同时兼容"源码运行"与"PyInstaller 打包运行"。

打包后：
  - 只读资源（web/）位于 sys._MEIPASS（onedir 模式下为 _internal/）
  - 可写数据（配置、上传、输出、日志）位于 %LOCALAPPDATA%\\StudyPilot
源码运行时：
  - 资源位于项目根目录
  - 数据目录仍位于 %LOCALAPPDATA%\\StudyPilot（可用 STUDY_PILOT_HOME 覆盖）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME_EN = "StudyPilot"


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包环境中。"""
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """程序根目录：源码根目录 / exe 所在目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """只读资源根目录。打包后是 _MEIPASS，源码运行时是项目根目录。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", str(app_root())))
    return app_root()


def web_dir() -> Path:
    """前端静态文件目录。"""
    return resource_root() / "web"


def data_root() -> Path:
    """可写数据根目录。"""
    override = os.environ.get("STUDY_PILOT_HOME", "").strip()
    if override:
        root = Path(override).expanduser()
    else:
        base = (
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or str(Path.home())
        )
        root = Path(base) / APP_NAME_EN
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sub(name: str) -> Path:
    p = data_root() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def uploads_dir() -> Path:
    return _sub("uploads")


def outputs_dir() -> Path:
    return _sub("outputs")


def jobs_dir() -> Path:
    return _sub("jobs")


def models_dir() -> Path:
    """faster-whisper 模型缓存目录（默认在数据目录内，便于卸载清理）。"""
    return _sub("models")


def logs_dir() -> Path:
    return _sub("logs")


def config_path() -> Path:
    return data_root() / "config.json"


def instance_lock_path() -> Path:
    return data_root() / "instance.lock"
