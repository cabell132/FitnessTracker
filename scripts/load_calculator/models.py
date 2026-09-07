"""Validated interpreted inputs and review output for the local experiment."""

from datetime import date
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

type Load = Annotated[float, Field(ge=0, allow_inf_nan=False)]
type PositiveReps = Annotated[int, Field(gt=0, strict=True)]
type Index = Annotated[int, Field(ge=0, strict=True)]


class Record(BaseModel):
    """Reject unknown fields rather than discard interpretation evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Context(Record):
    """Agent-resolved identity, role, and execution used for comparability."""

    exercise_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    role: Literal["working", "preparatory", "unknown"]
    execution: str = Field(min_length=1)


class Effort(Record):
    """One ordered effort; null rep bounds preserve open-ended prescriptions."""

    round: Index
    part: Index
    lower_reps: PositiveReps | None = None
    upper_reps: PositiveReps | None = None
    coach_load_kg: Load | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Require either ordered numeric bounds or an unresolved target.

        Returns:
            Self: Validated effort.

        Raises:
            ValueError: Rep bounds are incomplete or reversed.
        """
        if (self.lower_reps is None) != (self.upper_reps is None) or (
            self.lower_reps is not None
            and self.upper_reps is not None
            and self.upper_reps < self.lower_reps
        ):
            message = "Rep bounds must both be null or satisfy lower <= upper."
            raise ValueError(message)
        return self


class Prescription(Record):
    """Preserve ordered rounds and parts, plus original Coach instructions."""

    structure: Literal["straight", "ladder", "drop", "unsupported"]
    efforts: tuple[Effort, ...] = Field(min_length=1)
    instructions: str = ""

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        """Reject duplicate effort identities.

        Returns:
            Self: Validated prescription.

        Raises:
            ValueError: Two efforts share a round/part identity.
        """
        if len({(e.round, e.part) for e in self.efforts}) != len(self.efforts):
            message = "Each effort needs a unique round/part identity."
            raise ValueError(message)
        return self


class LoadOption(Record):
    """An equipment label and its explicitly confirmed recording aliases."""

    label: str = Field(min_length=1)
    weight_kg: Load
    recorded_aliases_kg: tuple[Load, ...] = ()


class Equipment(Record):
    """Known load options and confirmed adjacent steps; no inferred increments."""

    setup_id: str = Field(min_length=1)
    recording_convention: str = Field(min_length=1)
    options: tuple[LoadOption, ...]
    steps: tuple[tuple[Load, Load], ...] = ()
    inventory_complete: bool = False

    @model_validator(mode="after")
    def validate_options(self) -> Self:
        """Require unambiguous aliases and real, adjacent ascending steps.

        Returns:
            Self: Validated equipment.

        Raises:
            ValueError: Options, aliases, or step declarations conflict.
        """
        weights = [o.weight_kg for o in self.options]
        aliases = [a for o in self.options for a in {o.weight_kg, *o.recorded_aliases_kg}]
        if weights != sorted(set(weights)) or len(aliases) != len(set(aliases)):
            message = "Options must be sorted and unique, with unambiguous recording aliases."
            raise ValueError(message)
        adjacent = set(pairwise(weights))
        if not set(self.steps) <= adjacent:
            message = "Confirmed steps must join adjacent known options in ascending order."
            raise ValueError(message)
        return self


class PerformedEffort(Record):
    """One observed effort; missing records remain missing."""

    round: Index
    part: Index
    recorded_kg: Load | None
    reps: Annotated[int, Field(ge=0, strict=True)] | None
    rpe: Annotated[int, Field(ge=1, le=10, strict=True)] | None = None


class Performance(Record):
    """One sourced exposure with explicit interpretation of normal conditions."""

    evidence_id: str = Field(min_length=1)
    performed_on: date
    context: Context
    prescription: Prescription
    conditions: Literal["normal", "interrupted", "substitution", "unknown"]
    results: tuple[PerformedEffort, ...]
    preceding_context: str = ""


class Calculation(Record):
    """A local calculation request; no database or remote services required."""

    evaluation_date: date
    context: Context
    prescription: Prescription
    equipment: Equipment
    history: tuple[Performance, ...] = ()
    preceding_context: str = ""

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        """Reject mismatched equipment and duplicated evidence identifiers.

        Returns:
            Self: Validated calculation.

        Raises:
            ValueError: Equipment identity or evidence identifiers conflict.
        """
        if self.context.setup_id != self.equipment.setup_id:
            message = "Requested setup must match the equipment inventory."
            raise ValueError(message)
        if len({h.evidence_id for h in self.history}) != len(self.history):
            message = "Performance evidence identifiers must be unique."
            raise ValueError(message)
        return self


class CandidateEffort(Record):
    """A candidate recorded load, linked back to the full interpreted effort."""

    effort: Effort
    weight_kg: Load | None
    equipment_label: str | None = None
    source: Literal["coach", "policy", "unresolved"]


class Recommendation(Record):
    """Experimental review artifact, including unresolved decisions."""

    schema_version: Literal[1] = 1
    experimental: Literal[True] = True
    request: Calculation
    efforts: tuple[CandidateEffort, ...]
    evidence_ids: tuple[str, ...]
    reason: str
    explanation: str
    provisional: bool = False
    unresolved: tuple[str, ...] = ()
