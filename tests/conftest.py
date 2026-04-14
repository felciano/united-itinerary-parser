"""Shared pytest fixtures for itinerary parser tests."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_CASES_DIR = REPO_ROOT / "test-cases"
POPCLIP_BUNDLE = REPO_ROOT / "United Itinerary.popclipext"

# Make the PopClip bundle importable as a package path
sys.path.insert(0, str(POPCLIP_BUNDLE))


def _untabify_leading(text: str) -> str:
    """Convert any tabs within each line's leading whitespace to 4 spaces.

    The existing YAML fixtures were authored with tab indentation (sometimes
    mixed with spaces like '  \\t'), which violates the YAML spec. We normalize
    the indentation region without touching embedded tabs in content. 4 spaces
    per tab ensures literal-block content remains indented strictly more than
    the parent key (typically at column 3).
    """
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        i = 0
        while i < len(line) and line[i] in (" ", "\t"):
            i += 1
        indent = line[:i].replace("\t", "    ")
        out.append(indent + line[i:])
    return "".join(out)


def load_yaml_case(filename: str) -> dict[str, Any]:
    """Load a YAML test case from test-cases/.

    Supports two input keys:
    - input_text_block: inline literal block
    - input_text_block_file: sibling filename under test-cases/
    """
    path = TEST_CASES_DIR / filename
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(_untabify_leading(raw))
    if isinstance(data, list):
        data = data[0]
    if "input_text_block_file" in data and "input_text_block" not in data:
        ref = TEST_CASES_DIR / data["input_text_block_file"]
        data["input_text_block"] = ref.read_text(encoding="utf-8")
    return data
