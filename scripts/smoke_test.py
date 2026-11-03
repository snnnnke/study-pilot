"""冒烟测试：不调用真实 API，用 Mock 报告跑通「解析 → 总结 → 渲染 PDF」全流程。

用法：
    .venv\\Scripts\\python.exe scripts\\smoke_test.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["STUDY_PILOT_MOCK"] = "1"
os.environ.setdefault("STUDY_PILOT_HOME", str(ROOT / ".data"))
sys.path.insert(0, str(ROOT))

from core import extractors, llm, report  # noqa: E402


def main() -> int:
    docs_dir = ROOT / "docs"
    files = sorted(docs_dir.glob("*.pdf"))
    if not files:
        print("未找到 docs/*.pdf 测试文件")
        return 1

    print("=" * 60)
    print("1) 文件解析")
    docs: list[tuple[str, str]] = []
    for f in files:
        t0 = time.time()
        doc = extractors.extract(f)
        print(
            f"  - {f.name}\n"
            f"    kind={doc.kind} pages={doc.pages} chars={doc.chars} "
            f"耗时={time.time() - t0:.2f}s warnings={doc.warnings}"
        )
        if not doc.text.strip():
            print("    [警告] 没有提取到文字")
        docs.append((f.name, doc.text))

    print("\n2) AI 总结（Mock 模式，不消耗 API）")
    t0 = time.time()
    result = llm.analyze(docs, {}, profile="standard")
    print(
        f"  标题：{result['title']}\n"
        f"  大纲 {len(result['outline'])} 条 / 重点 {len(result['highlights'])} 条 / "
        f"自测题 {len(result['quiz'])} 题 / 耗时 {time.time() - t0:.2f}s"
    )

    print("\n3) 生成 PDF")
    out_dir = ROOT / ".data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"smoke_{ts}.pdf"
    t0 = time.time()
    report.build_report(result, [f.name for f in files], out_path)
    size_kb = out_path.stat().st_size / 1024
    print(f"  输出：{out_path}\n  大小：{size_kb:.1f} KB  耗时：{time.time() - t0:.2f}s")

    print("\n4) 校验 PDF 并渲染预览图")
    import pymupdf

    with pymupdf.open(str(out_path)) as pdf:
        print(f"  页数：{pdf.page_count}")
        preview_dir = ROOT / ".data" / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        for idx in range(min(pdf.page_count, 8)):
            page = pdf.load_page(idx)
            pix = page.get_pixmap(dpi=100)
            path = preview_dir / f"page_{idx + 1}.png"
            pix.save(str(path))
            print(f"  预览：{path}")

    print("\n完成 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
