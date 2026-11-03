import importlib

mods = [
    "flask", "fitz", "pptx", "docx", "openpyxl", "reportlab",
    "openai", "chardet", "faster_whisper", "ctranslate2", "av",
    "onnxruntime", "tokenizers",
]
for m in mods:
    try:
        mod = importlib.import_module(m)
        print(f"{m:18s} OK   {getattr(mod, '__version__', '')}")
    except Exception as e:
        print(f"{m:18s} FAIL {type(e).__name__}: {e}")
