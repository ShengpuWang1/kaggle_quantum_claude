"""Workspace-confined tools exposed to research agents."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import jsonschema

from .config import ROOT
from .providers import ToolCall, ToolSpec


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


class ToolContext:
    def __init__(
        self,
        workspace: Path,
        *,
        writable: bool,
        read_root: Path = ROOT,
        max_output_chars: int = 30000,
    ):
        self.workspace = workspace.resolve()
        self.read_root = read_root.resolve()
        self.writable = writable
        self.max_output_chars = max_output_chars
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._handlers = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "search_text": self._search_text,
            "write_file": self._write_file,
            "edit_file": self._edit_file,
        }
        self._schemas = {
            "list_files": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "pattern": {"type": "string", "default": "*"},
                },
                "additionalProperties": False,
            },
            "read_file": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            "search_text": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "pattern": {"type": "string"},
                    "glob": {"type": "string", "default": "*.py"},
                },
                "required": ["path", "pattern"],
                "additionalProperties": False,
            },
            "write_file": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            "edit_file": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
                "additionalProperties": False,
            },
        }

    def specs(self) -> list[ToolSpec]:
        descriptions = {
            "list_files": "List files below a permitted directory using a glob pattern.",
            "read_file": "Read a UTF-8 text file with optional zero-based line offset.",
            "search_text": "Search permitted text files with a regular expression.",
            "write_file": "Create or replace a UTF-8 file inside the experiment workspace.",
            "edit_file": "Replace one unique exact string in a workspace text file.",
        }
        names = ["list_files", "read_file", "search_text"]
        if self.writable:
            names += ["write_file", "edit_file"]
        return [
            ToolSpec(name, descriptions[name], self._schemas[name]) for name in names
        ]

    def execute(self, call: ToolCall) -> ToolResult:
        handler = self._handlers.get(call.name)
        if handler is None or (call.name in {"write_file", "edit_file"} and not self.writable):
            return ToolResult(f"Tool is not available: {call.name}", True)
        try:
            jsonschema.validate(call.arguments, self._schemas[call.name])
            result = handler(call.arguments)
            return ToolResult(self._bound(result))
        except Exception as exc:  # noqa: BLE001 - tool errors return to the model
            return ToolResult(self._bound(f"{type(exc).__name__}: {exc}"), True)

    def _bound(self, text: str) -> str:
        if len(text) <= self.max_output_chars:
            return text
        omitted = len(text) - self.max_output_chars
        return text[: self.max_output_chars] + f"\n... [{omitted} characters omitted]"

    @staticmethod
    def _blocked(path: Path) -> bool:
        blocked = {".secrets", ".venv", ".python", ".cache", ".git"}
        return any(part in blocked for part in path.parts)

    def _resolve(self, value: str, *, write: bool = False, must_exist: bool = True) -> Path:
        if not value:
            value = "."
        supplied = Path(value).expanduser()
        path = supplied if supplied.is_absolute() else self.workspace / supplied
        path = path.resolve()
        if self._blocked(path):
            raise PermissionError("Secret and environment paths are not accessible")
        if write:
            path.relative_to(self.workspace)
        else:
            path.relative_to(self.read_root)
        if must_exist and not path.exists():
            raise FileNotFoundError(path)
        if must_exist and path.is_symlink():
            raise PermissionError("Symlinks are not accessible")
        return path

    def _list_files(self, args: dict) -> str:
        base = self._resolve(args.get("path", "."))
        pattern = args.get("pattern", "*")
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ValueError("Glob must stay below the selected directory")
        entries = []
        for path in sorted(base.glob(pattern)):
            if self._blocked(path) or path.is_symlink():
                continue
            entries.append(str(path.relative_to(self.read_root)))
            if len(entries) >= 300:
                break
        return "\n".join(entries) or "No matching files"

    def _read_file(self, args: dict) -> str:
        path = self._resolve(args["path"])
        if not path.is_file() or path.stat().st_size > 4_000_000:
            raise ValueError("Only text files up to 4 MB can be read")
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        offset = args.get("offset", 0)
        limit = args.get("limit", 500)
        selected = lines[offset : offset + limit]
        body = "\n".join(f"{index + 1}\t{line}" for index, line in enumerate(selected, offset))
        if offset + limit < len(lines):
            body += f"\n... [{len(lines) - offset - limit} more lines]"
        return body

    def _search_text(self, args: dict) -> str:
        base = self._resolve(args["path"])
        regex = re.compile(args["pattern"])
        files = [base] if base.is_file() else sorted(base.glob(args.get("glob", "*.py")))
        matches = []
        for path in files:
            if not path.is_file() or path.is_symlink() or path.stat().st_size > 4_000_000:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(lines, 1):
                if regex.search(line):
                    matches.append(f"{path.relative_to(self.read_root)}:{number}:{line}")
                    if len(matches) >= 200:
                        return "\n".join(matches)
        return "\n".join(matches) or "No matches"

    def _write_file(self, args: dict) -> str:
        path = self._resolve(args["path"], write=True, must_exist=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = args["content"]
        temporary = path.with_name(f".{path.name}.agent-tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
        return f"Wrote {path.relative_to(self.workspace)} ({len(content)} characters)"

    def _edit_file(self, args: dict) -> str:
        path = self._resolve(args["path"], write=True)
        text = path.read_text(encoding="utf-8")
        old = args["old_string"]
        if text.count(old) != 1:
            raise ValueError(f"old_string occurs {text.count(old)} times; expected exactly one")
        updated = text.replace(old, args["new_string"], 1)
        temporary = path.with_name(f".{path.name}.agent-tmp")
        temporary.write_text(updated, encoding="utf-8")
        os.replace(temporary, path)
        return f"Edited {path.relative_to(self.workspace)}"


def terminal_spec(role: str, schema: dict) -> ToolSpec:
    names = {
        "director": "submit_plan",
        "implementer": "finish_implementation",
        "reviewer": "submit_review",
    }
    return ToolSpec(
        names[role],
        f"Submit the final structured {role} result and end this role session.",
        schema,
    )


def terminal_name(role: str) -> str:
    return {
        "director": "submit_plan",
        "implementer": "finish_implementation",
        "reviewer": "submit_review",
    }[role]


def pretty_json(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"
