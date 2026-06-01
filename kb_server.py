import os

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from search import build_query, clean_snippet, load_meta, parse_keywords, search_kb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))          # data lives one level up
KB_DIR = os.path.join(ROOT, "kb_store")
API_KEY = os.path.join(ROOT, "API_KEY.json")

app = FastAPI(title="KB Search")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/meta")
def meta():
    m = load_meta(os.path.join(KB_DIR, "index_meta.json")) or {}
    return {
        "embedding_model": m.get("embedding_model"),
        "dimension": m.get("dimension"),
        "total_vectors": m.get("total_vectors"),
    }


@app.get("/search")
def search(q: str = Query(""), mode: str = Query("auto"), top: int = Query(10)):
    keywords = parse_keywords(q)
    results = search_kb(build_query(q), keywords, KB_DIR, API_KEY, top, mode)
    for item in results:
        item["snippet"] = clean_snippet(item["record"].get("text", ""))
    return {"keywords": keywords, "mode": mode, "results": results}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
