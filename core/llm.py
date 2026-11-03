"""LLM 客户端与「Map-Reduce」总结流水线。

设计目标：
- 兼容任意 OpenAI 兼容接口（DeepSeek / 硅基流动 / 通义 / 智谱 / Ollama / LM Studio / 自定义）
- 长文档自动分块，逐块提炼（Map），再合并为结构化报告（Reduce）
- 输出必须是 JSON；解析失败自动重试
- 支持 STUDY_PILOT_MOCK=1 的离线假数据模式（用于验证排版，不消耗 API）
"""

from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import PROVIDER_MAP, get_api_key
from .errors import CancelledError, PipelineError
from . import prompts

MOCK = os.environ.get("STUDY_PILOT_MOCK", "").strip() == "1"

CHUNK_CHARS = 6000       # 单块目标字符数
CHUNK_OVERLAP = 300      # 块间重叠
MAX_REDUCE_CHARS = 60000 # Reduce 输入上限，超出则分批合并
MAP_WORKERS = 2          # Map 并发数（避免触发限流）


# ---------------------------------------------------------------- 配置对象

@dataclass
class AIConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.3
    extra_headers: dict = field(default_factory=dict)


def ai_config_from(cfg: dict) -> AIConfig:
    ai = cfg.get("ai", {})
    return AIConfig(
        base_url=(ai.get("base_url") or "").strip(),
        api_key=get_api_key(cfg),
        model=(ai.get("model") or "").strip(),
        temperature=float(ai.get("temperature", 0.3) or 0.3),
        extra_headers=dict(ai.get("extra_headers") or {}),
    )


def _is_reasoning_model(model: str) -> bool:
    m = (model or "").lower()
    return any(k in m for k in ("reasoner", "o1", "o3", "o4", "r1", "thinking"))


def _client(cfg: AIConfig):
    from openai import OpenAI

    if not cfg.base_url:
        raise PipelineError("尚未配置 AI 接口地址，请先在「设置」中填写。")
    if not cfg.model:
        raise PipelineError("尚未配置模型名称，请先在「设置」中填写。")
    try:
        return OpenAI(
            base_url=cfg.base_url,
            api_key=cfg.api_key or "sk-no-key-required",
            timeout=600,
            max_retries=2,
            default_headers=cfg.extra_headers or None,
        )
    except TypeError:
        return OpenAI(
            base_url=cfg.base_url,
            api_key=cfg.api_key or "sk-no-key-required",
            timeout=600,
            max_retries=2,
        )


def _friendly_error(exc: Exception) -> PipelineError:
    """把 SDK 异常翻译成用户能看懂的中文提示。"""
    text = str(exc)
    low = text.lower()
    try:
        import openai

        if isinstance(exc, openai.AuthenticationError):
            return PipelineError("API Key 无效或已过期，请在「设置」中重新填写。")
        if isinstance(exc, openai.RateLimitError):
            return PipelineError("请求过于频繁或额度不足（429），请稍后再试或检查账户余额。")
        if isinstance(exc, openai.APIConnectionError):
            return PipelineError(f"无法连接 AI 接口：请检查网络、代理或 base_url 是否正确。（{text}）")
        if isinstance(exc, openai.NotFoundError):
            return PipelineError(f"接口地址或模型不存在（404）：请检查 base_url 与模型名。（{text}）")
    except Exception:
        pass
    if "401" in low or "unauthorized" in low:
        return PipelineError("API Key 无效或已过期，请在「设置」中重新填写。")
    if "429" in low:
        return PipelineError("请求过于频繁或额度不足（429），请稍后再试。")
    if "model" in low and "not found" in low:
        return PipelineError(f"模型名不存在：请检查设置中的模型名称。（{text}）")
    return PipelineError(f"AI 接口调用失败：{text}")


def chat(
    cfg: AIConfig,
    system: str,
    user: str,
    json_mode: bool = True,
    temperature: float | None = None,
) -> str:
    """单轮对话，返回文本内容。"""
    client = _client(cfg)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    kwargs: dict[str, Any] = {"model": cfg.model, "messages": messages, "timeout": 600}
    if temperature is not None:
        kwargs["temperature"] = temperature
    elif not _is_reasoning_model(cfg.model):
        kwargs["temperature"] = cfg.temperature
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:
        msg = str(exc).lower()
        # 部分服务商不支持 response_format，去掉后重试
        if json_mode and ("response_format" in msg or "unsupported" in msg or "invalid" in msg):
            kwargs.pop("response_format", None)
            try:
                resp = client.chat.completions.create(**kwargs)
            except Exception as exc2:
                raise _friendly_error(exc2) from exc2
        else:
            raise _friendly_error(exc) from exc

    if not resp.choices:
        raise PipelineError("AI 返回了空响应，请重试。")
    content = resp.choices[0].message.content or ""
    if not content.strip():
        raise PipelineError("AI 返回了空内容，请重试。")
    return content


# ---------------------------------------------------------------- JSON 工具

def parse_json(text: str) -> dict:
    """从模型输出中提取 JSON（兼容 ```json 包裹、前后多余文字）。"""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"AI 输出的不是合法 JSON（{exc}）。") from exc
    if not isinstance(data, dict):
        raise PipelineError("AI 输出的 JSON 结构不正确。")
    return data


def _normalize_report(data: dict) -> dict:
    """补齐缺失字段，保证渲染层不会因缺字段崩溃。"""
    def as_list(v):
        return v if isinstance(v, list) else []

    report = {
        "title": str(data.get("title") or "学习报告").strip(),
        "overview": str(data.get("overview") or "").strip(),
        "outline": [],
        "highlights": [],
        "study_methods": [],
        "review_plan": {"principles": "", "schedule": [], "daily_routine": []},
        "career": {"roles": [], "skills": [], "interview_topics": [], "note": ""},
        "priority": {
            "urgent_important": [],
            "important_not_urgent": [],
            "urgent_not_important": [],
            "not_important": [],
            "advice": "",
        },
        "quiz": [],
        "keywords": [],
    }

    for item in as_list(data.get("outline")):
        if isinstance(item, dict):
            report["outline"].append({
                "level": int(item.get("level") or 1),
                "title": str(item.get("title") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
                "source": str(item.get("source") or "").strip(),
            })

    for item in as_list(data.get("highlights")):
        if isinstance(item, dict):
            try:
                importance = int(item.get("importance") or 3)
            except (TypeError, ValueError):
                importance = 3
            report["highlights"].append({
                "title": str(item.get("title") or "").strip(),
                "explain": str(item.get("explain") or "").strip(),
                "importance": max(1, min(5, importance)),
                "source": str(item.get("source") or "").strip(),
                "exam_tip": str(item.get("exam_tip") or "").strip(),
            })

    for item in as_list(data.get("study_methods")):
        if isinstance(item, dict):
            report["study_methods"].append({
                "method": str(item.get("method") or "").strip(),
                "why": str(item.get("why") or "").strip(),
                "how": str(item.get("how") or "").strip(),
            })

    rp = data.get("review_plan") if isinstance(data.get("review_plan"), dict) else {}
    report["review_plan"] = {
        "principles": str(rp.get("principles") or "").strip(),
        "schedule": [
            {
                "day": str(s.get("day") or "").strip(),
                "focus": str(s.get("focus") or "").strip(),
                "tasks": [str(t).strip() for t in as_list(s.get("tasks")) if str(t).strip()],
            }
            for s in as_list(rp.get("schedule"))
            if isinstance(s, dict)
        ],
        "daily_routine": [str(t).strip() for t in as_list(rp.get("daily_routine")) if str(t).strip()],
    }

    career = data.get("career") if isinstance(data.get("career"), dict) else {}
    report["career"] = {
        "roles": [str(r).strip() for r in as_list(career.get("roles")) if str(r).strip()],
        "skills": [
            {
                "name": str(s.get("name") or "").strip(),
                "why": str(s.get("why") or "").strip(),
                "level": str(s.get("level") or "").strip(),
            }
            for s in as_list(career.get("skills"))
            if isinstance(s, dict)
        ],
        "interview_topics": [
            str(t).strip() for t in as_list(career.get("interview_topics")) if str(t).strip()
        ],
        "note": str(career.get("note") or "就业与薪资信息为 AI 基于公开常识的推断，仅供参考。").strip(),
    }

    priority = data.get("priority") if isinstance(data.get("priority"), dict) else {}
    for key in ("urgent_important", "important_not_urgent", "urgent_not_important", "not_important"):
        items = []
        for item in as_list(priority.get(key)):
            if isinstance(item, dict):
                items.append({
                    "item": str(item.get("item") or "").strip(),
                    "reason": str(item.get("reason") or "").strip(),
                })
            elif isinstance(item, str):
                items.append({"item": item.strip(), "reason": ""})
        report["priority"][key] = [i for i in items if i["item"]]
    report["priority"]["advice"] = str(priority.get("advice") or "").strip()

    for item in as_list(data.get("quiz")):
        if isinstance(item, dict) and item.get("q"):
            report["quiz"].append({
                "q": str(item.get("q") or "").strip(),
                "options": [str(o).strip() for o in as_list(item.get("options")) if str(o).strip()],
                "answer": str(item.get("answer") or "").strip(),
                "explain": str(item.get("explain") or "").strip(),
            })

    report["keywords"] = [str(k).strip() for k in as_list(data.get("keywords")) if str(k).strip()]
    return report


# ---------------------------------------------------------------- 分块

def chunk_text(text: str, max_chars: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """按字符数切块，尽量在段落/句号边界断开，并保留少量重叠。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        if end < n:
            window = text[start:end]
            # 优先在段落、标题、句号处断开
            candidates = [window.rfind("\n\n"), window.rfind("\n# "), window.rfind("。")]
            cut = max(candidates)
            if cut > int(max_chars * 0.5):
                end = start + cut + 1
        chunks.append(text[start:end])
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [c.strip() for c in chunks if c.strip()]


# ---------------------------------------------------------------- Map / Reduce

def _map_one(
    cfg: AIConfig,
    name: str,
    chunk: str,
    index: int,
    total: int,
    cancel_event: threading.Event | None,
) -> dict:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("任务已取消")
    user = prompts.MAP_USER.format(name=name, index=index, total=total, chunk=chunk)
    text = chat(cfg, prompts.MAP_SYSTEM, user, json_mode=True, temperature=0.2)
    try:
        return parse_json(text)
    except PipelineError:
        # 重试一次，并强调只输出 JSON
        retry_user = user + "\n\n注意：上一次输出不是合法 JSON。请只输出 JSON 对象本身，不要任何其他文字。"
        text = chat(cfg, prompts.MAP_SYSTEM, retry_user, json_mode=True, temperature=0.1)
        return parse_json(text)


def _compact_maps(maps: list[dict], per_topic: int = 12) -> list[dict]:
    """压缩 Map 结果，控制 Reduce 输入长度。"""
    out: list[dict] = []
    for m in maps:
        if not isinstance(m, dict):
            continue
        points = [p for p in (m.get("points") or []) if isinstance(p, dict)]
        out.append({
            "topic": str(m.get("topic") or ""),
            "points": [
                {
                    "title": str(p.get("title") or ""),
                    "detail": str(p.get("detail") or ""),
                    "importance": p.get("importance") or 3,
                    "source": str(p.get("source") or ""),
                }
                for p in points[:per_topic]
            ],
            "concepts": [str(c) for c in (m.get("concepts") or [])[:10]],
        })
    return out


def _reduce_once(
    cfg: AIConfig,
    name: str,
    profile: str,
    parts: list[dict],
    cancel_event: threading.Event | None,
) -> dict:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("任务已取消")
    map_json = json.dumps(parts, ensure_ascii=False)
    user = prompts.REDUCE_USER.format(
        name=name,
        profile_desc=prompts.profile_desc(profile),
        map_json=map_json,
    )
    text = chat(cfg, prompts.REDUCE_SYSTEM, user, json_mode=True, temperature=0.3)
    try:
        return parse_json(text)
    except PipelineError:
        retry_user = user + "\n\n注意：上一次输出不是合法 JSON。请只输出 JSON 对象本身。"
        text = chat(cfg, prompts.REDUCE_SYSTEM, retry_user, json_mode=True, temperature=0.2)
        return parse_json(text)


def _merge_partials(
    cfg: AIConfig,
    name: str,
    partials: list[dict],
    cancel_event: threading.Event | None,
) -> dict:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError("任务已取消")
    user = prompts.MERGE_USER.format(parts_json=json.dumps(partials, ensure_ascii=False))
    text = chat(cfg, prompts.MERGE_SYSTEM, user, json_mode=True, temperature=0.2)
    try:
        return parse_json(text)
    except PipelineError:
        retry_user = user + "\n\n注意：只输出合法 JSON。"
        text = chat(cfg, prompts.MERGE_SYSTEM, retry_user, json_mode=True, temperature=0.1)
        return parse_json(text)


def analyze(
    docs: list[tuple[str, str]],
    cfg: dict,
    profile: str = "standard",
    progress_cb: Callable[[int, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """把若干份资料文本总结为结构化报告。docs: [(文件名, 文本)]"""
    if MOCK:
        return _mock_report(docs, profile)

    ai = ai_config_from(cfg)
    if not docs:
        raise PipelineError("没有可总结的内容。")

    name = "、".join(d for d, _ in docs)[:120]
    combined = "\n\n".join(f"【资料：{d}】\n{t}" for d, t in docs if t.strip())
    if not combined.strip():
        raise PipelineError("资料中没有可用的文字内容，无法总结。")

    chunks = chunk_text(combined)
    total = len(chunks)

    def report_progress(done: int, message: str):
        if progress_cb:
            pct = 5 + int(65 * done / max(1, total))
            progress_cb(pct, message)

    maps: list[dict] = []
    done = 0
    if total == 1:
        report_progress(0, "AI 正在通读资料并提炼…")
        maps.append(_map_one(ai, name, chunks[0], 1, 1, cancel_event))
        done = 1
    else:
        with ThreadPoolExecutor(max_workers=min(MAP_WORKERS, total)) as pool:
            futures = {
                pool.submit(_map_one, ai, name, chunk, i + 1, total, cancel_event): i
                for i, chunk in enumerate(chunks)
            }
            for future in as_completed(futures):
                if cancel_event is not None and cancel_event.is_set():
                    raise CancelledError("任务已取消")
                try:
                    maps.append(future.result())
                except CancelledError:
                    raise
                except Exception as exc:  # 单块失败不阻断整体
                    maps.append({"topic": "", "points": [], "concepts": []})
                done += 1
                report_progress(done, f"AI 正在提炼第 {done}/{total} 块内容…")

    report_progress(total, "AI 正在合并整理成完整报告…")

    compact = _compact_maps(maps)
    payload_len = len(json.dumps(compact, ensure_ascii=False))

    if payload_len <= MAX_REDUCE_CHARS:
        data = _reduce_once(ai, name, profile, compact, cancel_event)
    else:
        # 分批 Reduce，再合并
        batches: list[list[dict]] = []
        current: list[dict] = []
        current_len = 0
        for part in compact:
            part_len = len(json.dumps(part, ensure_ascii=False))
            if current and current_len + part_len > MAX_REDUCE_CHARS * 0.8:
                batches.append(current)
                current, current_len = [], 0
            current.append(part)
            current_len += part_len
        if current:
            batches.append(current)

        partials: list[dict] = []
        for i, batch in enumerate(batches, 1):
            if progress_cb:
                progress_cb(
                    70 + int(10 * i / len(batches)),
                    f"AI 正在整理第 {i}/{len(batches)} 批内容…",
                )
            partials.append(_reduce_once(ai, name, profile, batch, cancel_event))
        data = _merge_partials(ai, name, partials, cancel_event)

    if progress_cb:
        progress_cb(82, "报告结构生成完成，正在排版…")
    return _normalize_report(data)


# ---------------------------------------------------------------- Mock（离线验证）

def _mock_report(docs: list[tuple[str, str]], profile: str) -> dict:
    """返回一份结构完整的假报告，用于没有 API Key 时验证全流程与排版。"""
    name = docs[0][0] if docs else "示例课程"
    chars = sum(len(t) for _, t in docs)
    return {
        "title": f"{name.rsplit('.', 1)[0]} 学习报告",
        "overview": (
            "这是一份用于验证流水线与排版效果的示例报告（当前为离线 Mock 模式）。"
            "真实使用时会由你配置的 AI 接口根据上传资料生成内容。"
            f"本次共收到 {len(docs)} 份资料、约 {chars} 字。"
        ),
        "outline": [
            {"level": 1, "title": "第 1 章 基础概念", "summary": "介绍核心术语与背景", "source": "第 1-3 页"},
            {"level": 2, "title": "1.1 什么是变量", "summary": "变量的定义与使用", "source": "第 1 页"},
            {"level": 2, "title": "1.2 数据类型", "summary": "数字、字符串、布尔值", "source": "第 2 页"},
            {"level": 1, "title": "第 2 章 核心语法", "summary": "运算符与表达式", "source": "第 4-8 页"},
            {"level": 2, "title": "2.1 算术运算符", "summary": "加减乘除与优先级", "source": "第 4 页"},
            {"level": 2, "title": "2.2 字符串操作", "summary": "拼接、切片、格式化", "source": "第 6 页"},
        ],
        "highlights": [
            {"title": "变量是数据的容器", "explain": "变量名指向内存中的值，赋值即建立引用关系。", "importance": 5, "source": "第 1 页", "exam_tip": "常考：变量命名规则、动态类型"},
            {"title": "运算符优先级", "explain": "算术 > 比较 > 逻辑，括号可改变顺序。", "importance": 4, "source": "第 4 页", "exam_tip": "面试常问：and/or 短路求值"},
            {"title": "字符串不可变", "explain": "字符串修改会生成新对象，原对象不变。", "importance": 4, "source": "第 6 页", "exam_tip": "常考：切片与拼接的性能差异"},
            {"title": "类型转换", "explain": "int()/str()/float() 显式转换，避免隐式错误。", "importance": 3, "source": "第 3 页", "exam_tip": "常考：字符串与数字混算报错"},
        ],
        "study_methods": [
            {"method": "费曼学习法", "why": "基础语法概念多，讲给别人听能暴露理解漏洞。", "how": "每学完一节，用白纸写下解释并录音复述。"},
            {"method": "主动回忆 + 间隔重复", "why": "编程语法需要长期记忆，反复提取比重复阅读有效。", "how": "用 Anki 制作语法卡片，按 1/3/7 天复习。"},
            {"method": "动手写代码", "why": "语法只有写出来才算掌握。", "how": "每个知识点写 3 个最小示例，并故意制造错误观察报错。"},
        ],
        "review_plan": {
            "principles": "采用间隔重复：第 1、3、7、15、30 天各复习一次，每次先回忆再查漏。",
            "schedule": [
                {"day": "第 1 天", "focus": "变量与数据类型", "tasks": ["重读笔记", "默写 10 个变量示例", "做 5 道自测题"]},
                {"day": "第 3 天", "focus": "运算符", "tasks": ["整理优先级表", "手算表达式结果"]},
                {"day": "第 7 天", "focus": "字符串操作", "tasks": ["练习切片与格式化", "写一个小工具"]},
                {"day": "第 15 天", "focus": "综合复习", "tasks": ["做一套综合练习", "整理错题"]},
                {"day": "第 30 天", "focus": "查漏补缺", "tasks": ["重做错题", "向他人讲解核心概念"]},
            ],
            "daily_routine": ["每天 15 分钟复习卡片", "每天写 10 行代码", "每周做一次自测"],
        },
        "career": {
            "roles": ["Python 开发工程师", "数据分析师", "自动化测试工程师"],
            "skills": [
                {"name": "Python 基础语法", "why": "所有 Python 岗位的入场券", "level": "熟练"},
                {"name": "数据结构与算法", "why": "决定面试与后期上限", "level": "入门"},
                {"name": "项目实践", "why": "简历上最能体现能力的部分", "level": "熟练"},
            ],
            "interview_topics": ["可变与不可变类型", "字符串常用方法", "运算符优先级", "列表与元组的区别"],
            "note": "就业与薪资信息为 AI 基于公开常识的推断，仅供参考，请以实际招聘信息为准。",
        },
        "priority": {
            "urgent_important": [
                {"item": "变量与数据类型", "reason": "后续所有内容的基础，必须立刻掌握"},
                {"item": "运算符优先级", "reason": "写代码时立刻会用到"},
            ],
            "important_not_urgent": [
                {"item": "字符串高级操作", "reason": "决定代码质量，需要长期积累"},
                {"item": "项目实践", "reason": "决定就业竞争力，越早开始越好"},
            ],
            "urgent_not_important": [
                {"item": "冷门内置函数", "reason": "用到再查即可，不必提前记忆"},
            ],
            "not_important": [
                {"item": "历史版本差异细节", "reason": "除非维护老项目，否则可跳过"},
            ],
            "advice": "先花 70% 时间打牢基础语法并动手写，再用 30% 时间做小项目；不要一开始就背函数表。",
        },
        "quiz": [
            {"q": "以下哪个是合法的变量名？", "options": ["2name", "my-name", "_name", "class"], "answer": "C", "explain": "变量名不能以数字开头、不能含连字符、不能是关键字。"},
            {"q": "表达式 3 + 4 * 2 的结果是？", "options": ["14", "11", "24", "9"], "answer": "B", "explain": "乘法优先级高于加法，先算 4*2=8，再加 3。"},
            {"q": "字符串 s = 'abc'，s[1:] 的结果是？", "options": ["'a'", "'bc'", "'ab'", "'abc'"], "answer": "B", "explain": "切片从索引 1 到末尾，得到 'bc'。"},
        ],
        "keywords": ["变量", "数据类型", "运算符", "字符串", "类型转换"],
    }
