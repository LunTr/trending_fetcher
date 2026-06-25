import argparse
import heapq
import json
import os
import re

from model_client import ModelClient

DEFAULT_KB_DIR = os.path.join(os.getcwd(), "kb_store")
DEFAULT_API_KEY_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "API_KEY.json")
)
DEFAULT_TOP_K = 10


def parse_keywords(raw):
    raw = (raw or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def build_query(raw):
    keywords = parse_keywords(raw)
    if not keywords:
        return ""
    return " ".join(keywords)


def normalize_vectors(vectors, np):
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def load_meta(meta_path):
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_records_by_ids(doc_store_path, target_ids):
    records = {}
    if not target_ids or not os.path.exists(doc_store_path):
        return records

    with open(doc_store_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            vector_id = record.get("vector_id")
            if vector_id in target_ids:
                records[vector_id] = record
                if len(records) == len(target_ids):
                    break
    return records


def clean_snippet(text, max_chars=260):
    if not text:
        return ""
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + "..."


def keyword_score(text, keywords):
    if not text or not keywords:
        return 0
    lowered = text.lower()
    return sum(lowered.count(k.lower()) for k in keywords)


def keyword_search(doc_store_path, keywords, top_k):
    if not keywords:
        print("[!] Empty keywords.")
        return []
    if not os.path.exists(doc_store_path):
        print(f"[!] Missing doc store: {doc_store_path}")
        return []

    heap = []
    idx = 0
    with open(doc_store_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            title = record.get("title") or ""
            file_name = record.get("file_name") or ""
            text = record.get("text") or ""
            haystack = f"{title}\n{file_name}\n{text}"
            score = keyword_score(haystack, keywords)
            if score <= 0:
                continue
            entry = (score, idx, record)
            idx += 1
            if len(heap) < top_k:
                heapq.heappush(heap, entry)
            else:
                if entry > heap[0]:
                    heapq.heapreplace(heap, entry)

    if not heap:
        return []
    ranked = sorted(heap, key=lambda item: item[0], reverse=True)
    results = []
    for rank, (score, _, record) in enumerate(ranked, 1):
        results.append({
            "rank": rank,
            "score": float(score),
            "record": record,
        })
    return results


def search_kb(query, keywords, kb_dir, api_key_path, top_k, mode="auto"):
    if mode not in {"auto", "vector", "keyword"}:
        print("[!] Invalid mode. Use auto, vector, or keyword.")
        return []
    if mode == "keyword":
        doc_store_path = os.path.join(kb_dir, "doc_store.jsonl")
        return keyword_search(doc_store_path, keywords, top_k)

    try:
        import numpy as np
    except Exception:
        print("[!] Missing dependency: numpy. Install it before running search.")
        return []

    try:
        import faiss
    except Exception:
        print("[!] Missing dependency: faiss-cpu. Install it before running search.")
        return []

    if not query:
        print("[!] Empty query.")
        return []

    index_path = os.path.join(kb_dir, "vectors.faiss")
    meta_path = os.path.join(kb_dir, "index_meta.json")
    doc_store_path = os.path.join(kb_dir, "doc_store.jsonl")

    if not os.path.exists(index_path):
        print(f"[!] Missing index: {index_path}")
        return []

    meta = load_meta(meta_path)
    if not meta:
        print(f"[!] Missing index meta: {meta_path}")
        return []

    model_client = ModelClient.from_config_path(api_key_path)
    embed_model = model_client.embedding_conf.get("model")
    if not embed_model:
        print("[!] Embedding model is not configured in API_KEY.json.")
        return []

    if meta.get("embedding_model") != embed_model:
        print(
            "[!] Embedding model mismatch "
            f"(index: {meta.get('embedding_model')}, config: {embed_model}). "
            "Run `python createbase.py --refresh` to re-embed the existing chunks."
        )
        return []

    try:
        index = faiss.read_index(index_path)
    except Exception as exc:
        if mode == "vector":
            print(f"[!] Vector index is unreadable: {exc}")
            return []
        print(f"[!] Vector index is unreadable, falling back to keyword search: {exc}")
        return keyword_search(doc_store_path, keywords, top_k)

    try:
        query_vec = model_client.embed_texts([query])[0]
    except Exception as exc:
        if mode == "vector":
            print(f"[!] Embedding failed: {exc}")
            return []
        print(f"[!] Embedding failed, falling back to keyword search: {exc}")
        return keyword_search(doc_store_path, keywords, top_k)
    vectors_np = np.array([query_vec], dtype="float32")
    vectors_np = normalize_vectors(vectors_np, np)

    scores, ids = index.search(vectors_np, top_k)
    vector_ids = [int(i) for i in ids[0] if int(i) != -1]
    if not vector_ids:
        return []

    records_by_id = load_records_by_ids(doc_store_path, set(vector_ids))
    results = []
    for rank, (vector_id, score) in enumerate(zip(ids[0], scores[0]), 1):
        vector_id = int(vector_id)
        if vector_id == -1:
            continue
        record = records_by_id.get(vector_id)
        if not record:
            continue
        results.append({
            "rank": rank,
            "score": float(score),
            "record": record,
        })
    return results


def print_results(results, keywords):
    if not results:
        print("[!] No results.")
        return

    print("[+] Query keywords:", ", ".join(keywords))
    for item in results:
        rec = item["record"]
        snippet = clean_snippet(rec.get("text", ""))
        title = rec.get("title") or rec.get("file_name") or "(untitled)"
        print("-" * 80)
        print(f"Rank: {item['rank']}  Score: {item['score']:.4f}")
        print(f"Title: {title}")
        print(f"File: {rec.get('file_name')}  Type: {rec.get('file_type')}  Date: {rec.get('date')}")
        print(f"Section: {rec.get('section_title')}  Chunk: {rec.get('chunk_index')}/{rec.get('chunk_total')}")
        print(f"Path: {rec.get('source_path')}")
        print(f"Snippet: {snippet}")
    print("-" * 80)


def main():
    parser = argparse.ArgumentParser(description="Search KB by comma-separated keywords")
    parser.add_argument("query", nargs="?", help="Comma-separated keywords")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--kb-dir", default=DEFAULT_KB_DIR)
    parser.add_argument("--api", default=DEFAULT_API_KEY_PATH)
    parser.add_argument("--mode", default="auto", help="auto | vector | keyword")
    args = parser.parse_args()

    raw_query = args.query
    if not raw_query:
        raw_query = input("Keywords (comma-separated): ").strip()

    keywords = parse_keywords(raw_query)
    query = build_query(raw_query)
    results = search_kb(query, keywords, args.kb_dir, args.api, args.top, args.mode)
    print_results(results, keywords)


if __name__ == "__main__":
    main()
