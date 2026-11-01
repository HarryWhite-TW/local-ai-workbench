"""Repository-only reusable document capabilities, backed by existing services.

Run from the repository root: python -B -m src.project_capabilities --help.
The CLI consumes explicitly supplied UTF-8 text on stdin; it never opens a
user-selected path, loads credentials, executes commands, or calls a provider.
Direct Python exports below are the original functions, not copied algorithms.
This developer entry does not connect a new tool to the NEXUS user interface.
"""
from __future__ import annotations

import argparse
import json
import sys

from api.app.services.task_extractors import (
    extract_requirements_v1,
    normalize_requirement_text,
)

__all__ = ["extract_requirements_v1", "normalize_requirement_text"]
MAX_INPUT_BYTES = 1_048_576


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capability", choices=("list", "extract-requirements", "normalize-requirement"))
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.capability == "list":
        result = {
            "scope": "local-ai-workbench developer tools; not NEXUS UI integration",
            "source": "api.app.services.task_extractors",
            "dependencies": "Python standard library; run from repository root",
            "read_only": True,
            "limits": "No filesystem sandbox or execution authority is granted. Extraction uses English headings/modals, not semantic AI.",
            "capabilities": [
                {"name": "extract-requirements", "python": "extract_requirements_v1(content: str, *, file_type=None)",
                 "input": "UTF-8 text on stdin, at most 1 MiB", "output": "JSON {method, items: [{text, source_excerpt, match_reason}]}"},
                {"name": "normalize-requirement", "python": "normalize_requirement_text(text: str)",
                 "input": "UTF-8 text on stdin, at most 1 MiB", "output": "JSON {text: str}"},
            ],
        }
    else:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            parser.error("input exceeds 1 MiB; no result produced")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            parser.error("input must be UTF-8; no result produced")
        result = (extract_requirements_v1(text) if args.capability == "extract-requirements"
                  else {"text": normalize_requirement_text(text)})
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
