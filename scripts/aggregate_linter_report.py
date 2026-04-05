"""Parse linter-analysis-output.txt into JSON + markdown summaries with per-directory rollups."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
ARROW_RE = re.compile(r"-->\s+(.+?):(\d+):(\d+)\s*$")
WOULD_REFORMAT_RE = re.compile(r"Would reformat:\s*(.+?)\s*$")
PYDOC_FILE_RE = re.compile(r"^(fitness_tracker[/\\].+\.py)\s*$")
PYDOC_VIOLATION_RE = re.compile(r"^\s*(\d+):\s+(DOC\d+):")
SLOPPY_ISSUE_RE = re.compile(
    r"^\s{2}(fitness_tracker[/\\][^:\s]+)\s*:\s*(\d+)\s+\S"
)


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def norm_path(p: str) -> str:
    p = strip_ansi(p).strip()
    return p.replace("\\", "/")


def split_sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("=" * 20) and i + 2 < n:
            title = lines[i + 1].strip()
            if i + 2 < n and lines[i + 2].startswith("=" * 20):
                i += 3
                buf: list[str] = []
                while i < n and not (
                    lines[i].startswith("=" * 20)
                    and i + 2 < n
                    and lines[i + 2].startswith("=" * 20)
                ):
                    if lines[i].startswith("--- exit code:"):
                        i += 1
                        break
                    buf.append(lines[i])
                    i += 1
                sections.append((title, buf))
                continue
        i += 1
    return sections


def parse_ruff_check(body: list[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for raw in body:
        line = strip_ansi(raw)
        m = ARROW_RE.search(line)
        if m:
            counts[norm_path(m.group(1))] += 1
    return dict(counts)


def parse_ruff_format(body: list[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for raw in body:
        line = strip_ansi(raw)
        m = WOULD_REFORMAT_RE.match(line)
        if m:
            counts[norm_path(m.group(1))] += 1
    return dict(counts)


def parse_ty(body: list[str]) -> dict[str, int]:
    """One issue per error[/warning[ block (ty may print multiple `-->` for one diagnostic)."""
    counts: dict[str, int] = defaultdict(int)
    i = 0
    while i < len(body):
        line = strip_ansi(body[i])
        ls = line.lstrip()
        if ls.startswith("error[") or ls.startswith("warning["):
            j = i + 1
            primary: str | None = None
            while j < len(body):
                lj = strip_ansi(body[j])
                if j > i and (
                    lj.lstrip().startswith("error[")
                    or lj.lstrip().startswith("warning[")
                ):
                    break
                m = ARROW_RE.search(lj)
                if m is not None and primary is None:
                    primary = norm_path(m.group(1))
                j += 1
            if primary is not None:
                counts[primary] += 1
            i = j
            continue
        i += 1
    return dict(counts)


def parse_pydoclint(body: list[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    i = 0
    while i < len(body):
        line = body[i]
        stripped = line.strip()
        if "System.Management.Automation.RemoteException" in line:
            i += 1
            continue
        m = PYDOC_FILE_RE.match(stripped)
        if m:
            j = i + 1
            while j < len(body) and not body[j].strip():
                j += 1
            if j < len(body) and PYDOC_VIOLATION_RE.match(body[j]):
                path = norm_path(m.group(1))
                while j < len(body) and PYDOC_VIOLATION_RE.match(body[j]):
                    counts[path] += 1
                    j += 1
                i = j
                continue
        i += 1
    return dict(counts)


def parse_pip_audit(body: list[str]) -> dict[str, int]:
    """One pseudo-issue per vulnerable package (no source file path)."""
    counts: dict[str, int] = defaultdict(int)
    in_table = False
    for raw in body:
        line = strip_ansi(raw).rstrip()
        if line.startswith("Name ") and "Version" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("Name ") and "Skip Reason" in line:
            break
        if not line.strip() or line.startswith("----"):
            continue
        parts = line.split()
        pkg = parts[0]
        if pkg == "Name":
            continue
        counts[f"(dependency) {pkg}"] += 1
    return dict(counts)


def parse_sloppylint(body: list[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for raw in body:
        line = strip_ansi(raw)
        m = SLOPPY_ISSUE_RE.match(line)
        if m:
            counts[norm_path(m.group(1))] += 1
    return dict(counts)


def parse_slop_detector(body: list[str]) -> dict[str, int]:
    """Count flagged rows in the text table (filename may be short, e.g. base.py)."""
    counts: dict[str, int] = defaultdict(int)
    flag_re = re.compile(
        r"^\s+(\S+\.py)\b.*\b(SUSPICIOUS|DEPENDENCY_NOISE)\b",
    )
    for raw in body:
        line = strip_ansi(raw)
        m = flag_re.match(line)
        if m:
            counts[f"(slop-detector) {m.group(1)}"] += 1
    return dict(counts)


def section_router(title: str) -> str | None:
    t = title.upper()
    if "RUFF CHECK" in t:
        return "ruff_check"
    if "RUFF FORMAT" in t:
        return "ruff_format"
    if t.strip().startswith("TY ") or "TY (" in t:
        return "ty"
    if "PYDOCLINT" in t:
        return "pydoclint"
    if "PIP-AUDIT" in t or "PIP-AUDIT" in title:
        return "pip_audit"
    if "SLOPPYLINT" in t:
        return "sloppylint"
    if "SLOP DETECTOR" in t or "SLOP-DETECTOR" in t:
        return "slop_detector"
    return None


def build_tree(paths_counts: dict[str, int]) -> dict[str, Any]:
    """Nested tree: each node has name, total (rollup under subtree), direct_files, subdirs."""

    def make_node(name: str) -> dict[str, Any]:
        return {"name": name, "total": 0, "direct_files": {}, "subdirs": {}}

    root = make_node(".")

    for rel, cnt in sorted(paths_counts.items(), key=lambda x: x[0]):
        parts = [p for p in norm_path(rel).split("/") if p]
        if not parts:
            root["total"] += cnt
            continue
        node = root
        node["total"] += cnt
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            if is_last:
                df = node["direct_files"]
                df[part] = df.get(part, 0) + cnt
            else:
                sd = node["subdirs"]
                if part not in sd:
                    sd[part] = make_node(part)
                node = sd[part]
                node["total"] += cnt
    return root


def rollup_list(node: dict[str, Any], path_prefix: str = "") -> list[dict[str, Any]]:
    """Depth-first rows: each directory once (rollup), then each file under it."""
    rows: list[dict[str, Any]] = []
    name = node["name"]
    if name == ".":
        cur = path_prefix
    else:
        cur = f"{path_prefix}/{name}".strip("/") if path_prefix else name

    if name != ".":
        rows.append(
            {
                "path": cur,
                "issues": node["total"],
                "kind": "directory",
                "n_subdirs": len(node["subdirs"]),
                "n_files_here": len(node["direct_files"]),
            }
        )
    for sub in sorted(node["subdirs"].values(), key=lambda x: x["name"]):
        rows.extend(rollup_list(sub, cur))
    for fname, c in sorted(node["direct_files"].items()):
        fpath = f"{cur}/{fname}".strip("/")
        rows.append(
            {
                "path": fpath,
                "issues": c,
                "kind": "file",
                "n_subdirs": 0,
                "n_files_here": 0,
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path("linter-analysis-output.txt"),
        help="Plain-text linter report",
    )
    ap.add_argument(
        "-o",
        "--json-out",
        type=Path,
        default=Path("linter-analysis-summary.json"),
    )
    ap.add_argument(
        "-m",
        "--md-out",
        type=Path,
        default=Path("linter-analysis-summary.md"),
    )
    args = ap.parse_args()

    text = args.input.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    sections = split_sections(lines)

    parsers = {
        "ruff_check": parse_ruff_check,
        "ruff_format": parse_ruff_format,
        "ty": parse_ty,
        "pydoclint": parse_pydoclint,
        "pip_audit": parse_pip_audit,
        "sloppylint": parse_sloppylint,
        "slop_detector": parse_slop_detector,
    }

    by_linter: dict[str, dict[str, int]] = {}
    for title, body in sections:
        key = section_router(title)
        if key and key in parsers:
            by_linter[key] = parsers[key](body)

    summary_tools: dict[str, dict[str, Any]] = {}
    combined: dict[str, int] = defaultdict(int)
    for tool, fcounts in by_linter.items():
        total = sum(fcounts.values())
        summary_tools[tool] = {
            "issues": total,
            "files_touched": len(fcounts),
        }
        for fp, c in fcounts.items():
            combined[fp] += c

    grand = sum(summary_tools[t]["issues"] for t in summary_tools)

    trees_tool: dict[str, Any] = {
        tool: build_tree(fc) for tool, fc in by_linter.items()
    }
    tree_combined = build_tree(dict(combined))

    rollup_combined = rollup_list(tree_combined)
    rollup_by_linter = {t: rollup_list(trees_tool[t]) for t in trees_tool}

    out: dict[str, Any] = {
        "meta": {
            "source_report": str(args.input.as_posix()),
            "generated_utc": datetime.now(timezone.utc).isoformat(),
        },
        "totals_by_linter": summary_tools,
        "grand_total_issues": grand,
        "per_linter_file_counts": by_linter,
        "trees_by_linter": trees_tool,
        "combined_tree": tree_combined,
        "rollups": {
            "combined": rollup_combined,
            "by_linter": rollup_by_linter,
        },
        "combined_flat_by_file": dict(sorted(combined.items(), key=lambda x: (-x[1], x[0]))),
    }

    args.json_out.write_text(
        json.dumps(out, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    md_lines = [
        "# Linter report summary",
        "",
        f"Generated from `{args.input.as_posix()}`.",
        "",
        "## Totals by tool",
        "",
        "| Tool | Issues | Files affected |",
        "|------|-------:|---------------:|",
    ]
    for tool in sorted(summary_tools.keys()):
        s = summary_tools[tool]
        md_lines.append(f"| {tool} | {s['issues']} | {s['files_touched']} |")
    md_lines.append(f"| **combined (sum)** | **{grand}** | **{len(combined)}** |")
    md_lines.extend(
        [
            "",
            "## Combined tree (directories + files, depth-first)",
            "",
            "| Path | Kind | Issues (rollup for dirs) | Subdirs | Files here |",
            "|------|------|--------------------------|---------|------------|",
        ]
    )
    for row in rollup_combined:
        md_lines.append(
            f"| `{row['path']}` | {row['kind']} | {row['issues']} | "
            f"{row['n_subdirs']} | {row['n_files_here']} |"
        )
    md_lines.extend(
        [
            "",
            "Per-tool rollups live in `rollups.by_linter` in the JSON file.",
            "",
            "## Per-tool top files (up to 15 each)",
            "",
        ]
    )
    for tool in sorted(by_linter.keys()):
        md_lines.append(f"### {tool}")
        md_lines.extend(["| File | Issues |", "|------|-------:|"])
        items = sorted(by_linter[tool].items(), key=lambda x: (-x[1], x[0]))[:15]
        for fp, c in items:
            md_lines.append(f"| `{fp}` | {c} |")
        md_lines.append("")

    args.md_out.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.json_out} and {args.md_out}")


if __name__ == "__main__":
    main()
