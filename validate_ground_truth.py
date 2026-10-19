"""Run: uv run python validate_ground_truth.py

Checks the dataset before any scoring:
  - every row of dataset.csv is well formed and has a unique id
  - every row has screenshots/<id>.png and ground_truth/<id>.json, and every screenshot / ground truth has a row
  - every ground truth passes the schema
  - every ground-truth date uses the year nearest the row's reference_date (SCHEMA.md annotation rules)
Then prints how many examples each split and tag has.
"""
import json
import sys
from collections import Counter

from pydantic import ValidationError

from dataset import GT_DIR, MANIFEST, SCREENSHOT_DIR, SPLITS, load_manifest, nearest_date
from schema import Workout

errors = []

try:
    examples = load_manifest()
except (ValueError, KeyError) as e:
    sys.exit(f"FAIL  {MANIFEST}: {e}")

ids = [e.id for e in examples]
for dup in sorted(i for i, n in Counter(ids).items() if n > 1):
    errors.append(f"{MANIFEST}: id {dup} appears more than once")

for path in sorted(SCREENSHOT_DIR.glob("*.png")):
    if path.stem not in ids:
        errors.append(f"{path} has no row in {MANIFEST}")
for path in sorted(GT_DIR.glob("*.json")):
    if path.stem not in ids:
        errors.append(f"{path} has no row in {MANIFEST}")

for ex in examples:
    if not ex.screenshot.exists():
        errors.append(f"{ex.id}: missing {ex.screenshot}")
    if not ex.ground_truth.exists():
        errors.append(f"{ex.id}: missing {ex.ground_truth}")
        continue
    try:
        workout = Workout.model_validate(json.loads(ex.ground_truth.read_text()))
    except (ValidationError, json.JSONDecodeError) as e:
        errors.append(f"{ex.ground_truth}\n{e}")
        continue
    expected = nearest_date(workout.date.month, workout.date.day, ex.reference_date)
    if workout.date != expected:
        errors.append(f"{ex.ground_truth}: date {workout.date} should be {expected} "
                      f"(year nearest reference_date {ex.reference_date})")
    else:
        print(f"OK    {ex.id:<10} {ex.split:<5} {workout.date}  {workout.session_label}")

print()
for split in SPLITS:
    in_split = [e for e in examples if e.split == split]
    tags = Counter(t for e in in_split for t in e.tags)
    print(f"{split:<5} {len(in_split):>3} examples   " + ", ".join(f"{t}={n}" for t, n in sorted(tags.items())))

dev_tags = {t for e in examples if e.split == "dev" for t in e.tags}
test_tags = {t for e in examples if e.split == "test" for t in e.tags}
if test_tags:
    for t in sorted(dev_tags ^ test_tags):
        print(f"note  tag {t!r} only appears in {'dev' if t in dev_tags else 'test'}")

if errors:
    print()
    for err in errors:
        print(f"FAIL  {err}")
    sys.exit(1)
