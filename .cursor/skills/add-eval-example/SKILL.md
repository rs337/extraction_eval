---
name: add-eval-example
description: Adds one training-plan screenshot to the extraction eval dataset - saves the screenshot, transcribes it, writes ground_truth/image_N.json following SCHEMA.md annotation rules, adds a dataset.csv row with split and tags, and validates. Asks before changing schema.py, SCHEMA.md or prompts. Use when the user attaches a workout/training-plan screenshot and asks to add it as an example, label it, create ground truth, or grow the dataset.
---

# Add an eval example

Label one screenshot at a time. Finish and validate it, report, and wait for the user to confirm before starting the next.

The user reviews every label, so make that review fast: show exactly what was read and what will be saved, and flag anything uncertain.

## Read first (once per chat)

- `SCHEMA.md`: field glossary, **Annotation rules** (the source of truth for labels), scoring conventions
- `schema.py`: `Workout` / `Leaf` / `Repeat`, and the `Intensity` / `LeafType` vocabularies
- `dataset.py` and `dataset.csv`: the manifest format, existing splits and tags
- every file in `ground_truth/`: worked examples of the rules

## Workflow

```
- [ ] 1. Save screenshot
- [ ] 2. Transcribe
- [ ] 3. Check rules cover every line (else STOP and ask)
- [ ] 4. Write ground truth
- [ ] 5. Choose split and tags, add manifest row
- [ ] 6. Validate
- [ ] 7. Report and wait
```

**1. Save the screenshot** as `screenshots/image_N.png`, where N is the next unused number. Copy it from the attached image's path on disk. Never overwrite an existing file. Reference date: the date the user gives, otherwise today's date (say which you used).

**2. Transcribe** the card line by line: title, date line, session label, body. Keep capitals, spacing and typos.

**3. Check coverage.** For every body line, name the annotation rule that decides it. If any line has no clear rule or doesn't fit the schema, go to "When rules or schema don't fit" before writing anything.

**4. Write `ground_truth/image_N.json`** from the transcription only. Never run the extractor or read `runs/` to help label.

- `title` and `session_label` are copied exactly as printed.
- `date`: the printed month and day, in the year closest to the reference date (`dataset.nearest_date`).
- One instruction line is one step. Summary lines (`4X2KM`), style-only lines (`INTO`, `PROGRESSIVE RUN`) and filler (`as per request`) are not steps.
- Units: `2K`/`2KM` -> `distance_km: 2`; `800m` -> `0.8`; `10 mins` -> `duration_s: 600`; `90 seconds` -> `90`; `@4:30` (/km) -> `pace_s_per_km: 270`. Recompute every pace as minutes x 60 + seconds.
- `intensity` is set only from the mapping list in `SCHEMA.md`. Never infer it.
- `rest_between_s` is used only for rest stated as *between* reps. Any other rest is a `rest` step.
- `x2` after a group of lines repeats those lines (`image_2`).
- An unlabelled easy first or last block is `warmup` / `cooldown` (`image_1`, `image_5`).
- Formatting: match the existing files. Compact one-line steps, and omit fields that are null or false.

**5. Manifest row.** Add one line to `dataset.csv` with exactly 6 columns, `id,split,reference_date,source,tags,notes`:

```csv
image_6,test,2026-10-20,coach_app,time_repeats;rest_between,"x3 applies to both lines above"
```

- `id` is lowercase and matches the file names. Use commas, not tabs. Quote `notes` if it contains a comma or quote. `source` is `coach_app` unless told otherwise.
- **split:** never change an existing row. Target about 60% dev and 40% test, with every tag present in both splits. While test has fewer than about 40% of examples, prefer `test`. State the choice and the reason.
- **tags:** `;`-separated. Reuse existing tags. Tag what makes the card hard (`nested_repeat`, `rest_between`, `time_repeats`, `metres`, `pace_and_intensity`, `heart_rate`, `pace_range`, ...), not what every card has.

**6. Validate:** run `uv run python validate_ground_truth.py`. Fix every FAIL and re-run until it passes.

**7. Report** in this order, then wait for confirmation:
1. transcription
2. ground-truth JSON
3. CSV row and the split reason
4. uncertain fields and why (or "none")
5. any rule applied for the first time
6. split and tag counts from the validator

If the user corrects a label, fix it, re-validate, and ask whether the correction implies a missing rule.

## When rules or schema don't fit: stop and ask

Examples: a new intensity word, heart-rate target, pace range, fartlek, distance plus duration on one line, a nested repeat, or an ambiguous structure. Don't guess. Use AskQuestion with options and a recommendation, e.g.:

- (a) keep the wording in `note`, with no schema change
- (b) extend a vocabulary (`Intensity`, `LeafType`)
- (c) add a field or rule
- (d) a different structure

Once a change is approved:

- **Rule only:** add it to "Annotation rules" in `SCHEMA.md`, naming this image id as the worked example.
- **Schema change:** edit `schema.py` and `SCHEMA.md` together. That means the vocabulary lines, field tables, mapping list and cross-field rules.
- **Existing labels:** check every file in `ground_truth/` the change could affect, list the ones changed (or say none), then run the validator.
- **Prompts:** if the extractor must now output something new, find the newest `prompts/extract_vN.txt` and check whether it has been used: `rg -l '"prompt_version": "extract_vN"' runs/`. If it has never been used, propose editing it. If it has been used, propose `extract_v(N+1).txt`. Never edit a used prompt. Ask before touching any prompt.
- **Scorer:** for a new field, say whether `score.py` needs it (`LEAF_FIELDS`, `REPEAT_FIELDS`, `totals`). Don't edit without asking.

## Never

- Edit, relabel or re-split existing examples without asking.
- Run `run_inference.py` or `score.py`, or read model outputs for test examples.
- Edit `.cursor/plans/`.
- Commit, unless asked.
