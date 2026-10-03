#!/usr/bin/env python3
"""Ask a local OpenAI-compatible model about this requirements project."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DEFAULT_URL = os.environ.get("LM_STUDIO_URL", "http://barbara:1234/v1")
DEFAULT_MODEL = os.environ.get("LM_MODEL", "nvidia/nemotron-3-nano-4b")
CALL_LOG = ROOT / "last_model_call.md"
SYSTEM_PROMPT = """You are a requirements-engineering assistant working on a local Markdown project.

Project rules:
- Requirements use IDs REQ-### and are never reused or renumbered.
- Each requirement has Status (PROPOSED, ACTIVE, or RETIRED) and Source.
- Terms live in terms/<kebab-case-name>.md.
- Requirement links to terms and terms link back to requirements.
- Keep requirements.md, glossary.md, and related term pages synchronized.
- Do not invent facts or silently edit files.

Review the supplied project context. Answer the user's request with concrete file paths,
requirement IDs, and Markdown where useful. If a change is needed, propose it explicitly;
do not claim that files were changed. The assistant itself is read-only.
"""


def project_context(max_chars: int) -> str:
    files = sorted(
        path for path in ROOT.rglob("*")
        if path.is_file() and path.name != Path(__file__).name
        and ".git" not in path.parts
    )
    chunks: list[str] = []
    used = 0
    for path in files:
        relative = path.relative_to(ROOT)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        chunk = f"\n--- {relative} ---\n{text}\n"
        if used + len(chunk) > max_chars:
            chunks.append(f"\n--- {relative} ---\n[omitted: context limit reached]\n")
            break
        chunks.append(chunk)
        used += len(chunk)
    return "".join(chunks) or "[project has no readable files]"


def ask_model(base_url: str, model: str, request: str, context: str) -> str:
    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 1200,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Project context:\n{context}\n\nUser request:\n{request}"},
        ],
    }
    endpoint = base_url.rstrip("/") + "/chat/completions"
    http_request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(http_request, timeout=120) as response:
        result = json.load(response)
    return result["choices"][0]["message"]["content"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", nargs="+", help="Question or requirements task")
    parser.add_argument("--url", default=DEFAULT_URL, help="LM Studio OpenAI-compatible base URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model ID served by LM Studio")
    parser.add_argument("--max-context", type=int, default=120_000, help="Maximum context characters")
    args = parser.parse_args()

    request_text = " ".join(args.request)
    try:
        answer = ask_model(args.url, args.model, request_text, project_context(args.max_context))
    except Exception as error:
        parser.error(f"model request failed: {error}")
    timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    CALL_LOG.write_text(
        f"# Last local model call\n\n"
        f"- **UTC time:** `{timestamp}`\n"
        f"- **Model:** `{args.model}`\n"
        f"- **Endpoint:** `{args.url.rstrip('/')}`\n"
        f"- **Request:** {request_text}\n",
        encoding="utf-8",
    )
    print(f"[local model call: {timestamp} UTC | {args.model}]")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
