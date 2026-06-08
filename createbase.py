import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re

import fitz

from model_client import ModelClient

DATE_DIR_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
SUPPORTED_EXTS = {".pdf", ".docx", ".doc", ".md", ".txt"}
SKIP_SUFFIXES = ("_summary.md",)

DEFAULT_SOURCE_DIR = os.path.join(
    os.getcwd(), datetime.datetime.now().strftime("%Y-%m-%d"), "HuggingFace"
)
DEFAULT_KB_DIR = os.path.join(os.getcwd(), "kb_store")
DEFAULT_API_KEY_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "API_KEY.json")
)


def emit(reporter, event, **payload):
    if reporter:
        reporter({"event": event, **payload})


def report_log(reporter, message, **payload):
    print(message)
    emit(reporter, "log", message=message, **payload)


def remove_corrupt_file(file_path, reason=None):
    base_name = os.path.basename(file_path)
    if not os.path.exists(file_path):
        print(f"[!] Corrupt file missing, skipped: {base_name}")
        return
    try:
        os.remove(file_path)
        print(f"[!] Corrupt file deleted: {base_name}")
    except Exception as exc:
        if reason:
            print(f"[!] Failed to delete corrupt file: {base_name} ({reason}) ({exc})")
        else:
            print(f"[!] Failed to delete corrupt file: {base_name} ({exc})")


def build_kb(source_dir=DEFAULT_SOURCE_DIR, kb_dir=DEFAULT_KB_DIR, api_key_path=DEFAULT_API_KEY_PATH, rebuild=False, reporter=None):
    try:
        import numpy as np
    except Exception:
        report_log(reporter, "[!] Missing dependency: numpy. Install it before running createbase.", stage="kb-build", level="error")
        return

    try:
        import faiss
    except Exception:
        report_log(reporter, "[!] Missing dependency: faiss-cpu. Install it before running createbase.", stage="kb-build", level="error")
        return

    if not os.path.exists(source_dir):
        report_log(reporter, f"[!] Source directory not found: {source_dir}", stage="kb-build", level="error")
        return
    emit(reporter, "stage", stage="kb-build", source_dir=source_dir, kb_dir=kb_dir)

    os.makedirs(kb_dir, exist_ok=True)
    index_path = os.path.join(kb_dir, "vectors.faiss")
    meta_path = os.path.join(kb_dir, "index_meta.json")
    doc_store_path = os.path.join(kb_dir, "doc_store.jsonl")

    if rebuild:
        if os.path.exists(index_path):
            os.remove(index_path)
        if os.path.exists(meta_path):
            os.remove(meta_path)
        if os.path.exists(doc_store_path):
            os.remove(doc_store_path)

    model_client = ModelClient.from_config_path(api_key_path)
    embed_model = model_client.embedding_conf.get("model")
    if not embed_model:
        print("[!] Embedding model is not configured in API_KEY.json.")
        return

    index, meta = load_or_create_index(index_path, meta_path, embed_model)
    existing_chunk_ids, max_vector_id = load_existing_chunk_ids(doc_store_path)
    meta["next_id"] = max(meta.get("next_id", 1), max_vector_id + 1)

    pending_records = []
    total_new = 0
    processed_files = 0

    for file_path in iter_paper_files(source_dir):
        processed_files += 1
        emit(
            reporter,
            "kb_file",
            stage="kb-build",
            current=processed_files,
            file_name=os.path.basename(file_path),
            file_path=file_path,
        )
        text, doc_meta = extract_text_and_meta(file_path)
        if not text.strip():
            continue

        sections = split_sections(text)
        doc_id = doc_meta["doc_id"]
        for section_index, (section_title, section_text) in enumerate(sections):
            chunks = split_into_chunks(section_text)
            for chunk_index, chunk in enumerate(chunks):
                chunk_id = f"{doc_id}:{section_index}:{chunk_index}"
                if chunk_id in existing_chunk_ids:
                    continue

                record = {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "source_path": doc_meta["source_path"],
                    "file_name": doc_meta["file_name"],
                    "title": doc_meta.get("title", ""),
                    "authors": doc_meta.get("authors", ""),
                    "year": doc_meta.get("year", ""),
                    "date": doc_meta.get("date", ""),
                    "file_type": doc_meta["file_type"],
                    "section_title": section_title,
                    "chunk_index": chunk_index,
                    "chunk_total": len(chunks),
                    "text": chunk,
                }
                pending_records.append(record)

                if len(pending_records) >= 64:
                    added, index = flush_batch(
                        pending_records,
                        model_client,
                        index,
                        meta,
                        doc_store_path,
                        meta_path,
                        np,
                    )
                    total_new += added
                    emit(reporter, "kb_progress", stage="kb-build", added_chunks=total_new, total_vectors=meta.get("total_vectors"))
                    for rec in pending_records:
                        existing_chunk_ids.add(rec["chunk_id"])
                    pending_records = []

    if pending_records:
        added, index = flush_batch(
            pending_records,
            model_client,
            index,
            meta,
            doc_store_path,
            meta_path,
            np,
        )
        total_new += added
        emit(reporter, "kb_progress", stage="kb-build", added_chunks=total_new, total_vectors=meta.get("total_vectors"))
        for rec in pending_records:
            existing_chunk_ids.add(rec["chunk_id"])

    if index is None:
        report_log(reporter, "[!] No vectors were created. Check source directory and parsers.", stage="kb-build")
        return

    faiss.write_index(index, index_path)
    save_meta(meta_path, meta)

    report_log(reporter, f"[+] KB build complete. Added {total_new} new chunks.", stage="kb-build", added_chunks=total_new)


def load_or_create_index(index_path, meta_path, embed_model):
    try:
        import faiss
    except Exception:
        raise

    if os.path.exists(index_path):
        if not os.path.exists(meta_path):
            raise RuntimeError("Index meta missing. Rebuild with --rebuild.")
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("embedding_model") != embed_model:
            raise RuntimeError("Embedding model changed. Rebuild index to continue.")
        index = faiss.read_index(index_path)
        return index, meta

    meta = {
        "embedding_model": embed_model,
        "dimension": None,
        "total_vectors": 0,
        "next_id": 1,
        "updated_at": None,
    }
    index = None
    return index, meta


def flush_batch(records, model_client, index, meta, doc_store_path, meta_path, np):
    texts = [record["text"] for record in records]
    vectors = model_client.embed_texts(texts)
    vectors_np = np.array(vectors, dtype="float32")

    vectors_np = normalize_vectors(vectors_np, np)

    if index is None:
        dimension = vectors_np.shape[1]
        meta["dimension"] = dimension
        try:
            import faiss
        except Exception:
            raise
        base_index = faiss.IndexFlatIP(dimension)
        index = faiss.IndexIDMap2(base_index)

    if meta.get("dimension") and vectors_np.shape[1] != meta["dimension"]:
        raise RuntimeError("Embedding dimension mismatch. Rebuild index to continue.")

    vector_ids = []
    for record in records:
        record["vector_id"] = meta["next_id"]
        meta["next_id"] += 1
        vector_ids.append(record["vector_id"])

    ids_np = np.array(vector_ids, dtype="int64")
    index.add_with_ids(vectors_np, ids_np)

    with open(doc_store_path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    meta["total_vectors"] = int(index.ntotal)
    meta["updated_at"] = datetime.datetime.now().isoformat()
    save_meta(meta_path, meta)

    return len(records), index


def normalize_vectors(vectors, np):
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def load_existing_chunk_ids(doc_store_path):
    existing = set()
    max_vector_id = 0
    if not os.path.exists(doc_store_path):
        return existing, max_vector_id
    with open(doc_store_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            chunk_id = item.get("chunk_id")
            if chunk_id:
                existing.add(chunk_id)
            vector_id = item.get("vector_id")
            if isinstance(vector_id, int):
                max_vector_id = max(max_vector_id, vector_id)
    return existing, max_vector_id


def iter_paper_files(source_dir):
    for root, _, files in os.walk(source_dir):
        for name in files:
            if name.endswith(SKIP_SUFFIXES):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in SUPPORTED_EXTS:
                continue
            yield os.path.join(root, name)


def extract_text_and_meta(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".doc":
        print(f"[!] Unsupported .doc file skipped: {os.path.basename(file_path)}")
        return "", {}
    try:
        stat = os.stat(file_path)
    except Exception as exc:
        remove_corrupt_file(file_path, f"stat failed: {exc}")
        return "", {}
    doc_id = hash_doc_id(file_path, stat.st_size, stat.st_mtime)
    date_tag = find_date_in_path(file_path)
    year = date_tag.split("-")[0] if date_tag else ""

    metadata = {
        "doc_id": doc_id,
        "source_path": file_path,
        "file_name": os.path.basename(file_path),
        "file_type": ext.lstrip("."),
        "date": date_tag or "",
        "year": year,
    }

    if ext == ".pdf":
        text, pdf_meta = extract_pdf_text(file_path)
        metadata["title"] = pdf_meta.get("title") or derive_title_from_filename(file_path)
        metadata["authors"] = pdf_meta.get("author") or ""
        return text, metadata

    if ext == ".docx":
        text = extract_docx_text(file_path)
        metadata["title"] = derive_title_from_text(text) or derive_title_from_filename(file_path)
        return text, metadata

    text = read_text_file(file_path)
    metadata["title"] = derive_title_from_text(text) or derive_title_from_filename(file_path)
    return text, metadata


def extract_pdf_text(file_path):
    doc = None
    try:
        with suppress_mupdf_errors():
            doc = fitz.open(file_path)
            meta = doc.metadata or {}
            pages = []
            for page in doc:
                try:
                    pages.append(extract_page_text(page))
                except Exception:
                    continue
        return "\n\n".join(pages), meta
    except Exception as exc:
        remove_corrupt_file(file_path, f"pdf parse failed: {exc}")
        return "", {}
    finally:
        if doc is not None:
            with contextlib.suppress(Exception):
                doc.close()


@contextlib.contextmanager
def suppress_mupdf_errors():
    tools = getattr(fitz, "TOOLS", None)
    if tools:
        for name in ("mupdf_display_errors", "mupdf_display_warnings"):
            func = getattr(tools, name, None)
            if callable(func):
                with contextlib.suppress(Exception):
                    func(False)
    with open(os.devnull, "w") as devnull:
        with contextlib.redirect_stderr(devnull):
            yield


def extract_page_text(page):
    blocks = page.get_text("blocks")
    if not blocks:
        return page.get_text()

    text_blocks = [b for b in blocks if b[4].strip()]
    if not text_blocks:
        return ""

    mid = page.rect.width / 2
    left = [b for b in text_blocks if (b[0] + b[2]) / 2 <= mid]
    right = [b for b in text_blocks if (b[0] + b[2]) / 2 > mid]

    if left and right:
        left_sorted = sorted(left, key=lambda b: (b[1], b[0]))
        right_sorted = sorted(right, key=lambda b: (b[1], b[0]))
        ordered = left_sorted + right_sorted
    else:
        ordered = sorted(text_blocks, key=lambda b: (b[1], b[0]))

    lines = [b[4].strip() for b in ordered if b[4].strip()]
    return "\n".join(lines)


def extract_docx_text(file_path):
    try:
        from docx import Document
    except Exception:
        print("[!] Missing dependency: python-docx. Skipping docx file.")
        return ""

    try:
        doc = Document(file_path)
    except Exception as exc:
        remove_corrupt_file(file_path, f"docx parse failed: {exc}")
        return ""
    parts = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        parts.append(text)
    return "\n\n".join(parts)


def read_text_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as exc:
            remove_corrupt_file(file_path, f"text read failed: {exc}")
            return ""
    except Exception as exc:
        remove_corrupt_file(file_path, f"text read failed: {exc}")
        return ""


def split_sections(text):
    lines = text.splitlines()
    sections = []
    current_title = "Body"
    current_lines = []

    for line in lines:
        stripped = line.strip()
        if is_heading_line(stripped):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = clean_heading(stripped)
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))

    return [(title, text) for title, text in sections if text]


def is_heading_line(line):
    if not line:
        return False
    if line.startswith("#"):
        return True
    lowered = line.lower()
    if lowered in {"abstract", "introduction", "methods", "method", "results", "conclusion", "references"}:
        return True
    if re.match(r"^\d+(\.\d+)*\s+\S+", line) and len(line) <= 80:
        return True
    if line.isupper() and 4 <= len(line) <= 80:
        return True
    if line.endswith(":") and len(line) <= 80:
        return True
    return False


def clean_heading(line):
    line = line.lstrip("#").strip()
    return line if line else "Section"


def split_into_chunks(text, min_chars=300, max_chars=600, overlap_ratio=0.15):
    if not text:
        return []

    overlap_chars = int(max_chars * overlap_ratio)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    normalized_paragraphs = []
    for para in paragraphs:
        if len(para) <= max_chars:
            normalized_paragraphs.append(para)
        else:
            normalized_paragraphs.extend(split_long_text(para, max_chars, overlap_chars))

    chunks = []
    current = []
    current_len = 0

    for para in normalized_paragraphs:
        if current_len + len(para) + 2 > max_chars and current:
            chunk_text = "\n\n".join(current).strip()
            chunks.append(chunk_text)
            if overlap_chars > 0:
                overlap_text = chunk_text[-overlap_chars:]
                current = [overlap_text, para]
                current_len = len(overlap_text) + len(para)
            else:
                current = [para]
                current_len = len(para)
        else:
            current.append(para)
            current_len += len(para) + 2

    if current:
        chunks.append("\n\n".join(current).strip())

    if len(chunks) >= 2 and len(chunks[-1]) < min_chars:
        chunks[-2] = (chunks[-2] + "\n\n" + chunks[-1]).strip()
        chunks.pop()

    return [chunk for chunk in chunks if chunk]


def split_long_text(text, max_chars, overlap_chars):
    chunks = []
    start = 0
    step = max_chars - overlap_chars if max_chars > overlap_chars else max_chars
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += step
    return chunks


def derive_title_from_filename(file_path):
    base = os.path.splitext(os.path.basename(file_path))[0]
    base = re.sub(r"_\d{4}\.\d{4,5}(v\d+)?$", "", base)
    return base.replace("_", " ").strip()


def derive_title_from_text(text):
    if not text:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if stripped and len(stripped) <= 120:
            return stripped
    return ""


def hash_doc_id(path, size, mtime):
    payload = f"{path}|{size}|{int(mtime)}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def find_date_in_path(path):
    parts = os.path.normpath(path).split(os.sep)
    for part in parts:
        if DATE_DIR_PATTERN.fullmatch(part):
            return part
    return ""


def save_meta(meta_path, meta):
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Offline KB builder")
    parser.add_argument("--source", default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--kb-dir", default=DEFAULT_KB_DIR)
    parser.add_argument("--api", default=DEFAULT_API_KEY_PATH)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    build_kb(
        source_dir=args.source,
        kb_dir=args.kb_dir,
        api_key_path=args.api,
        rebuild=args.rebuild,
    )


if __name__ == "__main__":
    main()
