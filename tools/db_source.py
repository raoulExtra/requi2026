#!/usr/bin/env python3
"""SQLite-backed content storage and Markdown projections for Requi."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[([^]]+)\]\(([^)]+)\)")
REQ_ID = re.compile(r"\b(?:REQ|DB)-\d{3}\b")


def _title(text: str) -> str:
    match = re.search(r"^# (?:Layer: )?(.+)$", text, re.M)
    return match.group(1).strip() if match else ""


def _sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## (.+)$", text, re.M))
    return {
        match.group(1).strip().lower(): text[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        for index, match in enumerate(matches)
    }


def _add_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS terms(path TEXT PRIMARY KEY, name TEXT, definition TEXT);
        CREATE TABLE IF NOT EXISTS layers(id TEXT PRIMARY KEY, title TEXT);
        CREATE TABLE IF NOT EXISTS requirements(id TEXT PRIMARY KEY, source TEXT, status TEXT);
        CREATE TABLE IF NOT EXISTS term_layers(term_path TEXT, layer_id TEXT, PRIMARY KEY(term_path, layer_id));
        CREATE TABLE IF NOT EXISTS term_requirements(term_path TEXT, requirement_id TEXT, PRIMARY KEY(term_path, requirement_id));
        CREATE TABLE IF NOT EXISTS lexemes(id TEXT PRIMARY KEY, lemma TEXT NOT NULL, language TEXT NOT NULL, category TEXT NOT NULL, term_path TEXT);
        CREATE TABLE IF NOT EXISTS term_related(term_path TEXT, related_path TEXT, PRIMARY KEY(term_path, related_path));
        CREATE TABLE IF NOT EXISTS requirement_sources(path TEXT PRIMARY KEY, title TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requi_state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """
    )
    _add_column(db, "terms", "wikidata_id", "TEXT")
    _add_column(db, "terms", "lexeme_pending", "INTEGER NOT NULL DEFAULT 0")
    _add_column(db, "layers", "description", "TEXT NOT NULL DEFAULT ''")
    _add_column(db, "requirements", "title", "TEXT NOT NULL DEFAULT ''")
    _add_column(db, "requirements", "layer_id", "TEXT")
    _add_column(db, "requirements", "body", "TEXT NOT NULL DEFAULT ''")


def _state(db: sqlite3.Connection, key: str) -> str | None:
    row = db.execute("SELECT value FROM requi_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _set_state(db: sqlite3.Connection, key: str, value: str) -> None:
    db.execute("INSERT OR REPLACE INTO requi_state(key, value) VALUES (?, ?)", (key, value))


def _term_metadata(text: str) -> tuple[str | None, str | None, int]:
    wikidata = re.search(r"^> \*\*Wikidata:\*\* \[([^]]+)\]", text, re.M)
    lexeme = re.search(r"^> \*\*Lexeme:\*\* \[[^]]+\]\(\.\./lexeme/([^/]+)\.md\)", text, re.M)
    pending = bool(re.search(r"^> \*\*Lexeme:\*\* \*\(L-id via tools/wikidata\.py\)\*", text, re.M))
    return (wikidata.group(1) if wikidata else None, lexeme.group(1) if lexeme else None, int(pending))


def _term_row(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    parts = _sections(text)
    definition = " ".join(line.strip() for line in parts.get("definition", "").splitlines() if line.strip())
    related = []
    for _, target in LINK.findall(parts.get("related terms", "")):
        if target.endswith(".md") and not target.startswith("../"):
            related.append((path.parent / target).resolve().relative_to(ROOT).as_posix())
    layers = [
        (path.parent / target).resolve().relative_to(ROOT).as_posix().split("/", 1)[1].removesuffix(".md")
        for _, target in LINK.findall(parts.get("layers", ""))
        if target.startswith("../layers/")
    ]
    requirements = sorted(set(REQ_ID.findall(parts.get("requirements", ""))))
    wikidata_id, lexeme_id, lexeme_pending = _term_metadata(text)
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "name": _title(text),
        "definition": definition,
        "wikidata_id": wikidata_id,
        "lexeme_id": lexeme_id,
        "lexeme_pending": lexeme_pending,
        "layers": layers,
        "related": related,
        "requirements": requirements,
    }


def _layer_row(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^# Layer: (.+?)\n\n(.*?)(?:\n<!-- requi:begin|\Z)", text, re.S)
    description = match.group(2).strip() if match else ""
    return {"id": path.stem, "title": _title(text), "description": description}


def _requirement_sources() -> list[tuple[Path, str, str]]:
    result = []
    for path in sorted((ROOT / "requirements").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        result.append((path, _title(text), text))
    return result


def _import_requirements(db: sqlite3.Connection) -> None:
    db.execute("DELETE FROM requirement_sources")
    db.execute("DELETE FROM requirements")
    for path, source_title, text in _requirement_sources():
        source = path.relative_to(ROOT).as_posix()
        db.execute("INSERT INTO requirement_sources(path, title) VALUES (?, ?)", (source, source_title))
        matches = re.finditer(r"^## (DB-\d+) — (.+?)\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        for match in matches:
            requirement_id, title, body = match.groups()
            status = re.search(r"^- \*\*Status:\*\* ([^\n]+)$", body, re.M)
            layer = re.search(r"^- \*\*Layer:\*\* ([^\n]+)$", body, re.M)
            db.execute(
                "INSERT INTO requirements(id, source, status, title, layer_id, body) VALUES (?, ?, ?, ?, ?, ?)",
                (requirement_id, source, status.group(1).strip() if status else "", title.strip(), layer.group(1).strip() if layer else None, body.strip()),
            )


def import_markdown(db: sqlite3.Connection) -> None:
    """Perform the one-time Markdown-to-SQLite reconciliation."""
    ensure_schema(db)
    db.execute("DELETE FROM term_layers")
    db.execute("DELETE FROM term_requirements")
    db.execute("DELETE FROM term_related")
    db.execute("DELETE FROM terms")
    db.execute("DELETE FROM layers")
    db.execute("DELETE FROM lexemes")
    for path in sorted((ROOT / "terms").glob("*.md")):
        row = _term_row(path)
        db.execute(
            "INSERT INTO terms(path, name, definition, wikidata_id, lexeme_id, lexeme_pending) VALUES (?, ?, ?, ?, ?, ?)",
            (row["path"], row["name"], row["definition"], row["wikidata_id"], row["lexeme_id"], row["lexeme_pending"]),
        )
        for layer_id in row["layers"]:
            db.execute("INSERT INTO term_layers(term_path, layer_id) VALUES (?, ?)", (row["path"], layer_id))
        for requirement_id in row["requirements"]:
            db.execute("INSERT INTO term_requirements(term_path, requirement_id) VALUES (?, ?)", (row["path"], requirement_id))
        for related_path in row["related"]:
            db.execute("INSERT INTO term_related(term_path, related_path) VALUES (?, ?)", (row["path"], related_path))
    for path in sorted((ROOT / "layers").glob("*.md")):
        if path.name != "_layers.md":
            row = _layer_row(path)
            db.execute("INSERT INTO layers(id, title, description) VALUES (?, ?, ?)", (row["id"], row["title"], row["description"]))
    for path in sorted((ROOT / "lexeme").glob("L*.md")):
        text = path.read_text(encoding="utf-8")
        lemma = _title(text)
        language = re.search(r"^- \*\*Language:\*\* ([^\n]+)$", text, re.M)
        category = re.search(r"^- \*\*Lexical category:\*\* ([^\n]+)$", text, re.M)
        term = db.execute("SELECT path FROM terms WHERE lexeme_id = ?", (path.stem,)).fetchone()
        db.execute(
            "INSERT INTO lexemes(id, lemma, language, category, term_path) VALUES (?, ?, ?, ?, ?)",
            (path.stem, lemma, language.group(1).strip() if language else "", category.group(1).strip() if category else "", term[0] if term else None),
        )
    _import_requirements(db)
    now = datetime.now(timezone.utc).isoformat()
    _set_state(db, "source_mode", "sqlite")
    _set_state(db, "migration_status", "complete")
    _set_state(db, "migration_source", "markdown")
    _set_state(db, "migration_completed_at", now)


def _term_markdown(db: sqlite3.Connection, path: str) -> str:
    row = db.execute("SELECT name, definition, wikidata_id, lexeme_id, lexeme_pending FROM terms WHERE path = ?", (path,)).fetchone()
    if not row:
        raise ValueError(f"term not found: {path}")
    name, definition, wikidata_id, lexeme_id, lexeme_pending = row
    lines = [f"# {name}"]
    if wikidata_id:
        lines.extend([f"> **Wikidata:** [{wikidata_id}](https://www.wikidata.org/wiki/{wikidata_id})", ""])
    if lexeme_id:
        lines.extend([f"> **Lexeme:** [{lexeme_id}](../lexeme/{lexeme_id}.md)", ""])
    elif lexeme_pending:
        lines.extend(["> **Lexeme:** *(L-id via tools/wikidata.py)*", ""])
    lines.extend(["", "## Definition", definition, "", "## Layers"])
    for (layer_id,) in db.execute("SELECT layer_id FROM term_layers WHERE term_path = ? ORDER BY layer_id", (path,)):
        lines.append(f"- [{layer_id}](../layers/{layer_id}.md)")
    lines.extend(["", "## Related terms"])
    for (related_path,) in db.execute("SELECT related_path FROM term_related WHERE term_path = ? ORDER BY related_path", (path,)):
        lines.append(f"- [{Path(related_path).stem}]({Path(related_path).name})")
    lines.extend(["", "## Requirements"])
    for (requirement_id,) in db.execute("SELECT requirement_id FROM term_requirements WHERE term_path = ? ORDER BY requirement_id", (path,)):
        lines.append(f"- [{requirement_id}](../requirements.md#{requirement_id.lower()})")
    return "\n".join(lines).rstrip() + "\n"


def _layer_markdown(db: sqlite3.Connection, layer_id: str) -> str:
    row = db.execute("SELECT title, description FROM layers WHERE id = ?", (layer_id,)).fetchone()
    if not row:
        raise ValueError(f"layer not found: {layer_id}")
    title, description = row
    term_lines = [f"- [{name}](../terms/{Path(path).name})" for path, name in db.execute("SELECT t.path, t.name FROM terms t JOIN term_layers l ON l.term_path = t.path WHERE l.layer_id = ? ORDER BY lower(t.name)", (layer_id,))]
    req_lines = [f"- [{req_id} — {title_text}](../requirements/{Path(source).name}#{req_id.lower()})" for req_id, title_text, source in db.execute("SELECT id, title, source FROM requirements WHERE layer_id = ? ORDER BY id", (layer_id,))]
    return (
        f"# Layer: {layer_id}\n\n{description}\n\n"
        f"<!-- requi:begin layer-terms-{layer_id} -->\n{chr(10).join(term_lines) or '(no terms yet)'}\n<!-- requi:end -->\n\n"
        f"<!-- requi:begin layer-reqs-{layer_id} -->\n{chr(10).join(req_lines) or '(no requirements yet)'}\n<!-- requi:end -->\n"
    )


def _requirement_markdown(db: sqlite3.Connection, source: str) -> str:
    source_title = db.execute("SELECT title FROM requirement_sources WHERE path = ?", (source,)).fetchone()
    lines = [f"# {source_title[0] if source_title else Path(source).stem}", ""]
    for requirement_id, title, body in db.execute("SELECT id, title, body FROM requirements WHERE source = ? ORDER BY id", (source,)):
        lines.extend([f"## {requirement_id} — {title}", body, ""])
    return "\n".join(lines).rstrip() + "\n"


def render_database(db: sqlite3.Connection | None = None) -> None:
    owns_db = db is None
    db = db or sqlite3.connect(ROOT / "requi.db")
    ensure_schema(db)
    expected_terms = {ROOT / path for (path,) in db.execute("SELECT path FROM terms")}
    expected_layers = {ROOT / "layers" / f"{layer_id}.md" for (layer_id,) in db.execute("SELECT id FROM layers")}
    expected_requirements = {ROOT / path for (path,) in db.execute("SELECT path FROM requirement_sources")}
    expected_lexemes = {ROOT / "lexeme" / f"{lexeme_id}.md" for (lexeme_id,) in db.execute("SELECT id FROM lexemes")}
    for path in (ROOT / "terms").glob("*.md"):
        if path not in expected_terms:
            path.unlink()
    for path in (ROOT / "layers").glob("*.md"):
        if path.name != "_layers.md" and path not in expected_layers:
            path.unlink()
    for path in (ROOT / "requirements").glob("*.md"):
        if path not in expected_requirements:
            path.unlink()
    for path in (ROOT / "lexeme").glob("L*.md"):
        if path not in expected_lexemes:
            path.unlink()
    for (path,) in db.execute("SELECT path FROM terms ORDER BY path"):
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_term_markdown(db, path), encoding="utf-8")
    for (layer_id,) in db.execute("SELECT id FROM layers ORDER BY id"):
        (ROOT / "layers" / f"{layer_id}.md").write_text(_layer_markdown(db, layer_id), encoding="utf-8")
    for source, in db.execute("SELECT path FROM requirement_sources ORDER BY path"):
        target = ROOT / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_requirement_markdown(db, source), encoding="utf-8")
    lexeme_rows = db.execute("SELECT id, lemma, language, category FROM lexemes ORDER BY lower(lemma), id").fetchall()
    for lexeme_id, lemma, language, category in lexeme_rows:
        (ROOT / "lexeme" / f"{lexeme_id}.md").write_text(
            f"# {lemma}\n\n- **Wikidata Lexeme:** [{lexeme_id}](https://www.wikidata.org/wiki/{lexeme_id})\n- **Language:** {language}\n- **Lexical category:** {category}\n",
            encoding="utf-8",
        )
    lexeme_entries = "\n".join(f"- [{lemma}]({lexeme_id}.md)" for lexeme_id, lemma, _, _ in lexeme_rows) or "(no lexemes yet)"
    lexeme_index = ROOT / "lexeme" / "_lexeme.md"
    lexeme_index.write_text(f"# Lexemes (Wikidata)\n\nOne file per Wikidata Lexeme: `lexeme/L-#####.md`, linked from term files.\nPopulated from `requi.db`.\n\n<!-- requi:begin lexeme -->\n{lexeme_entries}\n<!-- requi:end -->\n", encoding="utf-8")
    layer_rows = "\n".join(f"- [{title}]({layer_id}.md)" for layer_id, title in db.execute("SELECT id, title FROM layers ORDER BY id")) or "(no layers yet)"
    (ROOT / "layers" / "_layers.md").write_text(f"# Layers\n\n<!-- requi:begin layers -->\n{layer_rows}\n<!-- requi:end -->\n", encoding="utf-8")
    glossary_rows = ["| Term | One-liner | Terms (related) | Requirements |", "|---|---|---|---|"]
    for path, name, definition in db.execute("SELECT path, name, definition FROM terms ORDER BY lower(name)"):
        related = ", ".join(f"[{Path(target).stem}]({target})" for (target,) in db.execute("SELECT related_path FROM term_related WHERE term_path = ? ORDER BY related_path", (path,)))
        requirements = ", ".join(f"[{req_id}](requirements.md#{req_id.lower()})" for (req_id,) in db.execute("SELECT requirement_id FROM term_requirements WHERE term_path = ? ORDER BY requirement_id", (path,)))
        glossary_rows.append(f"| [{name}]({path}) | {definition} | {related} | {requirements} |")
    glossary = ROOT / "glossary.md"
    glossary.write_text(f"# Glossary\n\n<!-- requi:begin glossary -->\n{chr(10).join(glossary_rows)}\n<!-- requi:end -->\n", encoding="utf-8")
    requirement_rows = "\n".join(f"- [{req_id} — {title}]({source}#{req_id.lower()})" for req_id, title, source in db.execute("SELECT id, title, source FROM requirements ORDER BY id")) or "(no requirements yet)"
    (ROOT / "requirements.md").write_text(f"# Requirements\n\n<!-- requi:begin requirements -->\n{requirement_rows}\n<!-- requi:end -->\n", encoding="utf-8")
    if owns_db:
        db.commit()
        db.close()
