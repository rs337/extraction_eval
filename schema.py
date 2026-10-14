"""Workout schema: the single definition used for ground truth, extraction output, storage and scoring.

Field meanings and cross-field rules live in SCHEMA.md. Update that file when this schema changes.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

Intensity = Literal["easy", "float", "half_marathon_pace", "marathon_pace", "tempo"]

LeafType = Literal["warmup", "cooldown", "work", "rest", "stride"]
class Leaf(BaseModel):
    """A single step: no nesting, no reps."""
    model_config = ConfigDict(extra="forbid")
    type: LeafType
    distance_km: Optional[float] = Field(None, gt=0)
    duration_s: Optional[int] = Field(None, gt=0)
    intensity: Optional[Intensity] = None
    pace_s_per_km: Optional[int] = Field(None, ge=150, le=600)
    optional: bool = False
    note: Optional[str] = None
    @model_validator(mode="after")
    def check_rules(self) -> "Leaf":
        if self.distance_km is not None and self.duration_s is not None:
            raise ValueError("a step has distance or duration, not both")
        return self
class Repeat(BaseModel):
    """A group repeated `reps` times. It can only contain Leaf steps."""
    model_config = ConfigDict(extra="forbid")
    type: Literal["repeat"]
    reps: int = Field(ge=2)
    rest_between_s: Optional[int] = Field(None, gt=0)
    optional: bool = False
    note: Optional[str] = None
    steps: list[Leaf] = Field(min_length=1, max_length=6)
Step = Annotated[Union[Leaf, Repeat], Field(discriminator="type")]

class Workout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    date: date
    session_label: str
    steps: list[Step] = Field(max_length=20)
