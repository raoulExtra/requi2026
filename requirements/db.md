# Database requirements

## DB-001 — Preserve the live database
- **Status:** ACTIVE
- **Source:** project decision
- **Layer:** db
- **Notes:** Database synchronization MUST NOT drop or recreate the live database. Existing records and unrelated application data MUST remain intact.

## DB-002 — Synchronize Markdown metadata safely
- **Status:** ACTIVE
- **Source:** project decision
- **Layer:** db
- **Notes:** `build` SHOULD use idempotent schema creation and upserts. Repeated builds MUST produce stable records without duplicating relationships.

## DB-003 — Track Wikidata Lexemes in the database
- **Status:** ACTIVE
- **Source:** project decision
- **Layer:** db
- **Notes:** Wikidata Lexeme identifiers, lemmas, language, lexical category, and linked term paths MUST be stored in `requi.db.lexemes`. Markdown and HTML Lexeme indexes MUST be derived from that table.

## DB-004 — Track generated HTML freshness
- **Status:** ACTIVE
- **Source:** project decision
- **Layer:** db
- **Notes:** The database MUST record source hashes for generated site pages so the CLI can report whether HTML regeneration is required.

## DB-005 — Expose semantic name collisions
- **Status:** ACTIVE
- **Source:** project decision
- **Layer:** db
- **Notes:** Database views MUST expose named entities across terms, layers, commands, tables, and views, including case-insensitive name collisions.

## DB-006 — Keep layers out of the term vocabulary
- **Status:** ACTIVE
- **Source:** project decision
- **Layer:** db
- **Notes:** Layers MUST be represented and rendered as layers, never inserted into the `terms` table or displayed as terms in the glossary and term indexes.
