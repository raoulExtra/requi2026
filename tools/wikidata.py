#!/usr/bin/env python3
"""Resolve Wikidata items and Lexemes with batched, rate-limited SPARQL queries."""
from __future__ import annotations

import argparse
import json
import os
import time
import sqlite3
from pathlib import Path
from db_source import ensure_schema, render_database
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
LANGUAGES = {"en": "Q1860"}
LEXICAL_CATEGORIES = {"verb": "Q24905", "noun": "Q1084", "adjective": "Q34698"}
USER_AGENT = os.environ.get(
    "WIKIDATA_USER_AGENT",
    "requi-metadata-helper/1.0 (local requirements graph; set WIKIDATA_USER_AGENT with contact)",
)
RETRYABLE = {429, 500, 502, 503, 504}


def sparql(query: str) -> list[dict[str, str]]:
    request = Request(
        SPARQL_ENDPOINT,
        data=urlencode({"query": query, "format": "json"}).encode(),
        headers={
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    for attempt in range(4):
        try:
            with urlopen(request, timeout=60) as response:
                bindings = json.load(response)["results"]["bindings"]
            return [{key: value["value"] for key, value in row.items()} for row in bindings]
        except HTTPError as error:
            if error.code not in RETRYABLE or attempt == 3:
                raise
            retry_after = error.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after else 2**attempt)
    return []


def literal(value: str, language: str = "en") -> str:
    return json.dumps(value) + f"@{language}"


def find_lexemes(lemmas: list[str], language: str, category: str) -> dict[str, str]:
    values = " ".join(literal(lemma, language) for lemma in sorted(set(lemmas)))
    query = f"""SELECT ?lemma ?lexeme WHERE {{
      VALUES ?lemma {{ {values} }}
      ?lexeme a ontolex:LexicalEntry ; wikibase:lemma ?lemma ;
               dct:language wd:{LANGUAGES[language]} ;
               wikibase:lexicalCategory wd:{LEXICAL_CATEGORIES[category]} .
    }}"""
    return {row["lemma"]: row["lexeme"].rsplit("/", 1)[-1] for row in sparql(query)}


def find_items(labels: list[str]) -> dict[str, tuple[str, str]]:
    values = " ".join(literal(label) for label in sorted(set(labels)))
    query = f"""SELECT ?label ?item ?description WHERE {{
      VALUES ?label {{ {values} }}
      ?item rdfs:label ?label .
      OPTIONAL {{ ?item schema:description ?description . FILTER(LANG(?description) = "en") }}
    }}"""
    matches: dict[str, tuple[str, str]] = {}
    for row in sparql(query):
        matches.setdefault(row["label"], (row["item"].rsplit("/", 1)[-1], row.get("description", "")))
    return matches


def write_lexeme(lemma: str, lexeme_id: str, language: str, category: str) -> None:
    db = sqlite3.connect(ROOT / "requi.db")
    ensure_schema(db)
    term = db.execute("SELECT path FROM terms WHERE lower(name) = lower(?)", (lemma,)).fetchone()
    term_path = term[0] if term else None
    db.execute(
        "INSERT OR REPLACE INTO lexemes(id, lemma, language, category, term_path) VALUES (?, ?, ?, ?, ?)",
        (lexeme_id, lemma, language, category, term_path),
    )
    if term_path:
        db.execute("UPDATE terms SET lexeme_id = ?, lexeme_pending = 0 WHERE path = ?", (lexeme_id, term_path))
    db.commit()
    render_database(db)
    db.commit()
    db.close()


def write_item(term_path: str, qid: str) -> None:
    db = sqlite3.connect(ROOT / "requi.db")
    ensure_schema(db)
    db.execute("UPDATE terms SET wikidata_id = ? WHERE path = ?", (qid, term_path))
    db.commit()
    render_database(db)
    db.commit()
    db.close()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write exact matches")
    parser.add_argument("--lexeme", help="find one Lexeme by lemma")
    parser.add_argument("--language", default="en", choices=sorted(LANGUAGES))
    parser.add_argument("--category", default="verb", choices=sorted(LEXICAL_CATEGORIES))
    args = parser.parse_args()

    if args.lexeme:
        matches = find_lexemes([args.lexeme], args.language, args.category)
        lexeme_id = matches.get(args.lexeme)
        if not lexeme_id:
            print(f"UNRESOLVED lexeme: {args.lexeme} ({args.language}, {args.category})")
            return 1
        print(f"{args.lexeme} ({args.language}, {args.category}) -> {lexeme_id}")
        if args.apply:
            write_lexeme(args.lexeme, lexeme_id, args.language, args.category)
        return 0

    candidates: list[tuple[Path, str]] = []
    db = sqlite3.connect(ROOT / "requi.db")
    ensure_schema(db)
    for path, label in db.execute("SELECT path, name FROM terms WHERE lexeme_pending = 1 ORDER BY path"):
        candidates.append((ROOT / path, label))
    db.close()
    matches = find_items([label for _, label in candidates]) if candidates else {}
    unresolved = 0
    for path, label in candidates:
        result = matches.get(label)
        if result is None:
            print(f"UNRESOLVED {path}: {label}")
            unresolved += 1
            continue
        qid, description = result
        print(f"{path.relative_to(ROOT)}: {qid} — {description}")
        if args.apply:
            write_item(path.relative_to(ROOT).as_posix(), qid)
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
