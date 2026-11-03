# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir 模式，启动快、杀软误报少）。

构建：
    .venv\\Scripts\\python.exe -m PyInstaller study-pilot.spec --noconfirm
产物：
    dist/StudyPilot/StudyPilot.exe
"""

import PyInstaller.utils.hooks as hooks

hiddenimports = []

# 这些包的子模块大量是动态导入，需要显式收集
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers"):
    try:
        hiddenimports += hooks.collect_submodules(pkg)
    except Exception:
        pass

hiddenimports += [
    "flask",
    "werkzeug",
    "jinja2",
    "click",
    "itsdangerous",
    "markupsafe",
    "openai",
    "httpx",
    "httpcore",
    "pydantic",
    "anyio",
    "h11",
    "certifi",
    "reportlab",
    "reportlab.pdfbase.ttfonts",
    "reportlab.pdfbase._fontdata",
    "pymupdf",
    "pptx",
    "docx",
    "openpyxl",
    "chardet",
    "chardet.universaldetector",
]

datas = [("web", "web")]

# 收集包内非 Python 资源（PyMuPDF 的 layout/onnx 资源、faster-whisper 的 VAD 模型等）
for pkg in ("pymupdf", "faster_whisper"):
    try:
        datas += hooks.collect_data_files(pkg)
    except Exception:
        pass

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排除明显用不到的大包
    excludes=[
        "tkinter",
        "matplotlib",
        "pandas",
        "scipy",
        "IPython",
        "jupyter",
        "pytest",
        "notebook",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StudyPilot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # 保留控制台便于查看启动地址与错误
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="StudyPilot",
)
