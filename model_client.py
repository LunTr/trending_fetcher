import json
import random
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
DEFAULT_CONCURRENCY = 4
DEFAULT_BATCH_SIZE = 16


def _build_url(base_url, suffix):
    if not base_url:
        return ""
    base = base_url.rstrip("/")
    suffix = suffix.lstrip("/")
    return f"{base}/{suffix}"


def _load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("API_KEY.json must be an object with model configs.")
    return data


def _normalize_conf(raw_conf):
    raw_conf = raw_conf or {}
    return {
        "api_key": raw_conf.get("API_KEY", ""),
        "base_url": raw_conf.get("Base_URL", ""),
        "model": raw_conf.get("Model", ""),
        "timeout": raw_conf.get("Timeout") or raw_conf.get("timeout") or DEFAULT_TIMEOUT,
        "concurrency": raw_conf.get("Concurrency") or raw_conf.get("concurrency") or DEFAULT_CONCURRENCY,
        "batch_size": raw_conf.get("Batch_Size") or raw_conf.get("batch_size") or DEFAULT_BATCH_SIZE,
        "max_retries": raw_conf.get("Max_Retries") or raw_conf.get("max_retries") or DEFAULT_RETRIES,
        "verify_ssl": raw_conf.get("Verify_SSL", raw_conf.get("verify_ssl", True)),
    }


class ModelClient:
    def __init__(self, embedding_conf, reranker_conf):
        self.embedding_conf = _normalize_conf(embedding_conf)
        self.reranker_conf = _normalize_conf(reranker_conf)
        self.session = requests.Session()
        proxies = urllib.request.getproxies()
        if proxies:
            self.session.proxies.update(proxies)
        self.session.trust_env = True

    @classmethod
    def from_config_path(cls, config_path):
        config = _load_config(config_path)
        embed_conf = config.get("Embedding_Model") or {}
        rerank_conf = config.get("Reranker_Model") or {}
        return cls(embed_conf, rerank_conf)

    def embed_texts(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return []
        conf = self.embedding_conf
        if not conf["model"]:
            raise ValueError("Embedding model is not configured.")
        if not conf["base_url"]:
            raise ValueError("Embedding base_url is not configured.")

        batch_size = int(conf["batch_size"])
        concurrency = max(1, int(conf["concurrency"]))
        batches = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            batches.append((start, batch))

        results = [None] * len(texts)
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_map = {
                executor.submit(self._embed_batch, batch): start
                for start, batch in batches
            }
            for future in as_completed(future_map):
                start = future_map[future]
                vectors = future.result()
                for offset, vector in enumerate(vectors):
                    results[start + offset] = vector

        if any(v is None for v in results):
            raise RuntimeError("Embedding returned empty vectors for some inputs.")
        return results

    def rerank(self, query, candidates):
        if not candidates:
            return []
        conf = self.reranker_conf
        if not conf["model"]:
            raise ValueError("Reranker model is not configured.")
        if not conf["base_url"]:
            raise ValueError("Reranker base_url is not configured.")

        url = _build_url(conf["base_url"], "rerank")
        payload = {
            "model": conf["model"],
            "query": query,
            "documents": candidates,
        }
        response = self._post_json(url, payload, conf)
        data = response.get("data") or response.get("results") or []

        if not data:
            raise RuntimeError("Rerank returned empty results.")

        if isinstance(data, list) and data and isinstance(data[0], dict):
            if "index" in data[0] or "document_index" in data[0]:
                scores = [0.0] * len(candidates)
                for item in data:
                    idx = item.get("index")
                    if idx is None:
                        idx = item.get("document_index")
                    if idx is None:
                        continue
                    score = item.get("relevance_score")
                    if score is None:
                        score = item.get("score")
                    scores[int(idx)] = float(score)
                return scores
            scores = [
                float(item.get("relevance_score") or item.get("score") or 0.0)
                for item in data
            ]
            if len(scores) != len(candidates):
                raise RuntimeError("Rerank results length mismatch.")
            return scores

        if isinstance(data, list) and len(data) == len(candidates):
            return [float(score) for score in data]

        raise RuntimeError("Unsupported rerank response format.")

    def _embed_batch(self, batch):
        conf = self.embedding_conf
        url = _build_url(conf["base_url"], "embeddings")
        payload = {
            "model": conf["model"],
            "input": batch,
        }
        response = self._post_json(url, payload, conf)
        data = response.get("data", [])
        if not data:
            raise RuntimeError("Embedding returned empty data.")

        if all("index" in item for item in data):
            data = sorted(data, key=lambda item: item["index"])
        vectors = [item.get("embedding") for item in data]
        if len(vectors) != len(batch):
            raise RuntimeError("Embedding results length mismatch.")
        return vectors

    def _post_json(self, url, payload, conf):
        headers = {"Content-Type": "application/json"}
        if conf.get("api_key"):
            headers["Authorization"] = f"Bearer {conf['api_key']}"

        timeout = conf.get("timeout", DEFAULT_TIMEOUT)
        verify_ssl = conf.get("verify_ssl", True)
        max_retries = int(conf.get("max_retries", DEFAULT_RETRIES))

        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                    verify=verify_ssl,
                )
                response.raise_for_status()
                return response.json()
            except Exception:
                if attempt >= max_retries - 1:
                    raise
                backoff = 1.5 ** attempt + random.random()
                time.sleep(backoff)

        raise RuntimeError("Request retries exceeded.")
