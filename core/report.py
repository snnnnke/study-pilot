"""PDF 报告生成：ReportLab Platypus。

排版结构：封面 → 目录（自动页码）→ 概述 → 大纲 → 核心重点 →
学习方法 → 复习计划 → 就业价值 → 轻重缓急（四象限）→ 自测题 → 关键词。

中文字体策略：优先加载 Windows 自带微软雅黑（msyh.ttc），
依次回退黑体 / 宋体 / ReportLab 内置 CID 字体，保证任何 Windows 机器都能渲染。
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------- 配色

INK = colors.HexColor("#1E293B")
MUTED = colors.HexColor("#64748B")
PRIMARY = colors.HexColor("#3155C6")
PRIMARY_DARK = colors.HexColor("#1E3A8A")
ACCENT = colors.HexColor("#2563EB")
LIGHT_BG = colors.HexColor("#F1F5F9")
BORDER = colors.HexColor("#CBD5E1")
WHITE = colors.white

QUAD_COLORS = {
    "urgent_important": ("#FEE2E2", "#B91C1C", "重要且紧急", "立刻掌握"),
    "important_not_urgent": ("#DBEAFE", "#1D4ED8", "重要不紧急", "长期积累"),
    "urgent_not_important": ("#FEF3C7", "#B45309", "紧急不重要", "速成应付"),
    "not_important": ("#E5E7EB", "#475569", "不重要不紧急", "可跳过"),
}

# ---------------------------------------------------------------- 字体

_FONT_NAME = "STSong-Light"
_FONT_BOLD = "STSong-Light"
_FONT_READY = False


def _try_ttf(name: str, path: str, subfont: int | None = None) -> bool:
    try:
        if subfont is None:
            pdfmetrics.registerFont(TTFont(name, path))
        else:
            pdfmetrics.registerFont(TTFont(name, path, subfontIndex=subfont))
        return True
    except Exception:
        return False


def ensure_font() -> None:
    """注册可用的中文字体（全局只执行一次）。"""
    global _FONT_NAME, _FONT_BOLD, _FONT_READY
    if _FONT_READY:
        return

    candidates = [
        # (注册名, 路径, 子字体索引)
        ("MSYH", r"C:\Windows\Fonts\msyh.ttc", 0),
        ("MSYH", r"C:\Windows\Fonts\msyh.ttf", None),
        ("SIMHEI", r"C:\Windows\Fonts\simhei.ttf", None),
        ("SIMSUN", r"C:\Windows\Fonts\simsun.ttc", 0),
        ("NOTO", r"C:\Windows\Fonts\NotoSansSC-Regular.otf", None),
        ("DENG", r"C:\Windows\Fonts\Deng.ttf", None),
    ]
    bold_candidates = [
        ("MSYH-Bold", r"C:\Windows\Fonts\msyhbd.ttc", 0),
        ("MSYH-Bold", r"C:\Windows\Fonts\msyhbd.ttf", None),
        ("SIMHEI-Bold", r"C:\Windows\Fonts\simhei.ttf", None),
    ]

    normal_name = None
    for name, path, sub in candidates:
        if os.path.exists(path) and _try_ttf(name, path, sub):
            normal_name = name
            break

    bold_name = normal_name
    if normal_name:
        for name, path, sub in bold_candidates:
            if os.path.exists(path) and _try_ttf(name, path, sub):
                bold_name = name
                break
        try:
            pdfmetrics.registerFontFamily(
                normal_name,
                normal=normal_name,
                bold=bold_name,
                italic=normal_name,
                boldItalic=bold_name,
            )
        except Exception:
            pass
        _FONT_NAME = normal_name
        _FONT_BOLD = bold_name
    else:
        # 最终兜底：ReportLab 内置中文 CID 字体（无需字体文件）
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            _FONT_NAME = _FONT_BOLD = "STSong-Light"
        except Exception:
            _FONT_NAME = _FONT_BOLD = "Helvetica"

    _FONT_READY = True


# ---------------------------------------------------------------- 样式

def _styles() -> dict[str, ParagraphStyle]:
    ensure_font()
    f = _FONT_NAME
    common = {"fontName": f, "wordWrap": "CJK", "textColor": INK}
    return {
        "body": ParagraphStyle("Body", fontSize=10.5, leading=17, spaceAfter=6, **common),
        "h1": ParagraphStyle(
            "H1", fontSize=17, leading=26, spaceBefore=10, spaceAfter=10,
            textColor=PRIMARY_DARK, fontName=_FONT_BOLD, wordWrap="CJK",
        ),
        "h2": ParagraphStyle(
            "H2", fontSize=12.5, leading=19, spaceBefore=8, spaceAfter=4,
            textColor=PRIMARY, fontName=_FONT_BOLD, wordWrap="CJK",
        ),
        "quote": ParagraphStyle(
            "Quote", fontSize=9.5, leading=15, leftIndent=8,
            fontName=f, wordWrap="CJK", textColor=MUTED,
        ),
        "small": ParagraphStyle(
            "Small", fontSize=8.5, leading=13,
            fontName=f, wordWrap="CJK", textColor=MUTED,
        ),
        "bullet": ParagraphStyle(
            "Bullet", fontSize=10.5, leading=17, leftIndent=14, bulletIndent=4,
            spaceAfter=3, **common,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle", fontSize=30, leading=42, alignment=TA_CENTER,
            textColor=PRIMARY_DARK, fontName=_FONT_BOLD, wordWrap="CJK",
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub", fontSize=13, leading=22, alignment=TA_CENTER,
            fontName=f, wordWrap="CJK", textColor=INK,
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta", fontSize=10, leading=18, alignment=TA_CENTER,
            fontName=f, wordWrap="CJK", textColor=MUTED,
        ),
        "toc_title": ParagraphStyle(
            "TocTitle", fontSize=20, leading=28, alignment=TA_CENTER,
            textColor=PRIMARY_DARK, fontName=_FONT_BOLD, wordWrap="CJK",
            spaceAfter=16,
        ),
        "quad_title": ParagraphStyle(
            "QuadTitle", fontSize=11, leading=16, fontName=_FONT_BOLD, wordWrap="CJK",
        ),
        "quad_item": ParagraphStyle(
            "QuadItem", fontSize=8.8, leading=13, fontName=f, wordWrap="CJK", textColor=INK,
        ),
        "table_head": ParagraphStyle(
            "TableHead", fontSize=9.5, leading=14, fontName=_FONT_BOLD,
            textColor=WHITE, wordWrap="CJK",
        ),
        "table_cell": ParagraphStyle(
            "TableCell", fontSize=9.2, leading=14, fontName=f, wordWrap="CJK", textColor=INK,
        ),
        "quiz_q": ParagraphStyle(
            "QuizQ", fontSize=10.5, leading=17, fontName=_FONT_BOLD,
            textColor=INK, wordWrap="CJK", spaceBefore=6,
        ),
    }


# ---------------------------------------------------------------- 文档模板（TOC）

class _ReportDoc(BaseDocTemplate):
    """支持自动目录的文档模板。"""

    def __init__(self, filename: str, **kwargs):
        super().__init__(filename, **kwargs)
        frame = Frame(
            self.leftMargin, self.bottomMargin, self.width, self.height, id="normal"
        )
        self.addPageTemplates(
            [PageTemplate(id="main", frames=[frame], onPage=self._draw_footer)]
        )

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == "H1":
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page))

    def _draw_footer(self, canvas, doc):
        if doc.page <= 1:  # 封面不显示页脚
            return
        canvas.saveState()
        canvas.setFont(_FONT_NAME, 8)
        canvas.setFillColor(MUTED)
        canvas.drawCentredString(A4[0] / 2, 12 * mm, f"— 第 {doc.page} 页 —")
        canvas.restoreState()


# ---------------------------------------------------------------- 工具函数

def _esc(text) -> str:
    """转义 ReportLab Paragraph 的 HTML 特殊字符。"""
    return (
        str(text if text is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    """把纯文本转义后包成 Paragraph（支持简单的 **加粗**）。"""
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", _esc(text))
    return Paragraph(escaped, style)


def _stars(n: int) -> str:
    n = max(1, min(5, int(n or 3)))
    return "★" * n + "☆" * (5 - n)


def _section_h1(title: str) -> list:
    return [Spacer(1, 4 * mm), Paragraph(title, _styles()["h1"]),
            HRFlowable(width="100%", thickness=1.2, color=PRIMARY,
                       spaceBefore=2, spaceAfter=8)]


def _table(rows: list[list], col_widths: list, header: bool = True) -> Table:
    st = _styles()
    data = []
    for r_i, row in enumerate(rows):
        cells = []
        for cell in row:
            if isinstance(cell, Paragraph):
                cells.append(cell)
            else:
                style = st["table_head"] if (header and r_i == 0) else st["table_cell"]
                cells.append(Paragraph(_esc(cell), style))
        data.append(cells)

    table = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    cmds = [
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        cmds += [
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ]
    table.setStyle(TableStyle(cmds))
    return table


# ---------------------------------------------------------------- 各章节

def _cover(report: dict, sources: list[str], st: dict) -> list:
    story: list = []
    story.append(Spacer(1, 34 * mm))
    story.append(Paragraph("学 伴 学 习 报 告", st["cover_meta"]))
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="38%", thickness=2, color=PRIMARY, hAlign="CENTER"))
    story.append(Spacer(1, 10 * mm))
    title = (report.get("title") or "学习报告").strip()
    if len(title) > 30:
        title = title[:30] + "…"
    story.append(Paragraph(_esc(title), st["cover_title"]))
    story.append(Spacer(1, 8 * mm))

    if report.get("overview"):
        # 封面简介限长
        brief = report["overview"]
        if len(brief) > 120:
            brief = brief[:120] + "…"
        story.append(Paragraph(_esc(brief), st["cover_sub"]))

    story.append(Spacer(1, 20 * mm))
    src_line = "、".join(sources[:4]) + (" 等" if len(sources) > 4 else "")
    story.append(Paragraph(f"资料来源：{_esc(src_line)}", st["cover_meta"]))
    story.append(Paragraph(
        f"生成日期：{time.strftime('%Y 年 %m 月 %d 日')}", st["cover_meta"]))
    story.append(Spacer(1, 22 * mm))
    story.append(HRFlowable(width="30%", thickness=0.8, color=BORDER, hAlign="CENTER"))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("由 学伴 StudyPilot 生成 · AI 辅助整理，请结合原文核对", st["small"]))
    story.append(PageBreak())
    return story


def _toc(story: list, st: dict) -> None:
    from reportlab.platypus.tableofcontents import TableOfContents

    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOC0", fontName=_FONT_NAME, fontSize=12, leading=24,
            textColor=INK, leftIndent=0, firstLineIndent=0,
        ),
        ParagraphStyle(
            "TOC1", fontName=_FONT_NAME, fontSize=10, leading=20,
            textColor=MUTED, leftIndent=16, firstLineIndent=0,
        ),
    ]
    toc.dotsMinLevel = 0
    story.append(Paragraph("目  录", st["toc_title"]))
    story.append(toc)
    story.append(PageBreak())


def _overview(report: dict, st: dict) -> list:
    story = _section_h1("资料概述")
    if report.get("overview"):
        story.append(_p(report["overview"], st["body"]))
    if report.get("keywords"):
        kw = "  ·  ".join(report["keywords"][:12])
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(f"<b>关键词：</b>{_esc(kw)}", st["quote"]))
    return story


def _outline(report: dict, st: dict) -> list:
    story = _section_h1("知识大纲")
    items = report.get("outline") or []
    if not items:
        story.append(_p("（本次未生成大纲）", st["quote"]))
        return story
    for item in items:
        level = int(item.get("level") or 1)
        title = item.get("title") or ""
        summary = item.get("summary") or ""
        source = item.get("source") or ""
        if level <= 1:
            story.append(Paragraph(f"◆ {title}", st["h2"]))
        else:
            title_p = Paragraph(f"　• {title}", st["body"])
            story.append(title_p)
        meta_bits = []
        if summary:
            meta_bits.append(summary)
        if source:
            meta_bits.append(f"〔{source}〕")
        if meta_bits:
            story.append(_p("　" + "  ".join(meta_bits), st["quote"]))
    story.append(Spacer(1, 2 * mm))
    return story


def _highlights(report: dict, st: dict) -> list:
    story = _section_h1("核心重点")
    items = report.get("highlights") or []
    if not items:
        story.append(_p("（本次未生成重点）", st["quote"]))
        return story
    items = sorted(items, key=lambda x: -(x.get("importance") or 0))
    for i, item in enumerate(items, 1):
        stars = _stars(item.get("importance") or 3)
        source = item.get("source") or ""
        head = f"{i}. {_esc(item.get('title', ''))}"
        story.append(Paragraph(
            f"{head}　<font color='#B45309'>{stars}</font>"
            + (f"　<font color='#94A3B8' size='8.5'>〔{_esc(source)}〕</font>" if source else ""),
            st["h2"],
        ))
        if item.get("explain"):
            story.append(_p(item["explain"], st["body"]))
        if item.get("exam_tip"):
            story.append(_p(f"考法/面试：{item['exam_tip']}", st["quote"]))
        story.append(Spacer(1, 1.5 * mm))
    return story


def _study_methods(report: dict, st: dict) -> list:
    story = _section_h1("学习方法")
    items = report.get("study_methods") or []
    if not items:
        story.append(_p("（本次未生成学习方法）", st["quote"]))
        return story
    for item in items:
        story.append(Paragraph(f"▍{item.get('method', '')}", st["h2"]))
        if item.get("why"):
            story.append(_p(f"为什么适合：{item['why']}", st["body"]))
        if item.get("how"):
            story.append(_p(f"具体做法：{item['how']}", st["body"]))
        story.append(Spacer(1, 1.2 * mm))
    return story


def _review_plan(report: dict, st: dict) -> list:
    story = _section_h1("复习计划")
    plan = report.get("review_plan") or {}
    if plan.get("principles"):
        story.append(_p(plan["principles"], st["body"]))

    schedule = plan.get("schedule") or []
    if schedule:
        rows = [["时间", "复习重点", "具体任务"]]
        for s in schedule:
            rows.append([
                s.get("day") or "",
                s.get("focus") or "",
                "；".join(s.get("tasks") or []) or "—",
            ])
        story.append(Spacer(1, 2 * mm))
        story.append(_table(rows, [26 * mm, 55 * mm, 89 * mm]))

    routine = plan.get("daily_routine") or []
    if routine:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("每日建议", st["h2"]))
        for r in routine:
            story.append(Paragraph(f"• {r}", st["bullet"]))
    return story


def _career(report: dict, st: dict) -> list:
    story = _section_h1("就业价值与技能关联")
    career = report.get("career") or {}
    if career.get("roles"):
        story.append(Paragraph("对应岗位方向", st["h2"]))
        story.append(_p("、".join(career["roles"]), st["body"]))

    skills = career.get("skills") or []
    if skills:
        story.append(Paragraph("需要补齐的技能", st["h2"]))
        rows = [["技能", "为什么重要", "目标水平"]]
        for s in skills:
            rows.append([s.get("name") or "", s.get("why") or "", s.get("level") or ""])
        story.append(_table(rows, [45 * mm, 90 * mm, 35 * mm]))

    topics = career.get("interview_topics") or []
    if topics:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("面试高频考点", st["h2"]))
        for t in topics:
            story.append(Paragraph(f"• {t}", st["bullet"]))

    note = career.get("note") or ""
    story.append(Spacer(1, 3 * mm))
    story.append(_p(note or "就业与薪资信息为 AI 基于公开常识的推断，仅供参考。", st["quote"]))
    return story


def _quadrant_table(report: dict, st: dict) -> Table:
    priority = report.get("priority") or {}
    blocks: list = []
    for key in ("urgent_important", "important_not_urgent",
                "urgent_not_important", "not_important"):
        bg_hex, title_hex, title, subtitle = QUAD_COLORS[key]
        items = priority.get(key) or []
        block: list = [
            Paragraph(
                f"{title}<br/><font size='8' color='{title_hex}'>{subtitle}</font>",
                ParagraphStyle("QT", parent=st["quad_title"], textColor=colors.HexColor(title_hex)),
            ),
            Spacer(1, 1.5 * mm),
        ]
        if not items:
            block.append(Paragraph("（暂无）", st["small"]))
        for it in items[:6]:
            reason = _esc(it.get("reason") or "")
            text = f"• <b>{_esc(it.get('item', ''))}</b>"
            if reason:
                text += f"：{reason}"
            block.append(Paragraph(text, st["quad_item"]))
            block.append(Spacer(1, 1 * mm))
        if len(items) > 6:
            block.append(Paragraph(f"… 另有 {len(items) - 6} 项", st["small"]))
        blocks.append(block)

    grid = [[blocks[0], blocks[1]], [blocks[2], blocks[3]]]
    bg = [
        colors.HexColor(QUAD_COLORS["urgent_important"][0]),
        colors.HexColor(QUAD_COLORS["important_not_urgent"][0]),
        colors.HexColor(QUAD_COLORS["urgent_not_important"][0]),
        colors.HexColor(QUAD_COLORS["not_important"][0]),
    ]
    table = Table(grid, colWidths=[85 * mm, 85 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), bg[0]),
        ("BACKGROUND", (1, 0), (1, 0), bg[1]),
        ("BACKGROUND", (0, 1), (0, 1), bg[2]),
        ("BACKGROUND", (1, 1), (1, 1), bg[3]),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def _priority(report: dict, st: dict) -> list:
    story = _section_h1("轻重缓急")
    advice = (report.get("priority") or {}).get("advice")
    if advice:
        story.append(_p(advice, st["body"]))
        story.append(Spacer(1, 2 * mm))
    story.append(_quadrant_table(report, st))
    return story


def _quiz(report: dict, st: dict) -> list:
    items = report.get("quiz") or []
    if not items:
        return []
    story = _section_h1("自测题")
    for i, item in enumerate(items, 1):
        story.append(Paragraph(f"{i}. {_esc(item.get('q', ''))}", st["quiz_q"]))
        options = item.get("options") or []
        for j, opt in enumerate(options):
            letter = "ABCDEFGH"[j] if j < 8 else str(j + 1)
            text = str(opt)
            if not re.match(r"^[A-Za-z][.、．)]", text):
                text = f"{letter}. {text}"
            story.append(Paragraph(f"　　{_esc(text)}", st["body"]))
        if item.get("answer"):
            story.append(Paragraph(f"　　<b>答案：{_esc(item['answer'])}</b>", st["body"]))
        if item.get("explain"):
            story.append(_p(f"　　解析：{item['explain']}", st["quote"]))
        story.append(Spacer(1, 2 * mm))
    return story


def _keywords(report: dict, st: dict) -> list:
    kws = report.get("keywords") or []
    if not kws:
        return []
    story = _section_h1("附录：关键词")
    story.append(_p("、".join(kws), st["body"]))
    return story


# ---------------------------------------------------------------- 入口

def safe_filename(text: str, fallback: str = "学伴报告") -> str:
    text = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", text or "").strip(" ._")
    text = text[:60] or fallback
    return text


def build_report(
    report: dict,
    sources: list[str],
    out_path: str | Path,
) -> str:
    """生成 PDF，返回文件路径。"""
    ensure_font()
    st = _styles()
    out_path = str(out_path)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    doc = _ReportDoc(
        out_path,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title=report.get("title") or "学伴学习报告",
        author="学伴 StudyPilot",
        subject="AI 学习资料总结报告",
        creator="学伴 StudyPilot",
    )

    story: list = []
    story += _cover(report, sources, st)
    _toc(story, st)
    story += _overview(report, st)
    story += _outline(report, st)
    story += _highlights(report, st)
    story += _study_methods(report, st)
    story += _review_plan(report, st)
    story += _career(report, st)
    story += _priority(report, st)
    story += _quiz(report, st)
    story += _keywords(report, st)

    doc.multiBuild(story)
    return out_path
