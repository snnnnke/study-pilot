"""验证真实 HTTP 调用链路：内置一个 Mock OpenAI 服务，走完整的「分块 Map → Reduce」流程。

它不同于 STUDY_PILOT_MOCK 的环境变量假数据——这里真的会：
  1. 启动一个本地 HTTP 服务，模拟 /v1/chat/completions
  2. 用 openai SDK 通过 HTTP 发起请求
  3. 解析返回 JSON、合并、生成 PDF

用法：
    .venv\\Scripts\\python.exe scripts\\llm_http_test.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("STUDY_PILOT_HOME", str(ROOT / ".data" / "http-test"))
sys.path.insert(0, str(ROOT))

MAP_RESULT = {
    "topic": "Python 基础语法",
    "points": [
        {"title": "变量与赋值", "detail": "变量是数据的引用，赋值即绑定。", "importance": 5, "source": "第 1 页"},
        {"title": "运算符优先级", "detail": "算术 > 比较 > 逻辑。", "importance": 4, "source": "第 4 页"},
    ],
    "concepts": ["变量", "运算符"],
    "difficulties": ["隐式类型转换"],
    "questions": ["and 和 or 的短路规则是什么？"],
}

REDUCE_RESULT = {
    "title": "Python 基础语法学习报告",
    "overview": "本报告由 HTTP Mock 服务生成，用于验证真实调用链路与排版。",
    "outline": [
        {"level": 1, "title": "第 1 章 变量与类型", "summary": "基础概念", "source": "第 1 页"},
        {"level": 2, "title": "1.1 变量", "summary": "赋值与引用", "source": "第 1 页"},
    ],
    "highlights": [
        {"title": "变量是引用", "explain": "赋值不会复制对象。", "importance": 5, "source": "第 1 页", "exam_tip": "常考：可变对象共享"},
    ],
    "study_methods": [
        {"method": "费曼学习法", "why": "暴露理解漏洞", "how": "每节讲给别人听"},
    ],
    "review_plan": {
        "principles": "间隔重复",
        "schedule": [
            {"day": "第 1 天", "focus": "变量", "tasks": ["复述", "写示例"]},
            {"day": "第 3 天", "focus": "运算符", "tasks": ["手算表达式"]},
            {"day": "第 7 天", "focus": "字符串", "tasks": ["练习切片"]},
            {"day": "第 15 天", "focus": "综合", "tasks": ["做套题"]},
            {"day": "第 30 天", "focus": "查漏", "tasks": ["重做错题"]},
        ],
        "daily_routine": ["每天 15 分钟卡片"],
    },
    "career": {
        "roles": ["Python 开发"],
        "skills": [{"name": "语法", "why": "入场券", "level": "熟练"}],
        "interview_topics": ["可变与不可变"],
        "note": "仅供参考。",
    },
    "priority": {
        "urgent_important": [{"item": "变量", "reason": "基础"}],
        "important_not_urgent": [{"item": "项目实践", "reason": "长期"}],
        "urgent_not_important": [{"item": "冷门函数", "reason": "用到再查"}],
        "not_important": [{"item": "版本细节", "reason": "可跳过"}],
        "advice": "先打基础再做项目。",
    },
    "quiz": [
        {"q": "变量赋值会复制对象吗？", "options": ["A. 会", "B. 不会"], "answer": "B", "explain": "赋值只是引用。"},
    ],
    "keywords": ["变量", "运算符"],
}

REQUEST_COUNT = {"n": 0}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except Exception:
            body = {}
        messages = body.get("messages") or []
        system = messages[0]["content"] if messages else ""
        REQUEST_COUNT["n"] += 1

        if "学习教练" in system or "知识工程师" in system:
            payload = MAP_RESULT
        elif "学习规划师" in system:
            payload = REDUCE_RESULT
        else:
            payload = REDUCE_RESULT

        content = json.dumps(payload, ensure_ascii=False)
        data = json.dumps({
            "id": f"chatcmpl-{REQUEST_COUNT['n']}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "mock-model"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }, ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main() -> int:
    server = HTTPServer(("127.0.0.1", 9999), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print("Mock OpenAI 服务已启动：http://127.0.0.1:9999/v1")

    from core import extractors, llm, report

    pdfs = sorted((ROOT / "docs").glob("*.pdf"))[:1]
    if not pdfs:
        print("缺少 docs/*.pdf")
        return 1
    doc = extractors.extract(pdfs[0])
    docs = [(pdfs[0].name, doc.text)]

    cfg = {
        "ai": {
            "base_url": "http://127.0.0.1:9999/v1",
            "api_key": "sk-test",
            "model": "mock-model",
            "temperature": 0.3,
            "extra_headers": {},
        }
    }

    print("\n调用 llm.analyze（真实 HTTP）…")
    t0 = time.time()
    result = llm.analyze(docs, cfg, profile="standard")
    print(f"  完成，耗时 {time.time() - t0:.2f}s，请求次数 {REQUEST_COUNT['n']}")
    print(f"  标题：{result['title']}")
    print(f"  大纲 {len(result['outline'])} / 重点 {len(result['highlights'])} / 自测 {len(result['quiz'])}")

    out = ROOT / ".data" / "http-test" / f"http_{time.strftime('%H%M%S')}.pdf"
    report.build_report(result, [pdfs[0].name], out)
    print(f"  PDF：{out}（{out.stat().st_size / 1024:.0f} KB）")

    server.shutdown()
    print("\nHTTP 链路验证通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
