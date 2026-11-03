"""配置读写：默认值、服务商预设、API Key 本地加密（Windows DPAPI）。

配置文件位于 %LOCALAPPDATA%\\StudyPilot\\config.json。
API Key 使用 Windows DPAPI 加密后以 "enc:<base64>" 形式存储；
非 Windows 或加密失败时退化为明文，并在读取时兼容旧格式。
"""

from __future__ import annotations

import base64
import copy
import ctypes
import json
import os
import threading
from ctypes import wintypes
from typing import Any

from .paths import config_path

_LOCK = threading.RLock()

# ---------------------------------------------------------------- 默认配置

DEFAULT_CONFIG: dict[str, Any] = {
    "ai": {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "temperature": 0.3,
        # 某些服务商需要额外请求头，例如 {"X-Api-Version": "..."}
        "extra_headers": {},
    },
    "asr": {
        "model_size": "small",  # tiny / base / small / medium / large-v3
        "model_path": "",       # 可选：本地模型目录（留空则按 model_size 自动下载）
        "device": "auto",       # auto / cpu / cuda
        "language": "auto",     # auto / zh / en ...
    },
    "report": {
        "profile": "standard",  # quick / standard / deep
    },
    "server": {
        "port": 8765,
    },
}

# ---------------------------------------------------------------- 服务商预设
# 前端下拉列表直接消费此结构；也支持任意 OpenAI 兼容接口（custom）。

PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "hint": "国内直连，中文效果好，性价比高（推荐）",
    },
    {
        "id": "siliconflow",
        "name": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": [
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct",
            "Qwen/Qwen3-8B",
        ],
        "hint": "聚合多种开源模型，按量计费，注册送额度",
    },
    {
        "id": "dashscope",
        "name": "阿里云通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
        "hint": "阿里云百炼，OpenAI 兼容模式",
    },
    {
        "id": "zhipu",
        "name": "智谱 AI",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-flash", "glm-4-plus", "glm-4-air"],
        "hint": "GLM 系列，flash 版本免费额度较多",
    },
    {
        "id": "moonshot",
        "name": "Moonshot 月之暗面",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "kimi-k2-0711-preview"],
        "hint": "Kimi 系列，长文本能力好",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
        "hint": "需要境外网络环境",
    },
    {
        "id": "ollama",
        "name": "Ollama（本地离线）",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": ["qwen2.5:7b", "llama3.1:8b", "qwen3:8b"],
        "hint": "本机运行，完全离线，无需 API Key",
    },
    {
        "id": "lmstudio",
        "name": "LM Studio（本地离线）",
        "base_url": "http://127.0.0.1:1234/v1",
        "models": ["local-model"],
        "hint": "本机运行，完全离线，无需 API Key",
    },
    {
        "id": "custom",
        "name": "自定义 / 其他兼容接口",
        "base_url": "",
        "models": [],
        "hint": "填入任意 OpenAI 兼容的 base_url 与模型名",
    },
]

PROVIDER_MAP = {p["id"]: p for p in PROVIDERS}


# ---------------------------------------------------------------- DPAPI 加解密

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_protect(data: bytes) -> bytes:
    """调用 Windows CryptProtectData 加密（仅当前用户可解密）。"""
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptProtectData 失败")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptUnprotectData 失败")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def encrypt_secret(plain: str) -> str:
    """加密 API Key，返回可直接写入 JSON 的字符串。"""
    if not plain:
        return ""
    if os.name != "nt":
        return "plain:" + plain
    try:
        raw = _dpapi_protect(plain.encode("utf-8"))
        return "enc:" + base64.b64encode(raw).decode("ascii")
    except Exception:
        return "plain:" + plain


def decrypt_secret(stored: str) -> str:
    """解密 API Key；兼容历史明文。"""
    if not stored:
        return ""
    if stored.startswith("plain:"):
        return stored[len("plain:"):]
    if stored.startswith("enc:"):
        if os.name != "nt":
            return ""
        try:
            raw = base64.b64decode(stored[len("enc:"):])
            return _dpapi_unprotect(raw).decode("utf-8")
        except Exception:
            return ""
    return stored  # 历史明文格式


def mask_key(key: str) -> str:
    """把 Key 打码用于前端展示，例如 sk-abc***wxyz。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:5] + "*" * 4 + key[-4:]


# ---------------------------------------------------------------- 读写

def _deep_merge(base: dict, override: dict) -> dict:
    """把 override 深合并进 base 的副本，缺省字段保持默认值。"""
    result = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config() -> dict[str, Any]:
    """读取配置；文件不存在或损坏时返回默认配置。"""
    with _LOCK:
        path = config_path()
        if not path.exists():
            return copy.deepcopy(DEFAULT_CONFIG)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return copy.deepcopy(DEFAULT_CONFIG)
        return _deep_merge(DEFAULT_CONFIG, raw if isinstance(raw, dict) else {})


def save_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """规范化并保存配置，返回保存后的完整配置。"""
    with _LOCK:
        merged = _deep_merge(DEFAULT_CONFIG, cfg)
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(path)
        return merged


def get_api_key(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    return decrypt_secret(cfg.get("ai", {}).get("api_key", ""))


def set_api_key(cfg: dict[str, Any], plain: str) -> dict[str, Any]:
    cfg = copy.deepcopy(cfg)
    cfg.setdefault("ai", {})["api_key"] = encrypt_secret(plain)
    return cfg


def public_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    """返回给前端的安全配置：不包含明文 Key。"""
    key = get_api_key(cfg)
    return {
        "ai": {
            "provider": cfg["ai"].get("provider", "custom"),
            "base_url": cfg["ai"].get("base_url", ""),
            "model": cfg["ai"].get("model", ""),
            "api_key_set": bool(key),
            "api_key_masked": mask_key(key),
            "temperature": cfg["ai"].get("temperature", 0.3),
            "extra_headers": cfg["ai"].get("extra_headers", {}),
        },
        "asr": dict(cfg.get("asr", {})),
        "report": dict(cfg.get("report", {})),
        "server": dict(cfg.get("server", {})),
    }
