#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from db_source import (
    ensure_schema,
    import_markdown,
    markdown_database_differences,
    render_database,
    _layer_markdown,
    _scope_markdown,
    _term_markdown,
)
from command_ast import load_commands, render_argparse, render_json, render_tree, select_commands

ROOT = Path(__file__).resolve().parents[1]




def render() -> None:
    db = sqlite3.connect(ROOT / "requi.db")
    try:
        ensure_schema(db)
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS commands(name TEXT PRIMARY KEY, purpose TEXT, usage TEXT);
            CREATE TABLE IF NOT EXISTS command_arguments(
                command_name TEXT, name TEXT, flag TEXT, required INTEGER, value_type TEXT, description TEXT,
                PRIMARY KEY(command_name, name)
            );
            CREATE TABLE IF NOT EXISTS command_aliases(command_name TEXT, alias TEXT PRIMARY KEY);
            """
        )
        command_data(db)
        render_database(db)
        db.commit()
    finally:
        db.close()
    subprocess.run([sys.executable, str(ROOT / "tools" / "site.py")], check=True)
COMMANDS = (
    ("build", "Import Markdown once, synchronize SQLite, and render the site", "./requi.sh build"),
    ("render", "Render the SQLite source of truth into Markdown projections and HTML", "./requi.sh render"),
    ("check", "Check Markdown, SQLite, and generated references for consistency", "./requi.sh check"),
    ("status", "Report generated HTML freshness", "./requi.sh status"),
    ("q", "Run a read-only SQL query against requi.db", "./requi.sh q SQL"),
    ("db", "Inspect database-backed entities or source state", "./requi.sh db ACTION [ENTITY]"),
    ("add-term", "Create a term in SQLite and render its HTML page", "./requi.sh add-term NAME --definition TEXT [--layer ID] [--scope ID]"),
    ("list-terms", "List all database terms and HTML routes", "./requi.sh list-terms"),
    ("show-term", "Display one database term as Markdown", "./requi.sh show-term NAME"),
    ("update-term", "Update a term in SQLite and render its HTML page", "./requi.sh update-term NAME [--definition TEXT] [--layer ID] [--scope ID]"),
    ("delete-term", "Delete a term from SQLite and rebuild HTML", "./requi.sh delete-term NAME"),
    ("add-scope", "Create a scope in SQLite and render its HTML page", "./requi.sh add-scope NAME [--description TEXT]"),
    ("list-scopes", "List all database scopes and HTML routes", "./requi.sh list-scopes"),
    ("show-scope", "Display one database scope as Markdown", "./requi.sh show-scope NAME"),
    ("update-scope", "Update a scope in SQLite and render its HTML page", "./requi.sh update-scope NAME [--description TEXT]"),
    ("delete-scope", "Delete an unused scope from SQLite and rebuild HTML", "./requi.sh delete-scope NAME"),
    ("add", "Create a term, layer, or scope using the compact command", "./requi.sh add ENTITY NAME [--definition TEXT] [--layer ID] [--scope ID]"),
    ("create", "Create a supported entity", "./requi.sh create ENTITY NAME"),
    ("read", "Read a supported entity or database view", "./requi.sh read ENTITY [NAME]"),
    ("update", "Update a supported entity", "./requi.sh update ENTITY NAME"),
    ("delete", "Delete a supported entity", "./requi.sh delete ENTITY NAME"),
    ("list", "List a supported entity or database view", "./requi.sh list ENTITY"),
    ("upd", "Short alias for update-term", "./requi.sh upd NAME [--definition TEXT] [--layer ID] [--scope ID]"),
    ("del", "Short alias for delete-term", "./requi.sh del NAME"),
    ("ast", "Inspect command structure or emit parser-construction code", "./requi.sh ast [COMMAND] [--format FORMAT]"),
)
COMMAND_ALIASES = (("delete", "del"), ("update", "upd"))
COMMAND_ARGUMENTS = (
    ("add-term", "name", "positional", 1, "string", "Display name"),
    ("add-term", "definition", "--definition", 1, "string", "One-line definition"),
    ("add-term", "layer", "--layer", 0, "layer-id", "Layer ID, for example data"),
    ("add-term", "scope", "--scope", 0, "scope-id", "Scope ID; repeat for multiple scopes"),
    ("show-term", "name", "positional", 1, "string", "Term display name"),
    ("update-term", "name", "positional", 1, "string", "Term display name"),
    ("update-term", "definition", "--definition", 0, "string", "Replacement definition"),
    ("update-term", "layer", "--layer", 0, "layer-id", "Replacement layer"),
    ("update-term", "scope", "--scope", 0, "scope-id", "Replacement scopes; repeat for multiple scopes"),
    ("delete-term", "name", "positional", 1, "string", "Term display name"),
    ("add-scope", "name", "positional", 1, "string", "Scope name"),
    ("add-scope", "description", "--description", 0, "string", "Scope description"),
    ("show-scope", "name", "positional", 1, "string", "Scope name"),
    ("update-scope", "name", "positional", 1, "string", "Scope name"),
    ("update-scope", "description", "--description", 0, "string", "Replacement description"),
    ("delete-scope", "name", "positional", 1, "string", "Scope name"),
    ("ast", "name", "positional", 0, "command", "Command name; omit for all commands"),
    ("ast", "format", "--format", 0, "enum", "tree, json, or python"),
    ("q", "sql", "positional", 1, "sql", "Read-only SQL query"),
    ("db", "action", "positional", 1, "enum", "list or status"),
    ("db", "entity", "positional", 0, "enum", "Currently lexemes for db list"),
    ("add", "entity", "positional", 1, "enum", "term, layer, or scope"),
    ("add", "name", "positional", 1, "string", "Entity name; remaining words are accepted for term names"),
    ("add", "definition", "--definition", 0, "string", "Term definition"),
    ("add", "layer", "--layer", 0, "layer-id", "Layer ID"),
    ("add", "scope", "--scope", 0, "scope-id", "Scope ID; repeat for multiple scopes"),
    ("create", "entity", "positional", 1, "enum", "term, layer, or scope"),
    ("create", "name", "positional", 1, "string", "Entity name"),
    ("create", "definition", "--definition", 0, "string", "Term definition"),
    ("create", "description", "--description", 0, "string", "Layer or scope description"),
    ("create", "layer", "--layer", 0, "layer-id", "Layer ID"),
    ("create", "scope", "--scope", 0, "scope-id", "Scope ID; repeat for multiple scopes"),
    ("read", "entity", "positional", 1, "enum", "term, layer, scope, or view"),
    ("read", "name", "positional", 0, "string", "Entity name, when required"),
    ("update", "entity", "positional", 1, "enum", "term, layer, or scope"),
    ("update", "name", "positional", 1, "string", "Entity name"),
    ("update", "definition", "--definition", 0, "string", "Replacement term definition"),
    ("update", "description", "--description", 0, "string", "Replacement layer or scope description"),
    ("update", "layer", "--layer", 0, "layer-id", "Replacement layer"),
    ("update", "scope", "--scope", 0, "scope-id", "Replacement scopes; repeat for multiple scopes"),
    ("delete", "entity", "positional", 1, "enum", "term, layer, or scope"),
    ("delete", "name", "positional", 1, "string", "Entity name"),
    ("list", "entity", "positional", 1, "enum", "term, scope, layer, lexeme, or view"),
    ("upd", "name", "positional", 1, "string", "Term name"),
    ("upd", "definition", "--definition", 0, "string", "Replacement definition"),
    ("upd", "layer", "--layer", 0, "layer-id", "Replacement layer"),
    ("upd", "scope", "--scope", 0, "scope-id", "Replacement scopes; repeat for multiple scopes"),
    ("del", "name", "positional", 1, "string", "Term name"),
)


def command_data(db: sqlite3.Connection) -> None:
    for name, purpose, usage in COMMANDS:
        db.execute("INSERT OR REPLACE INTO commands VALUES (?, ?, ?)", (name, purpose, usage))
    for command, name, flag, required, value_type, description in COMMAND_ARGUMENTS:
        db.execute(
            "INSERT OR REPLACE INTO command_arguments VALUES (?, ?, ?, ?, ?, ?)",
            (command, name, flag, required, value_type, description),
        )
    for command, alias in COMMAND_ALIASES:
        db.execute("INSERT OR REPLACE INTO command_aliases VALUES (?, ?)", (command, alias))

# REQUI: DB-001 DB-002 DB-004 DB-005 DB-006
def build() -> None:
    db = sqlite3.connect(ROOT / "requi.db")
    ensure_schema(db)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS commands(name TEXT PRIMARY KEY, purpose TEXT, usage TEXT);
        CREATE TABLE IF NOT EXISTS command_arguments(
            command_name TEXT, name TEXT, flag TEXT, required INTEGER, value_type TEXT, description TEXT,
            PRIMARY KEY(command_name, name)
        );
        CREATE TABLE IF NOT EXISTS command_aliases(command_name TEXT, alias TEXT PRIMARY KEY);
        DROP VIEW IF EXISTS v_name_collisions;
        DROP VIEW IF EXISTS v_entities;
        DROP VIEW IF EXISTS v_commands;
        """
    )
    source_mode = db.execute("SELECT value FROM requi_state WHERE key = 'source_mode'").fetchone()
    migrated = not source_mode or source_mode[0] != "sqlite"
    if migrated:
        import_markdown(db)
    command_data(db)
    db.execute(
        "CREATE VIEW v_commands AS "
        "SELECT c.name, c.purpose, c.usage, a.name AS argument, a.flag, a.required, "
        "a.value_type, a.description FROM commands c "
        "LEFT JOIN command_arguments a ON a.command_name = c.name"
    )
    db.executescript(
        """
        CREATE VIEW v_entities AS
        SELECT 'term' AS kind, name, path AS source FROM terms
        UNION ALL SELECT 'scope', name, 'scopes/' || id || '.md' FROM scopes
        UNION ALL SELECT 'layer', id, 'layers/' || id || '.md' FROM layers
        UNION ALL SELECT 'db-table', name, 'sqlite table' FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        UNION ALL SELECT 'command', name, 'commands' FROM commands
        UNION ALL SELECT 'view', name, 'sqlite view' FROM sqlite_master WHERE type = 'view';
        CREATE VIEW v_name_collisions AS
        SELECT lower(name) AS normalized_name, COUNT(*) AS match_count,
            group_concat(kind || ':' || source, ' | ') AS matches
        FROM v_entities GROUP BY lower(name) HAVING COUNT(*) > 1;
        """
    )
    db.commit()
    db.close()
    if migrated:
        render()
def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    if not slug:
        raise ValueError("name produces an empty identifier")
    return slug


def source_db() -> sqlite3.Connection:
    db = sqlite3.connect(ROOT / "requi.db")
    ensure_schema(db)
    source_mode = db.execute("SELECT value FROM requi_state WHERE key = 'source_mode'").fetchone()
    if not source_mode or source_mode[0] != "sqlite":
        db.close()
        build()
        db = sqlite3.connect(ROOT / "requi.db")
        ensure_schema(db)
    return db


def term_path(name: str) -> Path:
    db = source_db()
    row = db.execute("SELECT path FROM terms WHERE lower(name) = lower(?)", (name,)).fetchone()
    db.close()
    return ROOT / row[0] if row else ROOT / "terms" / f"{slugify(name)}.md"

def scope_ids(db: sqlite3.Connection, names: list[str]) -> list[str]:
    ids: list[str] = []
    for name in names:
        row = db.execute(
            "SELECT id FROM scopes WHERE lower(id) = lower(?) OR lower(name) = lower(?)",
            (name, name),
        ).fetchone()
        if not row:
            raise ValueError(f"unknown scope: {name}")
        if row[0] not in ids:
            ids.append(row[0])
    return ids


def scope_route(scope_id: str) -> str:
    return (Path("out") / "scopes" / f"{scope_id}.html").as_posix()


def add_scope(name: str, description: str) -> None:
    scope_id = slugify(name)
    db = source_db()
    if db.execute("SELECT 1 FROM scopes WHERE id = ? OR lower(name) = lower(?)", (scope_id, name)).fetchone():
        db.close()
        raise ValueError(f"scope already exists: {scope_id}")
    db.execute("INSERT INTO scopes(id, name, description) VALUES (?, ?, ?)", (scope_id, name, description))
    db.commit()
    db.close()
    render()
    print(scope_route(scope_id))


def list_scopes() -> None:
    db = source_db()
    for scope_id, name in db.execute("SELECT id, name FROM scopes ORDER BY lower(name), id"):
        print(f"{name}\t{scope_route(scope_id)}")
    db.close()


def show_scope(name: str) -> None:
    db = source_db()
    row = db.execute(
        "SELECT id FROM scopes WHERE lower(id) = lower(?) OR lower(name) = lower(?)",
        (name, name),
    ).fetchone()
    if not row:
        db.close()
        raise ValueError(f"scope not found: {name}")
    print(_scope_markdown(db, row[0]), end="")
    db.close()


def update_scope(name: str, description: str | None) -> None:
    db = source_db()
    row = db.execute(
        "SELECT id FROM scopes WHERE lower(id) = lower(?) OR lower(name) = lower(?)",
        (name, name),
    ).fetchone()
    if not row:
        db.close()
        raise ValueError(f"scope not found: {name}")
    if description is not None:
        db.execute("UPDATE scopes SET description = ? WHERE id = ?", (description, row[0]))
    db.commit()
    db.close()
    render()


def delete_scope(name: str) -> None:
    db = source_db()
    row = db.execute(
        "SELECT id FROM scopes WHERE lower(id) = lower(?) OR lower(name) = lower(?)",
        (name, name),
    ).fetchone()
    if not row:
        db.close()
        raise ValueError(f"scope not found: {name}")
    scope_id = row[0]
    used_by_terms = db.execute("SELECT 1 FROM term_scopes WHERE scope_id = ? LIMIT 1", (scope_id,)).fetchone()
    used_by_requirements = db.execute("SELECT 1 FROM requirement_sources WHERE scope_id = ? LIMIT 1", (scope_id,)).fetchone()
    if used_by_terms or used_by_requirements:
        db.close()
        raise ValueError(f"scope is in use: {scope_id}")
    db.execute("DELETE FROM scopes WHERE id = ?", (scope_id,))
    db.commit()
    db.close()
    render()


def add_term(name: str, definition: str, layer: str | None, scopes: list[str] | None = None) -> None:
    path = term_path(name)
    db = source_db()
    if db.execute("SELECT 1 FROM terms WHERE lower(name) = lower(?)", (name,)).fetchone():
        db.close()
        raise ValueError(f"term already exists: out/{path.relative_to(ROOT).with_suffix('.html').as_posix()}")
    if layer and not db.execute("SELECT 1 FROM layers WHERE id = ?", (layer,)).fetchone():
        db.close()
        raise ValueError(f"unknown layer: {layer}")
    scope_ids_to_add = scope_ids(db, scopes or [])
    relative = path.relative_to(ROOT).as_posix()
    db.execute("INSERT INTO terms(path, name, definition) VALUES (?, ?, ?)", (relative, name, definition))
    if layer:
        db.execute("INSERT INTO term_layers(term_path, layer_id) VALUES (?, ?)", (relative, layer))
    for scope_id in scope_ids_to_add:
        db.execute("INSERT INTO term_scopes(term_path, scope_id) VALUES (?, ?)", (relative, scope_id))
    db.commit()
    db.close()
    render()
    print((Path("out") / path.relative_to(ROOT).with_suffix(".html")).as_posix())


def list_terms() -> None:
    db = source_db()
    for name, path in db.execute("SELECT name, path FROM terms ORDER BY lower(name), path"):
        print(f"{name}\t{(Path('out') / Path(path).with_suffix('.html')).as_posix()}")
    db.close()


def show_term(name: str) -> None:
    db = source_db()
    row = db.execute("SELECT path FROM terms WHERE lower(name) = lower(?)", (name,)).fetchone()
    if not row:
        db.close()
        raise ValueError(f"term not found: {name}")
    print(_term_markdown(db, row[0]), end="")
    db.close()


def update_term(
    name: str,
    definition: str | None,
    layer: str | None,
    scopes: list[str] | None = None,
) -> None:
    db = source_db()
    row = db.execute("SELECT path FROM terms WHERE lower(name) = lower(?)", (name,)).fetchone()
    if not row:
        db.close()
        raise ValueError(f"term not found: {name}")
    if definition is not None:
        db.execute("UPDATE terms SET definition = ? WHERE path = ?", (definition, row[0]))
    if layer is not None:
        if not db.execute("SELECT 1 FROM layers WHERE id = ?", (layer,)).fetchone():
            db.close()
            raise ValueError(f"unknown layer: {layer}")
        db.execute("DELETE FROM term_layers WHERE term_path = ?", (row[0],))
        db.execute("INSERT INTO term_layers(term_path, layer_id) VALUES (?, ?)", (row[0], layer))
    if scopes is not None:
        scope_ids_to_set = scope_ids(db, scopes)
        db.execute("DELETE FROM term_scopes WHERE term_path = ?", (row[0],))
        for scope_id in scope_ids_to_set:
            db.execute("INSERT INTO term_scopes(term_path, scope_id) VALUES (?, ?)", (row[0], scope_id))
    db.commit()
    db.close()
    render()


def delete_term(name: str) -> None:
    db = source_db()
    row = db.execute("SELECT path FROM terms WHERE lower(name) = lower(?)", (name,)).fetchone()
    if not row:
        db.close()
        raise ValueError(f"term not found: {name}")
    relative = row[0]
    db.execute("DELETE FROM term_layers WHERE term_path = ?", (relative,))
    db.execute("DELETE FROM term_scopes WHERE term_path = ?", (relative,))
    db.execute("DELETE FROM term_requirements WHERE term_path = ?", (relative,))
    db.execute("DELETE FROM term_related WHERE term_path = ? OR related_path = ?", (relative, relative))
    db.execute("DELETE FROM terms WHERE path = ?", (relative,))
    db.commit()
    db.close()
    render()


def layer_path(name: str) -> Path:
    return ROOT / "layers" / f"{slugify(name)}.md"


def create_layer(name: str, description: str) -> None:
    layer_id = slugify(name)
    db = source_db()
    if db.execute("SELECT 1 FROM layers WHERE id = ?", (layer_id,)).fetchone():
        db.close()
        raise ValueError(f"layer already exists: {layer_id}")
    db.execute("INSERT INTO layers(id, title, description) VALUES (?, ?, ?)", (layer_id, layer_id, description))
    db.commit()
    db.close()
    render()


def list_layers() -> None:
    db = source_db()
    for layer_id, title in db.execute("SELECT id, title FROM layers ORDER BY id"):
        print(f"{title}\t{ROOT / 'layers' / (layer_id + '.md')}")
    db.close()


def list_lexemes() -> None:
    db = source_db()
    for row in db.execute(
        "SELECT id, lemma, language, category, COALESCE(term_path, '') "
        "FROM lexemes ORDER BY lower(lemma), id"
    ):
        print("\t".join(str(value) for value in row))
    db.close()
def db_status() -> None:
    db = source_db()
    for key, value in db.execute("SELECT key, value FROM requi_state ORDER BY key"):
        print(f"{key}\t{value}")
    db.close()


def read_layer(name: str) -> None:
    db = source_db()
    layer_id = slugify(name)
    if not db.execute("SELECT 1 FROM layers WHERE id = ?", (layer_id,)).fetchone():
        db.close()
        raise ValueError(f"layer not found: {name}")
    print(_layer_markdown(db, layer_id), end="")
    db.close()


def update_layer(name: str, description: str | None) -> None:
    db = source_db()
    layer_id = slugify(name)
    if not db.execute("SELECT 1 FROM layers WHERE id = ?", (layer_id,)).fetchone():
        db.close()
        raise ValueError(f"layer not found: {name}")
    if description is not None:
        db.execute("UPDATE layers SET description = ? WHERE id = ?", (description, layer_id))
    db.commit()
    db.close()
    render()


def delete_layer(name: str) -> None:
    db = source_db()
    layer_id = slugify(name)
    if not db.execute("SELECT 1 FROM layers WHERE id = ?", (layer_id,)).fetchone():
        db.close()
        raise ValueError(f"layer not found: {name}")
    if db.execute("SELECT 1 FROM term_layers WHERE layer_id = ? LIMIT 1", (layer_id,)).fetchone():
        db.close()
        raise ValueError(f"layer is still assigned to terms: {name}")
    db.execute("DELETE FROM layers WHERE id = ?", (layer_id,))
    db.commit()
    db.close()
    render()


def list_db_views() -> None:
    db = sqlite3.connect(ROOT / "requi.db")
    for name, sql in db.execute("SELECT name, sql FROM sqlite_master WHERE type = 'view' ORDER BY name"):
        print(f"{name}\t{sql}")
    db.close()




def check() -> int:
    errors: list[str] = []
    db = source_db()
    state = db.execute("SELECT value FROM requi_state WHERE key = 'source_mode'").fetchone()
    if not state or state[0] != "sqlite":
        errors.append("requi_state source_mode is not sqlite")
    term_paths = {path for (path,) in db.execute("SELECT path FROM terms")}
    layer_ids = {layer_id for (layer_id,) in db.execute("SELECT id FROM layers")}
    scope_ids_set = {scope_id for (scope_id,) in db.execute("SELECT id FROM scopes")}
    requirement_ids = {requirement_id for (requirement_id,) in db.execute("SELECT id FROM requirements")}
    for path in term_paths:
        for (layer_id,) in db.execute("SELECT layer_id FROM term_layers WHERE term_path = ?", (path,)):
            if layer_id not in layer_ids:
                errors.append(f"{path}: missing layer {layer_id}")
        for (scope_id,) in db.execute("SELECT scope_id FROM term_scopes WHERE term_path = ?", (path,)):
            if scope_id not in scope_ids_set:
                errors.append(f"{path}: missing scope {scope_id}")
        for (requirement_id,) in db.execute("SELECT requirement_id FROM term_requirements WHERE term_path = ?", (path,)):
            if requirement_id not in requirement_ids:
                errors.append(f"{path}: missing requirement {requirement_id}")
        for (related_path,) in db.execute("SELECT related_path FROM term_related WHERE term_path = ?", (path,)):
            if related_path not in term_paths:
                errors.append(f"{path}: missing related term {related_path}")
    for (scope_id,) in db.execute("SELECT scope_id FROM requirement_sources WHERE scope_id IS NOT NULL"):
        if scope_id not in scope_ids_set:
            errors.append(f"requirement source: missing scope {scope_id}")
    for layer_id in layer_ids:
        if not (ROOT / "layers" / f"{layer_id}.md").exists():
            errors.append(f"missing generated layer: layers/{layer_id}.md")
    if not (ROOT / "requirements.md").exists():
        errors.append("missing generated requirements.md")
    referenced = db.execute("SELECT COUNT(DISTINCT requirement_id) FROM term_requirements").fetchone()[0]
    errors.extend(markdown_database_differences(db))
    db.close()
    if errors:
        print("CHECK FAILED")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(
        f"CHECK OK: {len(term_paths)} terms, {len(layer_ids)} layers, "
        f"{len(scope_ids_set)} scopes, {referenced} referenced requirements"
    )
    return 0
def site_status() -> int:
    return subprocess.run([sys.executable, str(ROOT / "tools" / "site.py"), "--status"], check=False).returncode

def command_catalog() -> dict[str, tuple[str, str]]:
    if not (ROOT / "requi.db").exists():
        build()
    db = sqlite3.connect(ROOT / "requi.db")
    try:
        rows = db.execute("SELECT name, purpose, usage FROM v_commands GROUP BY name ORDER BY name").fetchall()
    except sqlite3.OperationalError:
        db.close()
        build()
        db = sqlite3.connect(ROOT / "requi.db")
        rows = db.execute("SELECT name, purpose, usage FROM v_commands GROUP BY name ORDER BY name").fetchall()
    db.close()
    return {name: (purpose, usage) for name, purpose, usage in rows}


def main() -> int:
    catalog = command_catalog()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    sub.add_parser("render")
    sub.add_parser("check")
    sub.add_parser("status")
    query = sub.add_parser("q")
    ast = sub.add_parser("ast", help="Inspect command structure or emit parser-construction code")
    ast.add_argument("name", nargs="?")
    ast.add_argument("--format", choices=("tree", "json", "python"), default="tree")
    query.add_argument("sql")
    database = sub.add_parser("db", help="Inspect database-backed entities")
    database_sub = database.add_subparsers(dest="db_action", required=True)
    database_list = database_sub.add_parser("list", help="List database entities")
    database_list.add_argument("entity", choices=["lexemes"])
    database_sub.add_parser("status", help="Show SQLite source-of-truth state")
    add = sub.add_parser("add-term", help=catalog["add-term"][0])
    add.add_argument("name")
    add.add_argument("--definition", required=True)
    add.add_argument("--layer")
    add.add_argument("--scope", action="append")
    add_scope_parser = sub.add_parser("add-scope", help="Create a scope in SQLite and render its HTML page")
    add_scope_parser.add_argument("name")
    add_scope_parser.add_argument("--description", default="")
    add_short = sub.add_parser("add")
    add_short.add_argument("name", nargs="+")
    add_short.add_argument("--definition", default="")
    add_short.add_argument("--layer")
    add_short.add_argument("--scope", action="append")
    listing = sub.add_parser("list-terms", help=catalog["list-terms"][0])
    listing.set_defaults()
    list_scopes_parser = sub.add_parser("list-scopes", help="List all database scopes and HTML routes")
    list_scopes_parser.set_defaults()
    show = sub.add_parser("show-term", help=catalog["show-term"][0])
    show.add_argument("name")
    show_scope_parser = sub.add_parser("show-scope", help="Display one database scope as Markdown")
    show_scope_parser.add_argument("name")
    update = sub.add_parser("update-term", help=catalog["update-term"][0])
    update.add_argument("name")
    update.add_argument("--definition")
    update.add_argument("--layer")
    update.add_argument("--scope", action="append")
    update_scope_parser = sub.add_parser("update-scope", help="Update a scope in SQLite and render its HTML page")
    update_scope_parser.add_argument("name")
    update_scope_parser.add_argument("--description")
    delete = sub.add_parser("delete-term", help=catalog["delete-term"][0])
    delete.add_argument("name")
    delete_scope_parser = sub.add_parser("delete-scope", help="Delete an unused scope from SQLite and rebuild HTML")
    delete_scope_parser.add_argument("name")
    create = sub.add_parser("create")
    create.add_argument("entity", choices=["term", "layer", "scope"])
    create.add_argument("name")
    create.add_argument("--definition")
    create.add_argument("--description")
    create.add_argument("--layer")
    create.add_argument("--scope", action="append")
    read = sub.add_parser("read")
    read.add_argument("entity", choices=["term", "layer", "scope", "view"])
    read.add_argument("name", nargs="?")
    update = sub.add_parser("update")
    update.add_argument("entity", choices=["term", "layer", "scope"])
    update.add_argument("name")
    update.add_argument("--definition")
    update.add_argument("--description")
    update.add_argument("--layer")
    update.add_argument("--scope", action="append")
    delete = sub.add_parser("delete")
    delete.add_argument("entity", choices=["term", "layer", "scope"])
    delete.add_argument("name")
    list_entity = sub.add_parser("list")
    list_entity.add_argument("entity", choices=["term", "layer", "scope", "lexeme", "view"])
    upd = sub.add_parser("upd")
    upd.add_argument("name")
    upd.add_argument("--definition")
    upd.add_argument("--layer")
    upd.add_argument("--scope", action="append")
    short_delete = sub.add_parser("del")
    short_delete.add_argument("name", nargs="+")
    args = parser.parse_args()
    if args.command == "ast":
        db = sqlite3.connect(ROOT / "requi.db")
        try:
            commands = select_commands(load_commands(db), args.name)
        except ValueError as exc:
            db.close()
            parser.error(str(exc))
        db.close()
        renderer = {"tree": render_tree, "json": render_json, "python": render_argparse}[args.format]
        print(renderer(commands))
        return 0
    if args.command == "db":
        if args.db_action == "list" and args.entity == "lexemes":
            list_lexemes()
            return 0
        if args.db_action == "status":
            db_status()
            return 0
    if args.command == "add" and args.name and args.name[0].casefold() == "lexeme":
        if len(args.name) != 3:
            raise ValueError("usage: add lexeme LEMMA CATEGORY")
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" / "wikidata.py"), "--lexeme", args.name[1], "--category", args.name[2], "--apply"],
            check=False,
        ).returncode
    if args.command == "add":
        if args.name and args.name[0].casefold() == "lexeme":
            raise ValueError("use add lexeme LEMMA CATEGORY")
        if args.name and args.name[0].casefold() == "layer":
            if len(args.name) < 2:
                raise ValueError("usage: add layer NAME")
            create_layer(" ".join(args.name[1:]), args.definition)
            return 0
        if args.name and args.name[0].casefold() == "scope":
            if len(args.name) < 2:
                raise ValueError("usage: add scope NAME")
            add_scope(" ".join(args.name[1:]), args.definition)
            return 0
        if args.name and args.name[0].casefold() == "term":
            if len(args.name) < 2:
                raise ValueError("usage: add term NAME")
            name = " ".join(args.name[1:])
        else:
            name = " ".join(args.name)
        add_term(name, args.definition, args.layer, args.scope)
        return 0
    if args.command == "del":
        delete_term(" ".join(args.name))
        return 0
    if args.command == "upd":
        update_term(args.name, args.definition, args.layer, args.scope)
        return 0
    if args.command == "create":
        if args.entity == "term":
            add_term(args.name, args.definition or "", args.layer, args.scope)
        elif args.entity == "layer":
            create_layer(args.name, args.description or "")
        else:
            add_scope(args.name, args.description or "")
        return 0
    if args.command == "read":
        if args.entity == "term":
            show_term(args.name)
        elif args.entity == "layer":
            read_layer(args.name)
        elif args.entity == "scope":
            show_scope(args.name)
        else:
            list_db_views()
        return 0
    if args.command == "update":
        if args.entity == "term":
            update_term(args.name, args.definition, args.layer, args.scope)
        elif args.entity == "layer":
            update_layer(args.name, args.description)
        else:
            update_scope(args.name, args.description)
        return 0
    if args.command == "delete":
        if args.entity == "term":
            delete_term(args.name)
        elif args.entity == "layer":
            delete_layer(args.name)
        else:
            delete_scope(args.name)
        return 0
    if args.command == "list":
        {
            "term": list_terms,
            "scope": list_scopes,
            "layer": list_layers,
            "lexeme": list_lexemes,
            "view": list_db_views,
        }[args.entity]()
        return 0
    if args.command == "build":
        build()
    elif args.command == "render":
        render()
    elif args.command == "check":
        return check()
    elif args.command == "status":
        return site_status()
    elif args.command == "q":
        db = sqlite3.connect(ROOT / "requi.db")
        for row in db.execute(args.sql):
            print("\t".join("" if value is None else str(value) for value in row))
        db.close()
    elif args.command == "add-term":
        add_term(args.name, args.definition, args.layer, args.scope)
    elif args.command == "list-terms":
        list_terms()
    elif args.command == "show-term":
        show_term(args.name)
    elif args.command == "update-term":
        update_term(args.name, args.definition, args.layer, args.scope)
    elif args.command == "delete-term":
        delete_term(args.name)
    elif args.command == "add-scope":
        add_scope(args.name, args.description)
    elif args.command == "list-scopes":
        list_scopes()
    elif args.command == "show-scope":
        show_scope(args.name)
    elif args.command == "update-scope":
        update_scope(args.name, args.description)
    elif args.command == "delete-scope":
        delete_scope(args.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
