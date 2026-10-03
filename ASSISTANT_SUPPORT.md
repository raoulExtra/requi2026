# Assistant support

This project can receive support from the primary coding assistant as well as the local model on Barbara.

## What the primary assistant can do

- Inspect the repository structure and Markdown files.
- Check requirement IDs, statuses, sources, anchors, and cross-links.
- Review proposals returned by the local model.
- Create or update requirement, scope, and term pages.
- Keep `requirements.md`, `glossary.md`, scope indexes, and term back-links synchronized.
- Run read-only consistency checks and report exact failures.
- Open and verify project tools when a user-facing interface is added.

## What the local model can do

Barbara's LM Studio endpoint is available for analysis and subprocess tasks:

- Base URL: `http://barbara:1234/v1`
- Model: `nvidia/nemotron-3-nano-4b`
- Helper: `./requi_assistant.py`

Example:

```sh
./requi_assistant.py "Review all requirements for missing term back-links"
```

## Safe collaboration workflow

1. The primary assistant reads the current repository state.
2. The local model receives a bounded Markdown context and the specific task.
3. The local model returns analysis or proposed Markdown changes.
4. The primary assistant verifies every path, ID, anchor, status, source, and link.
5. Only verified changes are written to this project.
6. A read-only consistency check is run after edits.

The local model and helper are advisory. They do not have permission to silently edit files. Model-generated paths, facts, and links must be checked against the repository because the model may hallucinate content that is not present.

## Project conventions

- Requirement IDs use `REQ-###`; IDs are never reused or renumbered.
- Requirement status is `PROPOSED`, `ACTIVE`, or `RETIRED`.
- Terms are stored in `requi.db` and rendered to `out/terms/<kebab-case-name>.html`; scopes are stored in `requi.db` and rendered to `out/scopes/<scope-id>.html`.
- Keep example content clearly marked or remove it when real project content is added.
