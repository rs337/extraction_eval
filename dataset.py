"""The dataset manifest (dataset.csv): which examples exist, their split, and the reference date for each.

One row per example. The `id` is the shared file stem: screenshots/<id>.png and ground_truth/<id>.json.
Columns:
  id              file stem, e.g. image_5
  split           dev (used for prompt tuning) or test (held out; do not inspect while tuning)
  reference_date  YYYY-MM-DD, the day the screenshot was taken; resolves the year (see nearest_date)
  source          where the screenshot came from, e.g. coach_app
  tags            ';'-separated case labels, e.g. nested_repeat;rest_between
  notes           free text
"""
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

MANIFEST = Path("dataset.csv")
SCREENSHOT_DIR = Path("screenshots")
GT_DIR = Path("ground_truth")
SPLITS = ("dev", "test")


@dataclass(frozen=True)
class Example:
    id: str
    split: str
    reference_date: date
    source: str
    tags: tuple[str, ...]
    notes: str

    @property
    def screenshot(self) -> Path:
        return SCREENSHOT_DIR / f"{self.id}.png"

    @property
    def ground_truth(self) -> Path:
        return GT_DIR / f"{self.id}.json"


def load_manifest(split: str = "all") -> list[Example]:
    """Rows of dataset.csv, optionally only one split. Raises ValueError on a malformed row."""
    examples = []
    with MANIFEST.open(newline="") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            if row["split"] not in SPLITS:
                raise ValueError(f"{MANIFEST}:{line_no}: split must be one of {SPLITS}, got {row['split']!r}")
            try:
                ref = date.fromisoformat(row["reference_date"])
            except ValueError:
                raise ValueError(f"{MANIFEST}:{line_no}: reference_date must be YYYY-MM-DD, "
                                 f"got {row['reference_date']!r}") from None
            examples.append(Example(
                id=row["id"].strip(),
                split=row["split"],
                reference_date=ref,
                source=(row.get("source") or "").strip(),
                tags=tuple(t.strip() for t in (row.get("tags") or "").split(";") if t.strip()),
                notes=(row.get("notes") or "").strip(),
            ))
    return [e for e in examples if split == "all" or e.split == split]


def nearest_date(month: int, day: int, reference: date) -> date:
    """The month/day in whichever year puts it closest to the reference date.

    Screenshots print a weekday and month-day but no year; this is the annotation rule for the year.
    """
    candidates = []
    for year in (reference.year - 1, reference.year, reference.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:          # 29 February in a non-leap year
            pass
    return min(candidates, key=lambda d: abs((d - reference).days))
