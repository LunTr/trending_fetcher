import argparse
import os
import re

import createbase

DATE_DIR_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DEFAULT_ROOT = os.getcwd()
DEFAULT_KB_DIR = os.path.join(os.getcwd(), "kb_store")
DEFAULT_API_KEY_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "API_KEY.json")
)


def iter_date_dirs(root_dir):
    for name in sorted(os.listdir(root_dir)):
        full_path = os.path.join(root_dir, name)
        if not os.path.isdir(full_path):
            continue
        if DATE_DIR_PATTERN.match(name):
            yield full_path


def main():
    parser = argparse.ArgumentParser(description="Build KB for all date folders")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--kb-dir", default=DEFAULT_KB_DIR)
    parser.add_argument("--api", default=DEFAULT_API_KEY_PATH)
    args = parser.parse_args()

    date_dirs = list(iter_date_dirs(args.root))
    if not date_dirs:
        print("[!] No date folders found.")
        return

    for date_dir in date_dirs:
        print(f"[+] Processing {date_dir}")
        createbase.build_kb(
            source_dir=date_dir,
            kb_dir=args.kb_dir,
            api_key_path=args.api,
            rebuild=False,
        )


if __name__ == "__main__":
    main()
