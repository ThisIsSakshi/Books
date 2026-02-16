#!/usr/bin/env python3
"""Render README sections as a 3-column library view and include new books."""

from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

BOOK_EXTENSIONS = {".pdf", ".rar", ".epub", ".mobi", ".azw3"}
DEFAULT_BASE_URL = "https://github.com/ThisIsSakshi/Books/blob/master/"
COLUMNS = 3
FALLBACK_FOLDER = "Other Books 📚"

SECTION_ORDER = [
    "Python Love ❤️",
    "ML 🤖",
    "System Design 💻",
    "Interview Specific 📖",
    "Other Books 📚",
    "Timepass 🤗",
]

SUMMARY_TO_FOLDER = (
    ("python", "Python Love ❤️"),
    ("machine learning", "ML 🤖"),
    ("system design", "System Design 💻"),
    ("interview prep", "Interview Specific 📖"),
    ("other books", "Other Books 📚"),
    ("timepass", "Timepass 🤗"),
)

BLOB_LINK_RE = re.compile(r"https://github\.com/[^\"'\s)]+/blob/[^\"'\s)]+")
MARKDOWN_CARD_RE = re.compile(
    r"<img[^>]*src=\"([^\"]*)\"[^>]*>\s*\]\((https://github\.com/[^\s)]+/blob/[^\s)]+)\)"
)
HTML_CARD_RE = re.compile(
    r"<a[^>]*href=\"(https://github\.com/[^\"]+/blob/[^\"]+)\"[^>]*>\s*<img[^>]*src=\"([^\"]*)\"",
    re.IGNORECASE,
)


@dataclass
class SectionSpan:
    folder: str
    summary_end_index: int
    details_end_index: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a 3-column library view inside existing README dropdown sections "
            "and add any new book files."
        )
    )
    parser.add_argument("--root", default=".", help="Repository root directory")
    parser.add_argument("--readme", default="README.md", help="README path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files",
    )
    return parser.parse_args()


def detect_base_url(readme_text: str) -> str:
    match = re.search(r"(https://github\.com/[^/\s]+/[^/\s]+/blob/[^/\s]+/)", readme_text)
    return match.group(1) if match else DEFAULT_BASE_URL


def decode_blob_path(link: str) -> str | None:
    clean = link.split("?", 1)[0]
    blob_split = clean.split("/blob/", 1)
    if len(blob_split) != 2:
        return None
    branch_split = blob_split[1].split("/", 1)
    if len(branch_split) != 2:
        return None
    return unquote(branch_split[1])


def extract_existing_image_sources(readme_text: str) -> dict[str, str]:
    path_to_src: dict[str, str] = {}

    for match in MARKDOWN_CARD_RE.finditer(readme_text):
        src, link = match.group(1), match.group(2)
        decoded = decode_blob_path(link)
        if decoded is None:
            continue
        current = path_to_src.get(decoded)
        if current is None or (not current and src):
            path_to_src[decoded] = src

    for match in HTML_CARD_RE.finditer(readme_text):
        link, src = match.group(1), match.group(2)
        decoded = decode_blob_path(link)
        if decoded is None:
            continue
        current = path_to_src.get(decoded)
        if current is None or (not current and src):
            path_to_src[decoded] = src

    return path_to_src


def extract_existing_order(readme_text: str) -> dict[str, list[str]]:
    order: dict[str, list[str]] = {folder: [] for folder in SECTION_ORDER}
    seen: set[str] = set()

    for match in BLOB_LINK_RE.finditer(readme_text):
        decoded = decode_blob_path(match.group(0))
        if decoded is None:
            continue
        if decoded in seen:
            continue
        for folder in SECTION_ORDER:
            if decoded.startswith(f"{folder}/"):
                order[folder].append(decoded)
                seen.add(decoded)
                break
    return order


def find_sections(lines: list[str]) -> list[SectionSpan]:
    sections: list[SectionSpan] = []
    index = 0
    while index < len(lines):
        if "<details" not in lines[index]:
            index += 1
            continue

        summary_lines = []
        probe = index + 1
        summary_end = -1
        while probe < len(lines):
            summary_lines.append(lines[probe])
            if "</summary>" in lines[probe]:
                summary_end = probe
                break
            probe += 1
        if summary_end == -1:
            index += 1
            continue

        summary_text = " ".join(summary_lines).lower()
        folder = None
        for token, mapped_folder in SUMMARY_TO_FOLDER:
            if token in summary_text:
                folder = mapped_folder
                break

        details_end = summary_end + 1
        while details_end < len(lines) and "</details>" not in lines[details_end]:
            details_end += 1

        if folder and details_end < len(lines):
            sections.append(
                SectionSpan(
                    folder=folder,
                    summary_end_index=summary_end,
                    details_end_index=details_end,
                )
            )
        index = details_end + 1
    return sections


def collect_books(root: Path, existing_order: dict[str, list[str]]) -> dict[str, list[Path]]:
    books_by_folder: dict[str, list[Path]] = {folder: [] for folder in SECTION_ORDER}
    disk_paths_by_folder: dict[str, dict[str, Path]] = {folder: {} for folder in SECTION_ORDER}

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        if path.suffix.lower() not in BOOK_EXTENSIONS:
            continue

        relative = path.relative_to(root)
        parts = relative.parts
        if not parts:
            continue
        top_level = parts[0]
        folder = top_level if top_level in SECTION_ORDER else FALLBACK_FOLDER
        disk_paths_by_folder[folder][relative.as_posix()] = relative

    for folder in SECTION_ORDER:
        disk_paths = disk_paths_by_folder[folder]
        books: list[Path] = []
        for existing in existing_order.get(folder, []):
            relative = disk_paths.pop(existing, None)
            if relative is not None:
                books.append(relative)
        for relative in sorted(disk_paths.values(), key=lambda item: item.as_posix().lower()):
            books.append(relative)
        books_by_folder[folder] = books
    return books_by_folder


def book_card(relative_path: Path, base_url: str, src_by_path: dict[str, str]) -> str:
    relative = relative_path.as_posix()
    title = html.escape(relative_path.stem)
    encoded_path = quote(relative, safe="/")
    url = f"{base_url}{encoded_path}"
    src = html.escape(src_by_path.get(relative, ""))
    return (
        '<td align="center" width="33%">\n'
        f'  <a href="{url}"><img src="{src}" alt="{title}" title="{title}" width="150" /></a><br>\n'
        f"  <sub><b>{title}</b></sub>\n"
        "</td>\n"
    )


def build_table_lines(
    books: list[Path],
    base_url: str,
    src_by_path: dict[str, str],
) -> list[str]:
    lines: list[str] = ["\n", "<table>\n"]
    if not books:
        lines.extend(["</table>\n", "\n"])
        return lines

    for i in range(0, len(books), COLUMNS):
        chunk = books[i : i + COLUMNS]
        lines.append("<tr>\n")
        for book in chunk:
            lines.append(book_card(book, base_url, src_by_path))
        for _ in range(COLUMNS - len(chunk)):
            lines.append('<td align="center" width="33%"></td>\n')
        lines.append("</tr>\n")
    lines.extend(["</table>\n", "\n"])
    return lines


def render_readme(
    lines: list[str],
    sections: list[SectionSpan],
    books_by_folder: dict[str, list[Path]],
    base_url: str,
    src_by_path: dict[str, str],
) -> list[str]:
    updated = lines[:]
    for section in sorted(sections, key=lambda item: item.summary_end_index, reverse=True):
        body = build_table_lines(books_by_folder.get(section.folder, []), base_url, src_by_path)
        start = section.summary_end_index + 1
        end = section.details_end_index
        updated[start:end] = body
    return updated


def print_new_books(books_by_folder: dict[str, list[Path]], known_paths: set[str]) -> int:
    count = 0
    for folder in SECTION_ORDER:
        for book in books_by_folder.get(folder, []):
            if book.as_posix() in known_paths:
                continue
            count += 1
            print(f"New book: {book.as_posix()} -> {folder}")
    return count


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
    src_by_path = extract_existing_image_sources(readme_text)
    existing_order = extract_existing_order(readme_text)
    known_paths = {path for paths in existing_order.values() for path in paths}
    books_by_folder = collect_books(root, existing_order)
    sections = find_sections(lines)
    if not sections:
        print("No supported dropdown sections found. README not modified.")
        return 1

    new_count = print_new_books(books_by_folder, known_paths)
    if new_count == 0:
        print("No new books detected. Reformatting section layout only.")

    updated_lines = render_readme(lines, sections, books_by_folder, base_url, src_by_path)
    updated_text = "".join(updated_lines)
    if updated_text == readme_text:
        print("README already up-to-date.")
        return 0

    if args.dry_run:
        print("\nDry run complete. README was not modified.")
        return 0

    readme_path.write_text(updated_text, encoding="utf-8")
    print(f"\nUpdated library view in {readme_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
