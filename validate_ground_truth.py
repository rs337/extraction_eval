"""Run: python validate_ground_truth.py  -> checks every JSON in ground_truth/ against the schema."""
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from schema import Workout

failed = False
for path in sorted(Path("ground_truth").glob("*.json")):
    try:
        Workout.model_validate(json.loads(path.read_text()))
        print(f"OK    {path.name}")
    except ValidationError as e:
        failed = True
        print(f"FAIL  {path.name}\n{e}\n")
sys.exit(1 if failed else 0)
