#!/usr/bin/env python3
"""Derive readable and generator-friendly ASTs from the Requi command catalog."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
import sqlite3


@dataclass(frozen=True)
class ArgumentNode:
    name: str
    kind: str
    flag: str | None
    required: bool
    value_type: str
    description: str
    metavar: str | None


@dataclass(frozen=True)
class CommandNode:
    name: str
    purpose: str
    usage: str
    aliases: tuple[str, ...]
    arguments: tuple[ArgumentNode, ...]


def _usage_arguments(command: str, usage: str) -> list[dict[str, object]]:
    """Read the compact usage grammar used by COMMANDS."""
    tail = usage.split(command, 1)[1].strip() if command in usage else ""
    pieces = re.findall(r"\[[^\]]+\]|--[A-Za-z0-9_-]+(?:\s+[A-Z][A-Za-z0-9_-]*)?|[A-Z][A-Za-z0-9_-]*", tail)
    result: list[dict[str, object]] = []
    for piece in pieces:
        optional = piece.startswith("[") and piece.endswith("]")
        token = piece[1:-1].strip() if optional else piece
        if token.startswith("--"):
            parts = token.split()
            flag = parts[0]
            metavar = parts[1] if len(parts) > 1 else None
            name = flag.removeprefix("--").replace("-", "_")
            result.append({
                "name": name,
                "kind": "option",
                "flag": flag,
                "required": not optional,
                "metavar": metavar,
            })
        else:
            result.append({
                "name": token.lower().replace("-", "_"),
                "kind": "positional",
                "flag": None,
                "required": not optional,
                "metavar": token,
            })
    return result


# REQUI: DB-002 DB-005
def load_commands(db: sqlite3.Connection) -> tuple[CommandNode, ...]:
    commands = db.execute("SELECT name, purpose, usage FROM commands ORDER BY name").fetchall()
    argument_rows = db.execute(
        "SELECT command_name, name, flag, required, value_type, description "
        "FROM command_arguments ORDER BY command_name, rowid"
    ).fetchall()
    metadata = {
        (command, name): {
            "flag": flag if flag != "positional" else None,
            "required": bool(required),
            "value_type": value_type,
            "description": description,
        }
        for command, name, flag, required, value_type, description in argument_rows
    }
    aliases: dict[str, list[str]] = {}
    for command, alias in db.execute("SELECT command_name, alias FROM command_aliases ORDER BY command_name, alias"):
        aliases.setdefault(command, []).append(alias)

    result: list[CommandNode] = []
    for name, purpose, usage in commands:
        arguments: list[ArgumentNode] = []
        for parsed in _usage_arguments(name, usage):
            key = (name, parsed["name"])
            details = metadata.get(key, {})
            flag = details.get("flag", parsed["flag"])
            arguments.append(
                ArgumentNode(
                    name=str(parsed["name"]),
                    kind=str(parsed["kind"]),
                    flag=str(flag) if flag else None,
                    required=bool(details.get("required", parsed["required"])),
                    value_type=str(details.get("value_type", "string")),
                    description=str(details.get("description", "")),
                    metavar=str(parsed["metavar"]) if parsed["metavar"] else None,
                )
            )
        result.append(CommandNode(name, purpose, usage, tuple(aliases.get(name, ())), tuple(arguments)))
    return tuple(result)


def select_commands(commands: tuple[CommandNode, ...], name: str | None) -> tuple[CommandNode, ...]:
    if not name:
        return commands
    for command in commands:
        if command.name == name or name in command.aliases:
            return (command,)
    raise ValueError(f"unknown command: {name}")


def _argument_label(argument: ArgumentNode) -> str:
    if argument.kind == "option":
        label = argument.flag or f"--{argument.name.replace('_', '-')}"
        if argument.metavar:
            label += f" <{argument.metavar}>"
    else:
        label = argument.metavar or argument.name.upper()
    return label + (" (optional)" if not argument.required else "")


def render_tree(commands: tuple[CommandNode, ...]) -> str:
    lines: list[str] = []
    for index, command in enumerate(commands):
        if index:
            lines.append("")
        lines.append(f"command {command.name}")
        lines.append(f"├─ purpose: {command.purpose}")
        lines.append(f"├─ usage: {command.usage}")
        if command.aliases:
            lines.append(f"├─ aliases: {', '.join(command.aliases)}")
        lines.append("└─ arguments:")
        if not command.arguments:
            lines.append("   └─ (none)")
            continue
        for position, argument in enumerate(command.arguments):
            branch = "└─" if position == len(command.arguments) - 1 else "├─"
            details = f" [{argument.value_type}]"
            if argument.description:
                details += f" — {argument.description}"
            lines.append(f"   {branch} {_argument_label(argument)}{details}")
    return "\n".join(lines)


def render_json(commands: tuple[CommandNode, ...]) -> str:
    return json.dumps([asdict(command) for command in commands], indent=2, sort_keys=False)


def _python_string(value: str) -> str:
    return repr(value)


def render_argparse(commands: tuple[CommandNode, ...]) -> str:
    """Emit parser-construction code; dispatch remains project-specific."""
    lines = [
        "# Generated by: ./requi.sh ast --format python",
        "sub = parser.add_subparsers(dest='command', required=True)",
    ]
    for command in commands:
        aliases = f", aliases={command.aliases!r}" if command.aliases else ""
        variable = re.sub(r"\W+", "_", command.name).strip("_") or "command"
        lines.append(f"{variable} = sub.add_parser({_python_string(command.name)}, help={_python_string(command.purpose)}{aliases})")
        for argument in command.arguments:
            if argument.kind == "positional":
                options = [f"metavar={argument.metavar or argument.name.upper()!r}"]
                if not argument.required:
                    options.append("nargs='?'")
                lines.append(f"{variable}.add_argument({_python_string(argument.name)}, {', '.join(options)})")
                continue
            flag = argument.flag or f"--{argument.name.replace('_', '-')}"
            options = [f"dest={argument.name!r}"]
            if argument.required:
                options.append("required=True")
            if argument.metavar:
                options.append(f"metavar={argument.metavar!r}")
            lines.append(f"{variable}.add_argument({_python_string(flag)}, {', '.join(options)})")
    return "\n".join(lines)
