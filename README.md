# Trending Fetcher and Summarizer

项目用于每日抓取 GitHub Trending 与 HuggingFace Daily Papers，按日期归档，并生成论文摘要与中文翻译。

## 功能

- 获取 GitHub Trending 仓库列表并下载 README
- 获取 HuggingFace Daily Papers 元数据并下载论文 PDF
- summarize.py 先生成摘要译文，再生成结构化摘要，写入同名 _summary.md
- README 中文翻译，优先使用大模型，失败时改用 Google 翻译
- best.py 从当日摘要中选择 LLM 方向论文，保存选择记录并下载 arXiv 源码
- createbase.py 与 baseall.py 构建离线知识库，search.py 查询

## 目录产出

- YYYY-MM-DD/GitHub/仓库名/README.md 与 README_zh.md
- YYYY-MM-DD/HuggingFace/论文标题_id.pdf 与 论文标题_id_summary.md
- YYYY-MM-DD/HuggingFace/llm_paper_selection.json 与 *_source.tar.gz
- kb_store 下保存向量索引与文档库
- kb_store/chunk_store.sqlite3 保存可恢复的 chunk 权威副本
- kb_store/embedding_cache_<model>.sqlite3 保存可复用的 embedding 向量缓存

## 使用方法

### 安装依赖

```
pip install -r requirements.txt
```

### 配置 API_KEY.json

- Summary_Models 用于摘要生成与论文筛选
- Embedding_Model 用于向量检索
- Reranker_Model 用于重排
- Base_URL 需填写完整 endpoint，供应商要求 /v1 时直接写入
- 可选字段包括 Timeout、Concurrency、Batch_Size、Max_Retries、Verify_SSL

### 运行流程

```
python main.py
python summarize.py
python best.py
```

### 离线知识库

```
python createbase.py --source 2026-05-30 --kb-dir kb_store --api API_KEY.json
python baseall.py --root . --kb-dir kb_store --api API_KEY.json
python search.py llm,agent --top 10 --kb-dir kb_store --api API_KEY.json --mode auto
```

知识库恢复说明：`vectors.faiss` 是可重建的派生索引。索引丢失或数量不一致时，构建器会优先从本地 embedding 缓存恢复，只对缓存缺失的 chunk 调用 embedding 服务；`doc_store.jsonl` 损坏时会从 `chunk_store.sqlite3` 恢复。首次升级到该恢复机制时，会从现有 FAISS 索引本地回填缓存，不会重复请求已有向量。

## 桌面查询应用（Tauri 单窗口）

`desktop/` 下是用 Tauri 2 + React + TypeScript 构建的单窗口桌面前端。窗口启动时会自动拉起本地 Python 后端，关闭窗口时自动结束该进程；点击结果会用系统默认程序打开 PDF、摘要译文或 README。

开发态会优先使用源码里的 `kb_server.py`。打包态会优先使用 PyInstaller 生成的 `dist/kb_server_pack/kb_server_pack.exe`，因此安装版不要求用户预先安装 Python。

桌面端现在是一个工作台：

- Main 下载：运行 arXiv 历史刷新、GitHub Trending、HuggingFace Daily Papers PDF 下载，并显示 PDF 字节进度。
- Summarize：运行 PDF 摘要、README 翻译，并显示模型探测、队列进度和实时日志。
- 知识库：保留原有 `/meta`、`/search` 检索接口，支持手动触发当天目录增量建库。
- 顶部状态栏会按页面显示 HTTPS 代理、Summary 模型或知识库 embedding/vectors 信息。
- Main 会统计当天已下载 arXiv PDF 数量，避免重复运行时超过每日下载上限。

前置依赖：

- 开发运行：Python 及依赖、Node.js、Rust 工具链、Windows WebView2 运行时
- 打包安装版：用户机器只需要 Windows WebView2 运行时；Python 后端已内置在安装包中

开发运行（自动起后端并打开窗口）：

```
cd desktop
npm install --include=dev
npm run tauri dev
```

轻量开发运行（Rust target 放入临时目录，退出后清理）：

```
cd desktop
npm run tauri:dev:light
```

### 打包 Windows 安装包

先用隔离 venv 打包 Python 后端，避免把 Anaconda、torch、transformers 等无关大包带进去：

```
cd E:\DL\EssaysHere\trending_fetcher
E:\soft\Anaconda\python.exe -m venv .venv-pack
.\.venv-pack\Scripts\python.exe -m pip install --upgrade pip
.\.venv-pack\Scripts\pip.exe install -r requirements-pack.txt
.\.venv-pack\Scripts\pyinstaller.exe --noconfirm --onedir --name kb_server_pack --add-data "prompt.json;." --hidden-import main --hidden-import summarize --hidden-import createbase --hidden-import update_arxiv_history --hidden-import search --hidden-import model_client --hidden-import prompt_store --hidden-import Gtranslate --hidden-import best --hidden-import baseall .\kb_server.py
```

再打 Tauri 安装包：

```
cd E:\DL\EssaysHere\trending_fetcher\desktop
$env:CARGO_TARGET_DIR="$env:LOCALAPPDATA\trending_fetcher\tauri-target\target"
.\node_modules\.bin\tauri.cmd build --bundles nsis
```

当前构建产物：

```
E:\DL\EssaysHere\trending_fetcher\dist\KB Search_0.1.0_x64-setup.exe
```

本次完整包体积约 44 MB，内置 Python 后端目录约 163 MB。Rust/Tauri release 构建缓存位于 `%LOCALAPPDATA%\trending_fetcher\tauri-target\target`，可能超过 1GB，但不会进入安装包。

说明：

- 检索引擎仍是 Python（FAISS 向量检索 + embedding）；桌面壳只负责自动启动它、提供原生窗口与系统默认程序打开文件的能力。
- 打包态优先启动内置 `kb_server_pack.exe`；开发态找不到内置后端时，壳会依次尝试 `KB_PYTHON`、python、python3、`E:\soft\Anaconda\python.exe`。
- 后端默认监听 127.0.0.1:8000，仅本机可访问。
- 数据根目录由 `TRENDING_FETCHER_DATA_DIR` 控制；开发态默认是仓库上一级目录，打包态默认是应用本地数据目录。
- 安装版默认数据目录类似 `%LOCALAPPDATA%\com.trendingfetcher.kbsearch\data`。`API_KEY.json`、日期目录、PDF、`kb_store` 不会被打进安装包，需要放在数据目录或通过环境变量指定。
- `requirements-pack.txt` 是打包后端用的最小依赖清单；`requirements.txt` 是源码运行依赖清单。

## 提示词管理

- prompt.json 统一保存提示词
- prompt_store.py 负责加载与多行模板拼接
- summarize.py 第二步会把摘要译文与原文一起送入模型，提升结构化输出稳定性
