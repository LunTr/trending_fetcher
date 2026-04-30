# Trending Fetcher & Summarizer

本项目自动抓取并用 AI 总结每日科技前沿。

- `main.py`：抓取 GitHub Trending Top5 项目代码库及 HuggingFace 每日论文，按日期归档。
- `summarize.py`：调用 LLM 将论文生成中文简报，并翻译 README。

**使用方法**：
1. `pip install -r requirements.txt`
2. 配置外层 `API_KEY.json`
3. 依次运行 `python main.py` 和 `python summarize.py`
