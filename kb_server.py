import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from search import build_query, clean_snippet, load_meta, parse_keywords, search_kb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))          # data lives one level up
KB_DIR = os.path.join(ROOT, "kb_store")
API_KEY = os.path.join(ROOT, "API_KEY.json")

app = FastAPI(title="KB Search")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def is_inside_root(target):
    # case-/separator-insensitive guard (fixes false 403 on Windows)
    t, r = os.path.normcase(os.path.abspath(target)), os.path.normcase(ROOT)
    return t == r or t.startswith(r + os.sep)


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


@app.get("/open")
def open_file(path: str = Query(...)):
    target = os.path.abspath(path)
    if not is_inside_root(target):
        raise HTTPException(403, "path outside allowed root")
    if not os.path.isfile(target):
        raise HTTPException(404, "file not found")
    media = "text/plain; charset=utf-8" if target.lower().endswith((".md", ".txt")) else None
    return FileResponse(target, media_type=media, content_disposition_type="inline")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
