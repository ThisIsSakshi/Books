#!/usr/bin/env python3
"""Append newly added books to README without modifying existing entries."""

from __future__ import annotations

import argparse
import html
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, unquote

BOOK_EXTENSIONS = {".pdf", ".rar", ".epub", ".mobi", ".azw3"}
DEFAULT_BASE_URL = "https://github.com/ThisIsSakshi/Books/blob/master/"

SECTION_ORDER = [
    "Python Love ❤️",
    "ML 🤖",
    "System Design 💻",
    "Interview Specific 📖",
    "Other Books 📚",
    "Timepass 🤗",
]

SECTION_EMOJI = {
    "Python Love ❤️": "❤️",
    "ML 🤖": "🤖",
    "System Design 💻": "💻",
    "Interview Specific 📖": "📖",
    "Other Books 📚": "📚",
    "Timepass 🤗": "🤗",
}

SUMMARY_TO_FOLDER = (
    ("python", "Python Love ❤️"),
    ("machine learning", "ML 🤖"),
    ("system design", "System Design 💻"),
    ("interview prep", "Interview Specific 📖"),
    ("other books", "Other Books 📚"),
    ("timepass", "Timepass 🤗"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find newly added books and append them to README while leaving existing "
            "content unchanged."
        )
    )
    parser.add_argument("--root", default=".", help="Repository root directory")
    parser.add_argument("--readme", default="README.md", help="README path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be added without writing files",
    )
    return parser.parse_args()


def detect_base_url(readme_text: str) -> str:
    match = re.search(r"(https://github\.com/[^/\s]+/[^/\s]+/blob/[^/\s]+/)", readme_text)
    return match.group(1) if match else DEFAULT_BASE_URL


def extract_linked_paths(readme_text: str) -> set[str]:
    linked_paths: set[str] = set()
    links = re.findall(r"https://github\.com/[^\s)]+/blob/[^\s)]+", readme_text)
    for link in links:
        clean_link = link.split("?", 1)[0]
        blob_split = clean_link.split("/blob/", 1)
        if len(blob_split) != 2:
            continue
        branch_split = blob_split[1].split("/", 1)
        if len(branch_split) != 2:
            continue
        encoded_path = branch_split[1]
        linked_paths.add(unquote(encoded_path))
    return linked_paths


def find_section_boundaries(lines: list[str]) -> dict[str, int]:
    boundaries: dict[str, int] = {}
    index = 0
    while index < len(lines):
        if "<details" not in lines[index]:
            index += 1
            continue

        summary_lines = []
        probe = index + 1
        while probe < len(lines):
            summary_lines.append(lines[probe])
            if "</summary>" in lines[probe]:
                break
            probe += 1

        summary_text = " ".join(summary_lines).lower()
        folder = None
        for token, mapped_folder in SUMMARY_TO_FOLDER:
            if token in summary_text:
                folder = mapped_folder
                break

        while probe < len(lines) and "</details>" not in lines[probe]:
            probe += 1

        if folder and probe < len(lines):
            boundaries[folder] = probe
        index = probe + 1
    return boundaries


def collect_new_books(root: Path, linked_paths: set[str]) -> dict[str, list[Path]]:
    new_books: dict[str, list[Path]] = defaultdict(list)
    for folder in SECTION_ORDER:
        folder_path = root / folder
        if not folder_path.exists():
            continue
        for path in sorted(folder_path.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in BOOK_EXTENSIONS:
                continue
            relative = path.relative_to(root)
            if relative.as_posix() not in linked_paths:
                new_books[folder].append(relative)
    return new_books


def build_entry(folder: str, relative_path: Path, base_url: str) -> str:
    title = html.escape(relative_path.stem)
    encoded_path = quote(relative_path.as_posix(), safe="/")
    url = f"{base_url}{encoded_path}"
    emoji = SECTION_EMOJI[folder]
    return f'{emoji}[<img alt="{title}" title="{title}" src="" width="150" /> ]({url})<br>'


def apply_updates(
    lines: list[str],
    section_boundaries: dict[str, int],
    new_books: dict[str, list[Path]],
    base_url: str,
) -> list[str]:
    insert_plan = []
    for folder, books in new_books.items():
        if not books:
            continue
        boundary = section_boundaries.get(folder)
        if boundary is None:
            continue
        entries = []
        entries.append("\n")
        for book in books:
            entries.append(build_entry(folder, book, base_url) + "\n")
            entries.append("\n")
        insert_plan.append((boundary, entries))

    updated_lines = lines[:]
    for boundary, entries in sorted(insert_plan, key=lambda item: item[0], reverse=True):
        updated_lines[boundary:boundary] = entries
    return updated_lines


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    readme_path = root / args.readme

    if not readme_path.exists():
        print(f"README not found: {readme_path}")
        return 1

    readme_text = readme_path.read_text(encoding="utf-8")
    lines = readme_text.splitlines(keepends=True)

    base_url = detect_base_url(readme_text)
    linked_paths = extract_linked_paths(readme_text)
    section_boundaries = find_section_boundaries(lines)
    new_books = collect_new_books(root, linked_paths)

    pending = {folder: books for folder, books in new_books.items() if books}
    if not pending:
        print("No new books found.")
        return 0

    for folder, books in pending.items():
        for book in books:
            print(f"Will add: {book.as_posix()} -> {folder}")

    if args.dry_run:
        print("\nDry run complete. README was not modified.")
        return 0

    updated_lines = apply_updates(lines, section_boundaries, pending, base_url)
    updated_text = "".join(updated_lines)
    if updated_text == readme_text:
        print("No applicable section found for new books. README not modified.")
        return 0

    readme_path.write_text(updated_text, encoding="utf-8")
    print(f"\nAdded {sum(len(books) for books in pending.values())} new book(s) to {readme_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
