#!/usr/bin/env python3
"""Detect intra-file code duplication on Write/Edit.

PostToolUse hook that analyzes Python and Markdown files for structural
duplication after every write or edit. Reports findings via additionalContext
so the agent sees them immediately and can self-correct.

Detection strategy:
  - Python: AST-based function body comparison + text-based repeated blocks
  - Markdown: repeated section structures (headers with similar content)

Design constraints:
  - Fires on every Write|Edit — must be fast (<500ms)
  - PostToolUse cannot block — advisory only (exit 0 unconditionally)
  - Intra-file only — cross-module analysis is the verifier's job (LLM-judged)
  - Conservative thresholds to minimize false positives
"""

import ast
import json
import os
import sys
from collections import defaultdict
from difflib import SequenceMatcher

# Minimum lines for a block to be considered a duplication candidate
MIN_BLOCK_LINES = 5
# Minimum similarity ratio for two blocks to be flagged
SIMILARITY_THRESHOLD = 0.85


def _analyze_python(file_path: str) -> list[str]:
    """Find duplicate patterns in a Python file using AST analysis."""
    findings = []

    with open(file_path) as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings

    # Strategy 1: Compare function/method bodies for structural similarity
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body_lines = _extract_body_lines(source, node)
            if len(body_lines) >= MIN_BLOCK_LINES:
                functions.append((node.name, node.lineno, node.end_lineno, body_lines))

    for i, (name_a, start_a, end_a, body_a) in enumerate(functions):
        for name_b, start_b, end_b, body_b in functions[i + 1 :]:
            ratio = SequenceMatcher(None, body_a, body_b).ratio()
            if ratio >= SIMILARITY_THRESHOLD:
                pct = int(ratio * 100)
                findings.append(
                    f"Similar functions: {name_a}() at lines {start_a}-{end_a} "
                    f"and {name_b}() at lines {start_b}-{end_b} "
                    f"are {pct}% structurally similar"
                )

    # Strategy 2: Detect repeated consecutive code blocks (non-function level)
    lines = source.splitlines()
    findings.extend(_find_repeated_blocks(lines))

    return findings


def _extract_body_lines(source: str, node: ast.AST) -> list[str]:
    """Extract normalized body lines from a function node."""
    lines = source.splitlines()
    if node.end_lineno is None:
        return []
    body_lines = lines[node.lineno : node.end_lineno]
    # Normalize: strip leading whitespace for comparison
    return [line.strip() for line in body_lines if line.strip()]


def _find_repeated_blocks(lines: list[str]) -> list[str]:
    """Find repeated text blocks of MIN_BLOCK_LINES or more consecutive lines."""
    findings = []
    stripped = [line.strip() for line in lines]
    n = len(stripped)

    # Sliding window: find blocks that appear more than once
    seen_blocks: dict[tuple[str, ...], int] = {}

    for start in range(n - MIN_BLOCK_LINES + 1):
        block = tuple(stripped[start : start + MIN_BLOCK_LINES])
        # Skip blocks that are mostly empty or trivial
        non_empty = [
            line for line in block if line and line not in ("", "pass", "return", "}", "]", ")")
        ]
        if len(non_empty) < MIN_BLOCK_LINES - 1:
            continue

        if block in seen_blocks:
            first_line = seen_blocks[block]
            # Only report each pair once
            if first_line != start:
                findings.append(
                    f"Repeated block: lines {first_line + 1}-{first_line + MIN_BLOCK_LINES} "
                    f"and lines {start + 1}-{start + MIN_BLOCK_LINES} "
                    f"share {MIN_BLOCK_LINES}+ identical lines"
                )
                # Prevent re-reporting the same block
                seen_blocks[block] = start
        else:
            seen_blocks[block] = start

    return findings


def _analyze_markdown(file_path: str) -> list[str]:
    """Find duplicate patterns in a Markdown file."""
    findings = []

    with open(file_path) as f:
        lines = f.readlines()

    # Strategy: detect repeated section content under different headers
    sections: dict[str, list[tuple[str, int]]] = defaultdict(list)
    current_header = None
    current_content: list[str] = []
    current_start = 0

    for i, line in enumerate(lines):
        if line.startswith("#"):
            if current_header and len(current_content) >= MIN_BLOCK_LINES:
                content_key = "\n".join(entry.strip() for entry in current_content if entry.strip())
                sections[content_key].append((current_header, current_start))
            current_header = line.strip()
            current_content = []
            current_start = i + 1
        else:
            current_content.append(line)

    # Flush last section
    if current_header and len(current_content) >= MIN_BLOCK_LINES:
        content_key = "\n".join(entry.strip() for entry in current_content if entry.strip())
        sections[content_key].append((current_header, current_start))

    for _content, headers in sections.items():
        if len(headers) > 1:
            locations = ", ".join(f'"{h}" (line {s})' for h, s in headers)
            findings.append(f"Duplicate section content under: {locations}")

    # Also check for repeated blocks across the whole file
    findings.extend(_find_repeated_blocks([line.rstrip() for line in lines]))

    return findings


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path or not os.path.isfile(file_path):
        return

    # Only analyze Python and Markdown files
    findings = []
    if file_path.endswith(".py"):
        findings = _analyze_python(file_path)
    elif file_path.endswith(".md"):
        findings = _analyze_markdown(file_path)
    else:
        return

    if not findings:
        return

    basename = os.path.basename(file_path)
    header = f"[duplication] {len(findings)} finding(s) in {basename}:"
    details = "\n".join(f"  - {f}" for f in findings)
    msg = f"{header}\n{details}"

    print(json.dumps({"additionalContext": msg}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Fail open — never block agent execution
        pass
