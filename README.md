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

## 桌面查询应用（Tauri 单窗口）

`desktop/` 下是用 Tauri 2 + React + TypeScript 重构的单窗口桌面前端，替代了原先浏览器里的 index.html。窗口启动时自动拉起 Python 检索后端（kb_server.py），关闭窗口时自动结束该进程；点击结果用系统默认程序打开 PDF 或中文译文 Markdown，不再走浏览器内联。

前置依赖：

- Python 及依赖（fastapi、uvicorn、faiss、numpy 等，见 requirements.txt）
- Rust 工具链（rustc / cargo）
- Windows 自带的 WebView2 运行时

开发运行（自动起后端并打开窗口）：

```
cd desktop
npm install --include=dev
npm run tauri dev
```

打包为可执行文件 / 安装包：

```
cd desktop
npm run tauri build
```

说明：

- 检索引擎仍是 Python（FAISS 向量检索 + embedding）；桌面壳只负责自动启动它、提供原生窗口与系统默认程序打开文件的能力。
- 若 python 不在 PATH，壳会依次尝试 python / python3 / E:\soft\Anaconda\python.exe；也可用环境变量 KB_PYTHON 指定解释器。
- 后端默认监听 127.0.0.1:8000，仅本机可访问。

## 提示词管理

- prompt.json 统一保存提示词
- prompt_store.py 负责加载与多行模板拼接
- summarize.py 第二步会把摘要译文与原文一起送入模型，提升结构化输出稳定性
