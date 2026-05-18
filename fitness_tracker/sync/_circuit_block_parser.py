"""Pure parser for newline-delimited True Coach Circuit and AMRAP blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

BlockKind = Literal["circuit", "amrap"]
ROUND_SPECIFIC_REP_LADDER_REASON = "round_specific_rep_ladder"

ROUND_COUNT_PATTERN = re.compile(r"\b(?P<count>\d+)\s*rounds?\b", re.IGNORECASE)
AMRAP_PATTERN = re.compile(
    r"\b(?P<minutes>\d+)\s*(?:'|min|mins|minute|minutes)\s*amrap\b",
    re.IGNORECASE,
)
LINE_PREFIX_PATTERN = re.compile(r"^\s*(?:[-*]|\u2022|\d+[\.)])\s*")
REST_LINE_PATTERN = re.compile(r"\brest\b", re.IGNORECASE)
DURATION_PATTERN = re.compile(
    r"\b(?P<value>\d+)\s*(?P<unit>min|mins|minute|minutes|s|sec|secs|second|seconds)\b",
    re.IGNORECASE,
)
ROUND_LADDER_PATTERN = re.compile(r"^\s*round\s+\d+\s*:", re.IGNORECASE)
TARGET_PREFIX_PATTERN = re.compile(
    r"^(?P<target>\d+(?:\s*-\s*\d+)?\s*(?:cal|cals|reps?|m|meters?|km|lengths?|l)?"
    r"(?:\s+(?:each side|es))?)\s+(?P<name>.+)$",
    re.IGNORECASE,
)
TARGET_SUFFIX_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+(?P<target>\d+(?:\s*-\s*\d+)?\s*"
    r"(?:s|sec|secs|second|seconds|min|mins|minute|minutes|m|meters?|km|lengths?|l)"
    r"(?:\s+(?:easy|hard|each side|es))?)$",
    re.IGNORECASE,
)
EACH_SIDE_SUFFIX_PATTERN = re.compile(r"\s+(?P<marker>ES|each side)$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedCircuitMovement:
    """One parsed movement line inside a Circuit or AMRAP block."""

    name: str
    target: str
    source_text: str


@dataclass(frozen=True)
class ParsedCircuitRest:
    """One rest-only instruction line inside a Circuit or AMRAP block."""

    source_text: str
    durations_seconds: list[int]


@dataclass(frozen=True)
class ParsedCircuitMetadataLine:
    """Non-movement line preserved for Agent review."""

    source_text: str


@dataclass(frozen=True)
class ParsedCircuitBlock:
    """Structured parse result for a Coach-authored Circuit or AMRAP block."""

    kind: BlockKind
    round_count: int | None
    amrap_time_cap_seconds: int | None
    movements: list[ParsedCircuitMovement]
    rests: list[ParsedCircuitRest]
    metadata_lines: list[ParsedCircuitMetadataLine]
    requires_agent_decision: bool
    agent_decision_reason: str | None


def parse_circuit_block(name: str, text: str) -> ParsedCircuitBlock | None:
    """Parse a newline-based Circuit or AMRAP prescription.

    Args:
        name (str): True Coach Workout Item name.
        text (str): True Coach Workout Item info/body text.

    Returns:
        ParsedCircuitBlock | None: Parsed block when the text has discernible
        newline-delimited structure, otherwise None.
    """
    lines = [_strip_line_prefix(line) for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None

    combined = f"{name}\n{text}"
    kind: BlockKind = "amrap" if AMRAP_PATTERN.search(combined) else "circuit"
    movements: list[ParsedCircuitMovement] = []
    rests: list[ParsedCircuitRest] = []
    metadata_lines: list[ParsedCircuitMetadataLine] = []
    requires_agent_decision = False
    agent_decision_reason: str | None = None

    for line in lines:
        if _is_round_ladder_line(line):
            metadata_lines.append(ParsedCircuitMetadataLine(source_text=line))
            requires_agent_decision = True
            agent_decision_reason = ROUND_SPECIFIC_REP_LADDER_REASON
            continue
        if _is_rest_line(line):
            rests.append(
                ParsedCircuitRest(
                    source_text=line,
                    durations_seconds=_duration_values_seconds(line),
                )
            )
            continue
        movements.append(_parse_movement_line(line))

    if len(movements) < 2:
        return None

    return ParsedCircuitBlock(
        kind=kind,
        round_count=_round_count(combined),
        amrap_time_cap_seconds=_amrap_time_cap_seconds(combined),
        movements=movements,
        rests=rests,
        metadata_lines=metadata_lines,
        requires_agent_decision=requires_agent_decision,
        agent_decision_reason=agent_decision_reason,
    )


def _strip_line_prefix(line: str) -> str:
    return LINE_PREFIX_PATTERN.sub("", line.strip()).strip()


def _round_count(text: str) -> int | None:
    match = ROUND_COUNT_PATTERN.search(text)
    if match is None:
        return None
    return int(match.group("count"))


def _amrap_time_cap_seconds(text: str) -> int | None:
    match = AMRAP_PATTERN.search(text)
    if match is None:
        return None
    return int(match.group("minutes")) * 60


def _is_round_ladder_line(line: str) -> bool:
    return ROUND_LADDER_PATTERN.search(line) is not None


def _is_rest_line(line: str) -> bool:
    return REST_LINE_PATTERN.search(line) is not None


def _duration_values_seconds(line: str) -> list[int]:
    values: list[int] = []
    for match in DURATION_PATTERN.finditer(line):
        value = int(match.group("value"))
        unit = match.group("unit").lower()
        values.append(value * 60 if unit.startswith("min") else value)
    return values


def _parse_movement_line(line: str) -> ParsedCircuitMovement:
    prefix_match = TARGET_PREFIX_PATTERN.match(line)
    if prefix_match is not None:
        name = prefix_match.group("name").strip()
        target = prefix_match.group("target").strip()
        each_side_match = EACH_SIDE_SUFFIX_PATTERN.search(name)
        if each_side_match is not None:
            name = name[: each_side_match.start()].strip()
            target = f"{target} {each_side_match.group('marker')}"
        return ParsedCircuitMovement(
            name=name,
            target=target,
            source_text=line,
        )

    suffix_match = TARGET_SUFFIX_PATTERN.match(line)
    if suffix_match is not None:
        return ParsedCircuitMovement(
            name=suffix_match.group("name").strip(),
            target=suffix_match.group("target").strip(),
            source_text=line,
        )

    return ParsedCircuitMovement(name=line, target="", source_text=line)
