# Workout schema

`schema.py` is the single definition used for ground truth, extraction output, storage, and scoring. This file is the field glossary. When a field, constraint, or rule changes, update `schema.py` and this document together.

Unknown keys are rejected (`extra="forbid"`), so a typo such as `distnace_km` fails validation instead of being dropped.

## Workout

| Field           | Type         | Constraints                        | Meaning                                                                                      |
| --------------- | ------------ | ---------------------------------- | -------------------------------------------------------------------------------------------- |
| `title`         | string       | required                           | Programme title, e.g. `"HALF/MARATHON PROGRAMME"`.                                           |
| `date`          | date         | required; ISO `YYYY-MM-DD` in JSON | Session date. NOTE year is not included in the image and must be inferred.                   |
| `session_label` | string       | required                           | Raw header text from the plan, e.g. `"INTERVALS"`, `"10 KM EASY RUN"`. Preserved as written. |
| `steps`         | list of Step | required; at most 20 items         | Ordered blocks of the session. Each item is a `Leaf` or a `Repeat`.                          |

## Step

A step is either a `Leaf` (one block of running) or a `Repeat` (a group of leaves done several times). The `type` field tells them apart: `repeat` is a `Repeat`, anything else is a `Leaf`.

### Leaf

`type` is one of `warmup`, `cooldown`, `work`, `rest`, `stride`.
`intensity` is one of `easy`, `float`, `half_marathon_pace`, `marathon_pace`, `tempo` or null.

| Field           | Type              | Constraints     | Meaning                                                                |
| --------------- | ----------------- | --------------- | ---------------------------------------------------------------------- |
| `type`          | LeafType          | required        | Kind of block.                                                         |
| `distance_km`   | float or null     | `> 0` when set  | Distance, when the plan states one.                                    |
| `duration_s`    | int or null       | `> 0` when set  | Duration in seconds, when the plan states one.                         |
| `intensity`     | Intensity or null |                 | Qualitative target, e.g. `"easy"`, `"float"`, `"half_marathon_pace"`.  |
| `pace_s_per_km` | int or null       | `150`-`600`     | Pace in seconds per kilometre. Null when no number is written.         |
| `optional`      | bool              | default `false` | `true` when the plan marks the step optional, e.g. `"( IF POSSIBLE)"`. |
| `note`          | string or null    |                 | Wording that does not fit the other fields.                            |

### Repeat

| Field            | Type            | Constraints                  | Meaning                                                                     |
| ---------------- | --------------- | ---------------------------- | --------------------------------------------------------------------------- |
| `type`           | `"repeat"`      | required                     | Marks the group.                                                            |
| `reps`           | int             | `>= 2`, required             | How many times the nested steps are repeated.                               |
| `steps`          | list of Leaf    | 1 to 6 items, required       | ONE repetition. A repeat cannot contain another repeat.                     |
| `rest_between_s` | int or null     | `> 0` when set               | Rest between reps, not after the last rep.                                  |
| `optional`       | bool            | default `false`              | `true` when the whole group is marked optional.                             |
| `note`           | string or null  |                              | Wording that does not fit the other fields.                                 |

A `Repeat` has no `distance_km`, `duration_s`, `intensity` or `pace_s_per_km`. Those belong on its nested leaves.

## Cross-field rules

- A `Leaf` has `distance_km` or `duration_s`, not both (enforced in `Leaf.check_rules`).
- Only a `Repeat` can have `reps`, `steps` or `rest_between_s`. The union is discriminated on `type`, and `extra="forbid"` rejects those keys on a `Leaf`.
- A `Repeat` needs `reps >= 2` and at least one nested leaf.

## Annotation rules

These decide what counts as the correct answer in `ground_truth/`. They apply to `title`, `session_label`, `date`, `intensity` and step structure.

- Copy `title` and `session_label` exactly as printed, including capitals. Do not title-case them.
- The image has a weekday and a month-day, not a year. Store a full `YYYY-MM-DD`. Choose the year so that weekday is correct for the reference date used by this eval, `2026-10-11`.
- Set `intensity` only when the plan prints one of these words. Map the printed wording to the label:
  - `easy` -> `easy`
  - `float` -> `float`
  - `half marathon pace`, `HMP` -> `half_marathon_pace`
  - `marathon pace`, `MP` -> `marathon_pace`
  - `tempo` -> `tempo`
- Leave `intensity` null for any other wording. `WARM UP` and `COOL DOWN` choose `type`; they are not an intensity. `2K EASY` is `intensity: "easy"`. `2KM COOL DOWN` has no intensity.
- **Empty body (image 3).** When the card has no body text, and the `session_label` itself states a distance or duration (e.g. `"10 KM EASY RUN"`), annotate ONE `work` step from the label: `{"type": "work", "distance_km": 10, "intensity": "easy"}`. When the label states no distance or duration, `steps` is an empty list.
- **Rest together with strides (image 4).** For text like `REST 3 MINS WITH 4X 20 SECONDS STRIDES`, annotate the strides `repeat` first, then a separate `rest` step. Do not put the rest into the strides repeat's `rest_between_s`; that field is only for rest explicitly described as being between reps (e.g. `90 SECONDS REST BETWEEN`).
- A summary line above the steps (e.g. `4X2KM` in image 4) is not a step. Annotate only the lines that describe what to run.
- Lines that only name the style of the block and carry no number or intensity (e.g. `INTO`, `PROGRESSIVE RUN`) are not steps and are not recorded.

## Scoring conventions

- Repeats are expanded before totals are compared: a `Repeat` becomes `reps` copies of its `steps`, with `reps - 1` `rest` segments of `rest_between_s` between them when that field is set. An explicit `rest` step and `rest_between_s` therefore compare equal.
