# OMA Requirements — Home

Jump between **terms** (glossary), **scopes** (semantic and requirement grouping), **layers** (architecture), and **software requirements**.

## Layout
| File | Purpose |
|---|---|
| [glossary.md](glossary.md) | A–Z index of all terms |
| [terms/](terms/) | Database-backed HTML page for each term; term records are stored only in `requi.db` |
| [scopes/_scopes.md](scopes/_scopes.md) | Scope index; scopes group terms and requirement categories |
| [layers/_layers.md](layers/_layers.md) | Architecture overview + generated jump table |
| [layers/frontend.md](layers/frontend.md) … | One file per layer: terms, requirements, code paths |
| [Lexeme index](lexemes/_lexemes.md) | One file per Wikidata Lexeme `L-#####` |
| [code.python/](code.python/index.html) | Database-backed catalog of Python source files and their responsibilities |
| [scopes/code.sh](scopes/code.sh.md) | Database-backed `./requi.sh` command and argument reference |
| [scopes/code.python](scopes/code.python.md) | Python source scope within the `code` layer |
| [requirements.md](requirements.md) | Scope index for requirement categories; source pages are listed under `requirements/` |
| [requirements/](requirements/) | Requirement sources, including general project conventions under `requirements/general/` |
| `requi.db` | Canonical semantic graph and migration state; `build` performs the one-time Markdown import, then SQLite drives projections and site rendering |
| [command_ast.md](command_ast.md) | Command AST views and generated `argparse` parser code |

## Conventions

### Term pages
#### Structure
H1 = display name.

#### Sections
- `## Definition`
- `## Scopes`
- `## Layers`
- `## Related terms`
- `## Requirements`

#### Metadata
Optional `> **Wikidata:** Q-###` and `> **Lexeme:** L-####` lines.

#### Storage
The record is stored in SQLite and rendered to `out/terms/<kebab-name>.html`; no term Markdown file is required.

### Scope pages
- **Storage:** Scopes are SQLite records rendered to `out/scopes/<scope-id>.html`.
- **Contents:** Each page lists assigned terms and requirement categories.
- **Commands:** Manage scopes with `add-scope`, `list-scopes`, `show-scope`, `update-scope`, and `delete-scope`.

### Bidirectional links
- **Maintain:** Keep both term ↔ scope, term ↔ requirement (`REQ-###`), and term ↔ layer links.
- **Check:** Run the consistency check to report orphaned links.
- **Diagnostics:** Inspect `v_term_orphans` and `v_layer_orphans` for details.

### Python requirement annotations
Add `# REQUI: DB-001 DB-004` to a Python source line to make its core requirement links collectable. The generated source page links each annotation to the requirement acceptance criterion, and each requirement page links back to the annotated line.
