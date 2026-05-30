# Trending Fetcher & Summarizer

项目抓取每日GitHub Trending与HuggingFace论文，按日期归档。运行：安装依赖，配置API_KEY.json，依次执行python main.py和python summarize.py。

## API_KEY.json

- Embedding_Model 与 Reranker_Model 的 Base_URL 必须填写完整可用的 endpoint。
- 如果供应商要求 /v1，请直接把 /v1 写进 Base_URL，本项目不会自动追加。

## Offline KB

- createbase.py: 对指定目录构建离线向量库与文档库。
- baseall.py: 扫描全部日期目录，将缺失文档补进知识库。
