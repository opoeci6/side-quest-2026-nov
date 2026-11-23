"""Render a Markdown file to a print-ready PDF with headless Chrome or Edge.

Usage:
    scripts/with-env.sh python scripts/render_pdf.py docs/pitch.md [-o docs/pitch.pdf] [--max-pages 1]

The browser runs with a throwaway profile under .cache/render/, so the user's
own browser profile is never touched.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / ".cache" / "render"

# Chrome first: on this machine headless Edge exits without writing a PDF.
BROWSER_CANDIDATES = [
    os.environ.get("BROWSER_PATH", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "google-chrome",
    "chromium",
    "msedge",
]

PRINT_CSS = """
@page { size: Letter; margin: 0.5in 0.6in; }
html { font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 10.2pt;
       line-height: 1.33; color: #1d1d1f; }
body { margin: 0; }
h1 { font-size: 17pt; margin: 0 0 2pt 0; color: #111; }
h1 + p { margin-top: 0; color: #555; }
h2 { font-size: 11pt; margin: 7pt 0 1pt 0; color: #b4470b;
     text-transform: none; letter-spacing: 0.1pt; }
p { margin: 2pt 0 4pt 0; }
ul { margin: 2pt 0 4pt 0; padding-left: 15pt; }
li { margin: 0 0 2pt 0; }
strong { color: #111; }
em { color: #333; }
"""


def find_browser() -> str:
    for candidate in BROWSER_CANDIDATES:
        if not candidate:
            continue
        if Path(candidate).is_file():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    sys.exit("render_pdf: no Edge or Chrome found; set BROWSER_PATH")


def count_pages(pdf_bytes: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf_bytes))


def render(md_path: Path, pdf_path: Path) -> int:
    text = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["extra", "sane_lists"])
    title = html.escape(md_path.stem)
    page = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title><style>{PRINT_CSS}</style></head>"
        f"<body>{body}</body></html>"
    )

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    html_path = WORK_DIR / f"{md_path.stem}.html"
    html_path.write_text(page, encoding="utf-8")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()

    cmd = [
        find_browser(),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        f"--user-data-dir={WORK_DIR / 'profile'}",
        f"--print-to-pdf={pdf_path}",
        html_path.as_uri(),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    if not pdf_path.exists():
        sys.exit("render_pdf: browser finished but wrote no PDF")
    return count_pages(pdf_path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("markdown_file", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="PDF path (default: next to the .md)")
    parser.add_argument("--max-pages", type=int, default=0, help="exit 1 if the PDF is longer")
    args = parser.parse_args()

    md_path = args.markdown_file.resolve()
    pdf_path = (args.output or md_path.with_suffix(".pdf")).resolve()
    pages = render(md_path, pdf_path)
    print(f"{pdf_path} ({pages} page{'s' if pages != 1 else ''})")
    if args.max_pages and pages > args.max_pages:
        print(f"render_pdf: {pages} pages, limit is {args.max_pages}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
