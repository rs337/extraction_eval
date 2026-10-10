"""Workout schema: the single definition used for ground truth, extraction output, storage and scoring.

Field meanings and cross-field rules live in SCHEMA.md. Update that file when this schema changes.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

StepType = Literal["warmup", "cooldown", "work", "rest", "stride", "repeat"]


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")  # typos like "distnace_km" are rejected

    type: StepType
    distance_km: Optional[float] = Field(None, gt=0)
    duration_s: Optional[int] = Field(None, gt=0)
    intensity: Optional[str] = None            # qualitative target, e.g. "easy", "float"
    pace_s_per_km: Optional[int] = Field(None, ge=150, le=600)  # null if no number is written
    optional: bool = False                     # e.g. "( IF POSSIBLE)"
    note: Optional[str] = None                 # for ambiguous wording

    # repeat groups only
    reps: Optional[int] = Field(None, ge=2)
    rest_between_s: Optional[int] = Field(None, gt=0)  # rest between reps, not after the last
    steps: Optional[list[Step]] = None

    @model_validator(mode="after")
    def check_rules(self) -> "Step":
        if self.type == "repeat":
            if not self.reps or not self.steps:
                raise ValueError("repeat needs reps and steps")
            if self.distance_km is not None or self.duration_s is not None:
                raise ValueError("repeat cannot have its own distance/duration")
        else:
            if self.steps is not None or self.reps is not None or self.rest_between_s is not None:
                raise ValueError("only repeat steps can have reps/steps/rest_between_s")
            if self.distance_km is not None and self.duration_s is not None:
                raise ValueError("a step has distance or duration, not both")
        return self


class Workout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    date: date
    session_label: str                         # raw header text, e.g. "INTERVALS"
    steps: list[Step]
