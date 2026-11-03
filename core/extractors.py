"""文件解析：把 PDF / PPTX / DOCX / TXT / XLSX 提取成保留层级结构的文本。

输出统一使用 Markdown 风格标题（# / ##）与页码标记，
方便后续 AI 识别章节结构、生成大纲并标注出处。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

DOC_EXTENSIONS = {
    ".pdf",
    ".pptx",
    ".docx",
    ".txt",
    ".md",
    ".markdown",
    ".xlsx",
}

LEGACY_EXTENSIONS = {".ppt", ".doc"}

MEDIA_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
    ".flv",
    ".mp3",
    ".wav",
    ".m4a",
    ".flac",
    ".ogg",
    ".aac",
    ".wma",
    ".opus",
}


@dataclass
class ExtractedDoc:
    """一个文件的解析结果。"""

    name: str
    kind: str  # pdf / pptx / docx / text / xlsx / media / unknown
    text: str
    pages: int = 0
    warnings: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def chars(self) -> int:
        return len(self.text)


def kind_for(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".pptx":
        return "pptx"
    if ext == ".ppt":
        return "ppt-legacy"
    if ext == ".docx":
        return "docx"
    if ext == ".doc":
        return "doc-legacy"
    if ext in (".txt", ".md", ".markdown"):
        return "text"
    if ext in (".xlsx", ".xls"):
        return "xlsx"
    if ext in MEDIA_EXTENSIONS:
        return "media"
    return "unknown"


def is_media(name: str) -> bool:
    return kind_for(name) == "media"


def extract(path: str | Path, name: str | None = None) -> ExtractedDoc:
    """按扩展名分派解析。媒体文件不在这里处理（见 transcribe.py）。"""
    path = Path(path)
    name = name or path.name
    kind = kind_for(name)
    try:
        if kind == "pdf":
            return _extract_pdf(path, name)
        if kind == "pptx":
            return _extract_pptx(path, name)
        if kind == "docx":
            return _extract_docx(path, name)
        if kind == "text":
            return _extract_text(path, name)
        if kind == "xlsx":
            return _extract_xlsx(path, name)
        if kind in ("ppt-legacy", "doc-legacy"):
            raise ValueError(
                f"暂不支持旧版 .{name.rsplit('.', 1)[-1]} 格式，请用 Office/WPS 另存为 .pptx 或 .docx 后再试。"
            )
        if kind == "media":
            raise ValueError("媒体文件请交给语音转写模块处理。")
        raise ValueError(f"不支持的文件格式：{name}")
    except ValueError:
        raise
    except Exception as exc:  # 解析失败要给出可读原因
        raise ValueError(f"解析「{name}」失败：{exc}") from exc


# ---------------------------------------------------------------- 文本清洗

def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join(lines).strip()


# ---------------------------------------------------------------- PDF

def _extract_pdf(path: Path, name: str) -> ExtractedDoc:
    import pymupdf  # PyMuPDF

    warnings: list[str] = []
    parts: list[str] = []
    total_chars = 0

    with pymupdf.open(str(path)) as doc:
        pages = doc.page_count
        for i in range(pages):
            page = doc.load_page(i)
            text = _clean_text(page.get_text("text") or "")
            total_chars += len(text)
            if text:
                parts.append(f"\n\n<!-- 第 {i + 1} 页 -->\n{text}")

    if pages > 0 and total_chars < 80:
        warnings.append(
            "该 PDF 几乎没有可提取的文字，可能是扫描件（图片型 PDF）。建议使用文字版 PDF，或先做 OCR 再上传。"
        )

    text = "\n".join(parts).strip()
    return ExtractedDoc(
        name=name,
        kind="pdf",
        text=text,
        pages=pages,
        warnings=warnings,
    )


# ---------------------------------------------------------------- PPTX

def _extract_pptx(path: Path, name: str) -> ExtractedDoc:
    from pptx import Presentation

    prs = Presentation(str(path))
    warnings: list[str] = []
    parts: list[str] = []

    for idx, slide in enumerate(prs.slides, 1):
        block: list[str] = []
        # 标题单独强调
        title = ""
        try:
            if slide.shapes.title is not None:
                title = _shape_text(slide.shapes.title).strip()
        except Exception:
            title = ""

        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            text = _shape_text(shape).strip()
            if text and text != title:
                block.append(text)

        # 表格
        for shape in slide.shapes:
            if getattr(shape, "has_table", False):
                block.append(_table_to_text(shape.table))

        # 备注
        try:
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    block.append(f"[备注] {notes}")
        except Exception:
            pass

        if title or block:
            head = f"## 第 {idx} 页" + (f"：{title}" if title else "")
            parts.append(head + "\n" + "\n".join(block))

    if not parts:
        warnings.append("未能从 PPT 中提取到文字，请确认文件不是纯图片。")

    return ExtractedDoc(name=name, kind="pptx", text="\n\n".join(parts).strip(), pages=len(prs.slides), warnings=warnings)


def _shape_text(shape) -> str:
    """提取一个形状内所有段落的文字。"""
    try:
        tf = shape.text_frame
    except Exception:
        return ""
    lines: list[str] = []
    for para in tf.paragraphs:
        text = "".join(run.text for run in para.runs).strip()
        if not text:
            text = (para.text or "").strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _table_to_text(table) -> str:
    rows: list[str] = []
    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            value = (cell.text or "").replace("\n", " ").strip()
            cells.append(value)
        rows.append(" | ".join(cells))
    return "\n".join(rows)


# ---------------------------------------------------------------- DOCX

def _extract_docx(path: Path, name: str) -> ExtractedDoc:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    parts: list[str] = []
    body = doc.element.body

    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            para = Paragraph(child, doc)
            text = (para.text or "").strip()
            if not text:
                continue
            style = (para.style.name or "").lower() if para.style else ""
            if style.startswith("heading"):
                level = 1
                m = re.search(r"(\d+)", style)
                if m:
                    level = min(6, max(1, int(m.group(1))))
                parts.append(f"\n{'#' * level} {text}")
            elif style.startswith("title"):
                parts.append(f"\n# {text}")
            else:
                parts.append(text)
        elif child.tag == qn("w:tbl"):
            table = Table(child, doc)
            parts.append("\n" + _table_to_text(table))

    text = _clean_text("\n".join(parts))
    return ExtractedDoc(name=name, kind="docx", text=text, pages=0)


# ---------------------------------------------------------------- TXT / MD

def _read_text_auto(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    try:
        import chardet

        detected = chardet.detect(raw)
        encoding = detected.get("encoding")
        if encoding:
            return raw.decode(encoding, errors="replace")
    except Exception:
        pass
    return raw.decode("utf-8", errors="replace")


def _extract_text(path: Path, name: str) -> ExtractedDoc:
    text = _clean_text(_read_text_auto(path))
    return ExtractedDoc(name=name, kind="text", text=text)


# ---------------------------------------------------------------- XLSX

def _extract_xlsx(path: Path, name: str) -> ExtractedDoc:
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    parts: list[str] = []
    try:
        for sheet in wb.worksheets:
            parts.append(f"\n## 工作表：{sheet.title}")
            row_count = 0
            for row in sheet.iter_rows(values_only=True):
                values = ["" if v is None else str(v).replace("\n", " ").strip() for v in row]
                if not any(values):
                    continue
                parts.append(" | ".join(values))
                row_count += 1
                if row_count >= 2000:  # 防止超大表格撑爆
                    parts.append("…（表格过长，已截断）")
                    break
    finally:
        wb.close()

    text = _clean_text("\n".join(parts))
    return ExtractedDoc(name=name, kind="xlsx", text=text)
