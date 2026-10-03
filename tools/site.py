#!/usr/bin/env python3
"""Render the Requi Markdown graph into a self-contained clickable HTML site."""
from __future__ import annotations

import hashlib
import html
import re
import sqlite3
import sys
from pathlib import Path
from db_source import database_markdown

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
LINK = re.compile(r"\[([^]]+)\]\(([^)]+)\)")


def href(target: str, source: Path) -> str:
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return target
    anchor = ""
    if "#" in target:
        target, anchor = target.split("#", 1)
    resolved = (source.parent / target).resolve()
    target_rel = resolved.relative_to(ROOT)
    target_rel = (target_rel / "index.html") if target.endswith("/") else target_rel.with_suffix(".html")
    source_rel = source.relative_to(ROOT)
    return Path(__import__("os").path.relpath(target_rel, source_rel.parent)).as_posix() + (f"#{anchor}" if anchor else "")
def inline(text: str, source: Path) -> str:
    escaped = html.escape(text, quote=False)
    placeholders: list[str] = []

    def replace(match: re.Match[str]) -> str:
        label, target = match.groups()
        token = f"\x00{len(placeholders)}\x00"
        placeholders.append(f'<a href="{html.escape(href(target, source), quote=True)}">{html.escape(label)}</a>')
        return token

    escaped = LINK.sub(replace, escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    for index, value in enumerate(placeholders):
        escaped = escaped.replace(f"\x00{index}\x00", value)
    return escaped


def render(markdown: str, source: Path) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    in_code = False
    paragraph: list[str] = []
    list_open = False
    table_rows: list[list[str]] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            output.append(f"<p>{inline(' '.join(paragraph), source)}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            output.append("</ul>")
            list_open = False

    def close_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        output.append("<table><thead><tr>" + "".join(f"<th>{inline(cell, source)}</th>" for cell in table_rows[0]) + "</tr></thead><tbody>")
        for row in table_rows[1:]:
            output.append("<tr>" + "".join(f"<td>{inline(cell, source)}</td>" for cell in row) + "</tr>")
        output.append("</tbody></table>")
        table_rows = []

    for line in lines:
        if line.startswith("```"):
            flush_paragraph()
            close_list()
            close_table()
            output.append("</code></pre>" if in_code else "<pre><code>")
            in_code = not in_code
            continue
        if in_code:
            output.append(html.escape(line) + "\n")
            continue
        if line.strip().startswith("|") and line.strip().endswith("|"):
            flush_paragraph()
            close_list()
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                table_rows.append(cells)
            continue
        close_table()
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        item = re.match(r"^\s*[-*]\s+(.+)$", line)
        quote = re.match(r"^\s*>\s*(.*)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            heading_text = heading.group(2)
            heading_id = heading_text.split(" — ", 1)[0].lower() if heading_text.startswith("DB-") else re.sub(r"[^a-z0-9]+", "-", heading_text.lower()).strip("-")
            output.append(f'<h{level} id="{heading_id}">{inline(heading_text, source)}</h{level}>')
        elif item:
            flush_paragraph()
            if not list_open:
                output.append("<ul>")
                list_open = True
            output.append(f"<li>{inline(item.group(1), source)}</li>")
        elif quote:
            flush_paragraph()
            close_list()
            output.append(f"<blockquote>{inline(quote.group(1), source)}</blockquote>")
        elif line.strip():
            close_list()
            paragraph.append(line.strip())
        else:
            flush_paragraph()
            close_list()
    flush_paragraph()
    close_list()
    close_table()
    return "\n".join(output)


def page(title: str, body: str, source: Path) -> str:
    home = Path(__import__("os").path.relpath("_HOME.html", source.relative_to(ROOT).parent)).as_posix()
    return f'''<!doctype html>
<meta charset="utf-8">
<title>{html.escape(title)} — Requi</title>
<style>:root{{color-scheme:light dark}}body{{font:16px/1.6 system-ui,sans-serif;max-width:72rem;margin:0 auto;padding:2rem 1.25rem;background:#10141c;color:#e8edf5}}main{{background:#171d28;border:1px solid #2c3748;border-radius:14px;padding:2rem}}nav{{margin-bottom:1rem}}a{{color:#72b7ff}}h1,h2,h3{{line-height:1.2;color:#fff}}pre{{background:#0b0e13;border:1px solid #2c3748;border-radius:8px;padding:1rem;overflow:auto}}code{{background:#0b0e13;padding:.15rem .35rem;border-radius:4px}}table{{width:100%;border-collapse:collapse;margin:1rem 0}}td,th{{border:1px solid #3a4658;padding:.6rem;text-align:left}}th{{background:#222c3b}}blockquote{{border-left:4px solid #72b7ff;margin:1rem 0;padding:.25rem 1rem;color:#b8c4d6}}</style>
<nav><a href="{home}">Requi home</a></nav>
<main>{body}</main>
'''

def _is_database_projection(relative: str) -> bool:
    path = Path(relative)
    return relative in {"glossary.md", "requirements.md"} or path.parts[:1] in {
        ("terms",),
        ("layers",),
        ("requirements",),
        ("lexeme",),
    }


def markdown_sources(db: sqlite3.Connection) -> dict[str, str]:
    """Return static Markdown plus SQLite-backed projections for site rendering."""
    sources = {
        str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
        for path in ROOT.rglob("*.md")
        if OUT not in path.parents and ".git" not in path.parts
        and not _is_database_projection(str(path.relative_to(ROOT)))
    }
    sources.update(database_markdown(db))
    return dict(sorted(sources.items()))


def status() -> int:
    db = sqlite3.connect(ROOT / "requi.db")
    try:
        rows = db.execute("SELECT path, source_hash FROM site_sources").fetchall()
    except sqlite3.OperationalError:
        db.close()
        print("STALE: site has never been generated")
        return 1
    current = markdown_sources(db)
    current_hashes = {
        relative: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for relative, content in current.items()
    }
    recorded = {relative: source_hash for relative, source_hash in rows}
    stale = sorted(set(current_hashes) - set(recorded))
    for relative, source_hash in recorded.items():
        generated = OUT / Path(relative).with_suffix(".html")
        if current_hashes.get(relative) != source_hash or not generated.exists():
            stale.append(relative)
    db.close()
    if stale:
        print("STALE: run python3 tools/site.py")
        print("\n".join(f"- {path}" for path in sorted(set(stale))))
        return 1
    print("HTML CURRENT")
    return 0



def main() -> None:
    db = sqlite3.connect(ROOT / "requi.db")
    db.execute("CREATE TABLE IF NOT EXISTS site_sources(path TEXT PRIMARY KEY, source_hash TEXT NOT NULL, generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    OUT.mkdir(parents=True, exist_ok=True)
    sources = markdown_sources(db)
    for (relative_source,) in db.execute("SELECT path FROM site_sources").fetchall():
        if relative_source not in sources:
            generated = OUT / Path(relative_source).with_suffix(".html")
            if generated.exists():
                generated.unlink()
            db.execute("DELETE FROM site_sources WHERE path = ?", (relative_source,))
    for relative, markdown in sources.items():
        source = ROOT / relative
        destination = OUT / Path(relative).with_suffix(".html")
        destination.parent.mkdir(parents=True, exist_ok=True)
        title_match = re.search(r"^# (?:Layer: )?(.+)$", markdown, re.M)
        title = title_match.group(1).strip() if title_match else source.stem
        destination.write_text(page(title, render(markdown, source), source), encoding="utf-8")
        digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        db.execute(
            "INSERT OR REPLACE INTO site_sources(path, source_hash) VALUES (?, ?)",
            (relative, digest),
        )

    for directory in sorted({path.parent for path in OUT.rglob("*.html")}):
        if directory == OUT:
            continue
        entries = "\n".join(
            f'<li><a href="{path.name}">{path.stem}</a></li>'
            for path in sorted(directory.glob("*.html"))
            if path.name != "index.html"
        )
        if directory == OUT / "requirements":
            requirement_entries = []
            for relative, markdown in sources.items():
                if not relative.startswith("requirements/"):
                    continue
                for match in re.finditer(r"^## ((?:REQ|DB)-\d+) — (.+)$", markdown, re.M):
                    requirement_entries.append(
                        f'<li><a href="{Path(relative).stem}.html#{match.group(1).lower()}">{match.group(1)} — {html.escape(match.group(2))}</a></li>'
                    )
            entries = entries + "\n" + "\n".join(requirement_entries)
        (directory / "index.html").write_text(
            f'<!doctype html><meta charset="utf-8"><title>{directory.name} — Requi</title>'
            f'<style>body{{font:16px system-ui,sans-serif;max-width:60rem;margin:2rem auto}}a{{color:#06c}}</style>'
            f'<h1>{directory.name}</h1><ul>{entries}</ul>',
            encoding="utf-8",
        )

    links = "\n".join(
        f'<li><a href="{path.relative_to(OUT).as_posix()}">{path.relative_to(OUT).with_suffix("").as_posix()}</a></li>'
        for path in sorted(OUT.rglob("*.html"))
    )
    (OUT / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Requi</title>'
        '<style>body{font:16px system-ui,sans-serif;max-width:68rem;margin:2rem auto}a{color:#06c}</style>'
        '<h1>Requi</h1><p>Clickable generated HTML for every Markdown file.</p><ul>'
        + links + "</ul>",
        encoding="utf-8",
    )
    print(f"Generated {len(sources)} Markdown pages in {OUT.relative_to(ROOT)}/")
    db.commit()
    db.close()


if __name__ == "__main__":
    if sys.argv[1:] == ["--status"]:
        raise SystemExit(status())
    main()
