# Workout schema

`schema.py` is the single definition used for ground truth, extraction output, storage, and scoring. This file is the field glossary. When a field, constraint, or rule changes, update `schema.py` and this document together.

Unknown keys are rejected (`extra="forbid"`), so a typo such as `distnace_km` fails validation instead of being dropped.

## Workout

| Field           | Type         | Constraints                        | Meaning                                                                                      |
| --------------- | ------------ | ---------------------------------- | -------------------------------------------------------------------------------------------- |
| `title`         | string       | required                           | Programme title, e.g. `"Half/Marathon Programme"`.                                           |
| `date`          | date         | required; ISO `YYYY-MM-DD` in JSON | Session date.                                                                                |
| `session_label` | string       | required                           | Raw header text from the plan, e.g. `"INTERVALS"`, `"10 KM EASY RUN"`. Preserved as written. |
| `steps`         | list of Step | required                           | Ordered blocks of the session.                                                               |

## Step

`type` is one of `warmup`, `cooldown`, `work`, `rest`, `stride`, `repeat`.

| Field            | Type                 | Constraints                  | Meaning                                                                    |
| ---------------- | -------------------- | ---------------------------- | -------------------------------------------------------------------------- |
| `type`           | StepType             | required                     | Kind of block.                                                             |
| `distance_km`    | float or null        | `> 0` when set               | Distance, when the plan states one.                                        |
| `duration_s`     | int or null          | `> 0` when set               | Duration in seconds, when the plan states one.                             |
| `intensity`      | string or null       |                              | Qualitative target, e.g. `"easy"`, `"float"`, `"half_marathon_pace"`.      |
| `pace_s_per_km`  | int or null          | `150`–`600` when set         | Pace in seconds per kilometre. Null when no number is written on the plan. |
| `optional`       | bool                 | default `false`              | `true` when the plan marks the step optional, e.g. `"( IF POSSIBLE)"`.     |
| `note`           | string or null       |                              | Wording that does not fit the other fields.                                |
| `reps`           | int or null          | `>= 2` when set; repeat only | How many times the nested steps are repeated.                              |
| `rest_between_s` | int or null          | `> 0` when set; repeat only  | Rest between reps, not after the last rep.                                 |
| `steps`          | list of Step or null | repeat only                  | Nested steps inside a repeat.                                              |

## Cross-field rules

Enforced in `Step.check_rules`:

- A `repeat` must have `reps` and a non-empty `steps` list, and must not set `distance_km` or `duration_s`. Distance and duration belong on the nested steps.
- Any other type must not set `reps`, `steps`, or `rest_between_s`.
- A non-repeat step may set `distance_km` or `duration_s`, but not both.
