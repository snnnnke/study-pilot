# 学伴 StudyPilot

> 把学习资料变成一份能直接照着学的 PDF 报告。Windows 免安装，双击即用。

**学伴**是一个本地运行的 AI 学习资料总结工具。把课程 **PPT / PDF / Word / 视频 / 音频** 拖进来，它会在你的电脑上完成解析、转写，再调用你配置的 AI 接口，生成一份结构化 **PDF 学习报告**：

- 📖 **知识大纲** —— 整份资料的知识骨架，标注页码 / 时间戳
- 🔥 **核心重点** —— 按重要度排序，含解释、出处、常见考法
- 🧠 **学习方法** —— 针对这份资料该用什么方法学、按什么顺序学
- 📅 **复习计划** —— 1/3/7/15/30 天间隔重复表 + 每日任务
- 💼 **就业价值** —— 对应岗位、需要补齐的技能、面试高频考点
- 🎯 **轻重缓急** —— 重要紧急四象限，告诉你先学什么、什么可以跳过

---

## 快速开始

### 方式一：直接使用（推荐给普通用户）

1. 打开 [Releases](../../releases) 页面，下载最新 `StudyPilot-win64.zip`
2. 解压到任意目录（例如 `D:\StudyPilot`）
3. 双击 `StudyPilot.exe`
4. 浏览器会自动打开本地页面（首次使用请先在右上角「设置」里填写 AI 接口信息）
5. 拖入学习资料 → 选择报告档位 → 开始生成 → 下载 PDF

> 首次启动会在控制台窗口显示访问地址；关闭该窗口即退出程序。

### 方式二：从源码运行（开发者）

需要 Python 3.11 / 3.12。

```bash
git clone https://github.com/snnnnke/study-pilot
cd study-pilot

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

# 启动
python app.py
```

---

## 配置 AI 接口

软件本身不包含 AI，需要你使用任意 **OpenAI 兼容** 的接口。点击右上角 **设置**，填写：

| 字段 | 说明 |
|---|---|
| 服务商 | 内置 DeepSeek / 硅基流动 / 通义千问 / 智谱 / Moonshot / OpenAI / Ollama / LM Studio，也可选「自定义」 |
| 接口地址 | 例如 `https://api.deepseek.com/v1` |
| 模型 | 例如 `deepseek-chat` |
| API Key | 本地使用 Windows DPAPI 加密保存；Ollama / LM Studio 可留空 |

点击「测试连接」确认可用后保存。**API Key 只保存在本机，不会上传到任何第三方。**

> 推荐 DeepSeek：国内直连、中文效果好、一份报告通常只要几毛钱。

### 完全离线（可选）

- **AI**：安装 [Ollama](https://ollama.com/)，拉一个模型（如 `ollama pull qwen2.5:7b`），服务商选 Ollama。
- **语音转写**：默认就是本地 faster-whisper，不需要联网。
- **提前下载模型（受限网络 / 离线机器）**：

```bash
python scripts/fetch_model.py small          # 下载到 .data/models-small
# 或指定目录
python scripts/fetch_model.py tiny D:\models\whisper-tiny
```

下载完成后，把模型目录路径填到「设置 → 语音转写 → 本地模型目录」即可离线使用。
也可以直接设置环境变量 `HF_ENDPOINT` 切换模型下载源（默认 `https://hf-mirror.com`）。

---

## 本地语音转写（faster-whisper）

音视频文件会在本机用 faster-whisper 转成文字，**不上传云端**。

- 首次使用某个模型时会自动下载到 `%LOCALAPPDATA%\StudyPilot\models`，默认走 `hf-mirror.com` 镜像。
- 模型大小与占用（CPU 推理）：

| 模型 | 体积 | 说明 |
|---|---|---|
| tiny | ~75 MB | 最快，精度一般 |
| base | ~145 MB | 快速 |
| small | ~466 MB | **默认，平衡** |
| medium | ~1.5 GB | 精度更高，较慢 |
| large-v3 | ~3.1 GB | 最高精度，很慢 |

- CPU 推理速度约为音频时长的 0.5～2 倍（取决于 CPU）。若电脑有 NVIDIA 显卡并配置好 CUDA，会自动启用 GPU 加速。
- 可在 `.env` / 系统环境变量中设置 `HF_ENDPOINT` 切换模型下载源。

---

## 支持的文件格式

| 类型 | 格式 |
|---|---|
| 文档 | `.pdf` `.docx` `.pptx` `.txt` `.md` `.xlsx` |
| 音视频 | `.mp4` `.mkv` `.mov` `.avi` `.webm` `.mp3` `.wav` `.m4a` `.flac` `.ogg` `.aac` `.wma` `.opus` |

> 旧版 `.ppt` / `.doc` 请先用 Office / WPS 另存为 `.pptx` / `.docx`。
> 扫描版（图片型）PDF 暂不支持 OCR，建议使用文字版 PDF。

---

## 报告档位

| 档位 | 特点 | 大致耗时 |
|---|---|---|
| 快速 | 精简，优先核心概念 | 1～3 分钟 |
| 标准 | 平衡深度与篇幅（默认） | 3～8 分钟 |
| 深度 | 最详细，含更多重点与自测题 | 8～20 分钟 |

耗时取决于资料长度、模型速度和接口响应。

---

## 数据与隐私

- 所有文件解析、PDF 生成都在**本机**完成。
- 只有提取出的**文本片段**会发送到你配置的 AI 接口用于总结。
- 语音转写完全在本地完成，音频不会上传。
- API Key 使用 Windows DPAPI 加密存储。
- 上传的原始文件与生成的报告默认保存在 `%LOCALAPPDATA%\StudyPilot`，可在「历史记录」中删除。

---

## 打包发布

```bash
.venv\Scripts\python.exe build.py
```

会生成 `dist/StudyPilot/StudyPilot.exe` 和 `StudyPilot-win64.zip`。

也可以直接推一个 `v*` 标签，GitHub Actions 会自动在 Windows 上构建并发布 Release：

```bash
git tag v1.0.0
git push origin v1.0.0
```

> 由于内置本地语音转写（faster-whisper + ctranslate2 + onnxruntime），完整包体积约 150–300 MB（视压缩率而定）。

---

## 项目结构

```
study-pilot/
├── app.py                  # 启动入口：Flask 本地服务 + 自动打开浏览器
├── core/
│   ├── config.py           # 配置、服务商预设、API Key 加密
│   ├── extractors.py       # PDF / PPTX / DOCX / TXT / XLSX 解析
│   ├── transcribe.py       # 本地 faster-whisper 语音转写
│   ├── llm.py              # OpenAI 兼容客户端 + Map-Reduce 总结
│   ├── prompts.py          # 提示词模板
│   ├── report.py           # ReportLab PDF 排版生成
│   ├── pipeline.py         # 任务流水线
│   ├── store.py            # 任务状态存储
│   ├── errors.py           # 异常类型
│   └── paths.py            # 路径管理（兼容打包运行）
├── web/                    # 前端（原生 HTML/CSS/JS，零构建）
├── scripts/
│   ├── check_env.py        # 依赖自检
│   ├── smoke_test.py       # 离线冒烟测试（Mock 模式）
│   └── api_test.py         # 接口测试
├── build.py                # 一键打包
├── study-pilot.spec        # PyInstaller 配置
├── requirements.txt
└── docs/方案.md            # 项目方案
```

---

## 常见问题

**Q：双击 exe 后浏览器没打开？**
控制台窗口里会显示地址（如 `http://127.0.0.1:8765`），手动复制到浏览器打开即可。

**Q：提示「API Key 无效」？**
到对应服务商控制台确认 Key 是否正确、是否还有余额；Ollama / LM Studio 不需要 Key。

**Q：音视频转写很慢？**
CPU 推理属于正常现象。可以先换 `small` 或 `base` 模型；有 NVIDIA 显卡时会自动使用 GPU。

**Q：扫描版 PDF 生成的报告是空的？**
当前版本不支持 OCR，请使用文字版 PDF，或先对扫描件做 OCR。

**Q：报告内容和原文对不上？**
AI 总结可能出错，报告封面已注明「请结合原文核对」。可在设置里换一个更强的模型，或选择「深度」档位。

---


> 免责声明：AI 生成的就业方向、薪资等信息基于公开常识的推断，仅供参考，请以实际招聘信息为准。
