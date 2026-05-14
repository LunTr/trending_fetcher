import os
import json
import re

ARXIV_HISTORY_FILE = "downloaded_arxiv_history.json"
DATE_DIR_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ARXIV_ID_PATTERN = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")


def extract_arxiv_id_from_name(name):
    match = ARXIV_ID_PATTERN.search(name)
    if not match:
        return None
    return f"{match.group(1)}{match.group(2) or ''}"


def find_date_in_path(path, base_dir):
    rel_path = os.path.relpath(path, base_dir)
    for part in rel_path.split(os.sep):
        if DATE_DIR_PATTERN.match(part):
            return part
    return None


def build_history(base_dir):
    history = {}
    for root, _, files in os.walk(base_dir):
        for fname in files:
            if not (fname.endswith(".pdf") or fname.endswith("_summary.md")):
                continue
            arxiv_id = extract_arxiv_id_from_name(fname)
            if not arxiv_id:
                continue
            full_path = os.path.join(root, fname)
            date_str = find_date_in_path(full_path, base_dir)
            if not date_str:
                continue
            existing_date = history.get(arxiv_id)
            if not existing_date or date_str > existing_date:
                history[arxiv_id] = date_str
    return history


def main():
    base_dir = os.getcwd()
    history = build_history(base_dir)
    with open(ARXIV_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"Updated {ARXIV_HISTORY_FILE} with {len(history)} entries.")


if __name__ == "__main__":
    main()
