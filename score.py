"""Run: uv run python score.py [RUN_DIR ...] [--all] [--split dev|test|all]

Scores saved runs against ground_truth/. With no argument, scores the newest run.
--split limits scoring to the examples of that split in dataset.csv (default: all, i.e. whatever the run contains).
Writes runs/<run_id>/scores.json and prints a report per run.

Metric layers, coarse to fine (see SCHEMA.md "Scoring conventions"):
  1. validity   - did the output parse and pass the current schema
  2. top-level  - title, date, session_label exact match
  3. steps      - align predicted steps to true steps; precision/recall/F1 and per-field accuracy
  4. segments   - expand repeats into a flat list and compare totals (forgives different-but-valid structure)
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from pydantic import ValidationError

from dataset import load_manifest
from schema import Leaf, Repeat, Workout

RUNS_DIR = Path("runs")
TOP_FIELDS = ["title", "date", "session_label"]
LEAF_FIELDS = ["distance_km", "duration_s", "intensity", "pace_s_per_km",
               "pace_min_s_per_km", "pace_max_s_per_km", "optional"]
REPEAT_FIELDS = ["reps", "rest_between_s", "optional"]
KM_TOL = 0.01

# ---------- loading ----------

def load_ground_truth(split: str = "all") -> dict[str, Workout]:
    """{'image_1': Workout, ...} for the examples of a split, keyed by id (the shared file stem)."""
    return {e.id: Workout.model_validate_json(e.ground_truth.read_text()) for e in load_manifest(split)}


def load_records(run_dir: Path) -> list[dict]:
    """Every per-image record in a run. The glob skips summary.json and scores.json."""
    return [json.loads(p.read_text()) for p in sorted(run_dir.glob("image_*.json"))]


def parse_prediction(record: dict) -> Workout | None:
    """The model's output as a Workout, or None if it is not valid under the CURRENT schema."""
    if not record.get("valid"):
        return None
    try:
        return Workout.model_validate(record["parsed"])
    except ValidationError:
        return None

# ---------- comparing values ----------

def same(a, b) -> bool:
    """Equality, with a tolerance for floats (distance_km)."""
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(a - b) <= KM_TOL
    return a == b


def fields_for(step) -> list[str]:
    return REPEAT_FIELDS if isinstance(step, Repeat) else LEAF_FIELDS


def relevant(field: str, a, b) -> bool:
    """Score a field only if at least one side sets it. null vs null is not evidence of skill."""
    return getattr(a, field) not in (None, False) or getattr(b, field) not in (None, False)


def similarity(a, b) -> float:
    """Share of relevant fields that agree, 0..1. Used only to break ties during alignment."""
    rel = [f for f in fields_for(a) if relevant(f, a, b)]
    if not rel:
        return 1.0
    return sum(same(getattr(a, f), getattr(b, f)) for f in rel) / len(rel)

# ---------- layer 3: step alignment ----------

def align(gt: list, pred: list) -> list[tuple[int, int]]:
    """Order-preserving pairing of steps with the same type.

    Maximises (number of pairs, total similarity): first pair as many steps as possible,
    then among equally good pairings prefer the one whose fields agree most.
    Classic longest-common-subsequence dynamic programming.
    """
    n, m = len(gt), len(pred)
    # best[i][j] = best (pairs, similarity) achievable using gt[i:] and pred[j:]
    best = [[(0, 0.0)] * (m + 1) for _ in range(n + 1)]
    take = [[False] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best[i][j] = max(best[i + 1][j], best[i][j + 1])        # skip a gt step or a pred step
            if gt[i].type == pred[j].type:
                count, sim = best[i + 1][j + 1]
                pair = (count + 1, sim + similarity(gt[i], pred[j]))  # or pair them
                if pair > best[i][j]:
                    best[i][j], take[i][j] = pair, True

    # walk the table from the start to read off which pairs were chosen
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if take[i][j]:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif best[i + 1][j] >= best[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs

def score_steps(gt: list, pred: list, total: Counter, correct: Counter) -> tuple[int, int, int]:
    """Align two step lists, record per-field results into total/correct, return (n_gt, n_pred, n_matched).

    Inside a matched repeat the nested steps are aligned too and added to the counts.
    """
    n_gt, n_pred = len(gt), len(pred)
    pairs = align(gt, pred)
    n_matched = len(pairs)
    for i, j in pairs:
        g, p = gt[i], pred[j]
        for f in fields_for(g):
            if relevant(f, g, p):
                total[f] += 1
                correct[f] += same(getattr(g, f), getattr(p, f))
        if isinstance(g, Repeat):
            a, b, c = score_steps(g.steps, p.steps, total, correct)
            n_gt, n_pred, n_matched = n_gt + a, n_pred + b, n_matched + c
    return n_gt, n_pred, n_matched

# ---------- layer 4: expanded segments ----------

def expand(steps: list) -> list[Leaf]:
    """Flatten repeats into the actual sequence run, with rest_between_s turned into rest segments."""
    out = []
    for s in steps:
        if isinstance(s, Repeat):
            for k in range(s.reps):
                out.extend(s.steps)
                if s.rest_between_s and k < s.reps - 1:
                    out.append(Leaf(type="rest", duration_s=s.rest_between_s))
        else:
            out.append(s)
    return out


def totals(steps: list) -> dict:
    """Structure-independent summary of what the athlete actually has to do."""
    segs = expand(steps)
    return {
        "n_segments": len(segs),
        "distance_km": round(sum(s.distance_km or 0 for s in segs), 3),
        "moving_time_s": sum(s.duration_s or 0 for s in segs if s.type != "rest"),
        "rest_time_s": sum(s.duration_s or 0 for s in segs if s.type == "rest"),
        "paces": [s.pace_s_per_km for s in segs if s.pace_s_per_km is not None],
        "pace_ranges": [[s.pace_min_s_per_km, s.pace_max_s_per_km] for s in segs if s.pace_min_s_per_km is not None],
    }

# ---------- one output ----------

def score_output(record: dict, gt: Workout) -> dict:
    """All four layers for one model output. An invalid output scores as an empty prediction."""
    pred = parse_prediction(record)
    total, correct = Counter(), Counter()
    n_gt, n_pred, n_matched = score_steps(gt.steps, pred.steps if pred else [], total, correct)
    gt_totals = totals(gt.steps)
    pred_totals = totals(pred.steps) if pred else None
    return {
        "image": Path(record["image"]).stem,
        "repeat": record.get("repeat", 1),
        "valid": pred is not None,
        "top": {f: pred is not None and getattr(pred, f) == getattr(gt, f) for f in TOP_FIELDS},
        "steps": {"n_gt": n_gt, "n_pred": n_pred, "n_matched": n_matched},
        "fields": {f: [correct[f], total[f]] for f in total},
        "segments": {k: pred_totals is not None and same(v, pred_totals[k]) for k, v in gt_totals.items()},
        "gt_totals": gt_totals,
        "pred_totals": pred_totals,
    }

# ---------- aggregation ----------

def prf(n_gt: int, n_pred: int, n_matched: int) -> tuple[float, float, float]:
    p = n_matched / n_pred if n_pred else 0.0
    r = n_matched / n_gt if n_gt else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 3), round(r, 3), round(f1, 3)


def summarise(results: list[dict]) -> dict:
    """Pool counts across outputs (micro-average), then turn them into rates."""
    steps, f_correct, f_total = Counter(), Counter(), Counter()
    for r in results:
        steps.update(r["steps"])
        for f, (c, t) in r["fields"].items():
            f_correct[f] += c
            f_total[f] += t
    p, rec, f1 = prf(steps["n_gt"], steps["n_pred"], steps["n_matched"])
    return {
        "n_outputs": len(results),
        "validity_rate": round(mean(r["valid"] for r in results), 3),
        "top_level": {f: round(mean(r["top"][f] for r in results), 3) for f in TOP_FIELDS},
        "steps": {"precision": p, "recall": rec, "f1": f1, **steps},
        "field_accuracy": {f: round(f_correct[f] / f_total[f], 3) for f in sorted(f_total)},
        "field_counts": {f: [f_correct[f], f_total[f]] for f in sorted(f_total)},
        "segments": {k: round(mean(r["segments"][k] for r in results), 3) for k in results[0]["segments"]},
        "all_segments_match": round(mean(all(r["segments"].values()) for r in results), 3),
    }

# ---------- run level ----------

def score_run(run_dir: Path, gt: dict[str, Workout], split: str = "all") -> dict | None:
    in_manifest = {e.id for e in load_manifest()}
    results = []
    for record in load_records(run_dir):
        image = Path(record["image"]).stem
        if image not in gt:
            if image not in in_manifest:
                print(f"  skip {record['image']}: not in dataset.csv")
            continue
        results.append(score_output(record, gt[image]))
    if not results:
        print(f"\n=== {run_dir.name}: no outputs for split={split}")
        return None

    by_image = defaultdict(list)
    for r in results:
        by_image[r["image"]].append(r)

    scores = {
        "run_id": run_dir.name,
        "split": split,
        "overall": summarise(results),
        "per_image": {img: summarise(rs) for img, rs in sorted(by_image.items())},
        "outputs": results,
    }
    (run_dir / "scores.json").write_text(json.dumps(scores, indent=2))
    return scores


def print_report(scores: dict) -> None:
    s = scores["overall"]
    st = s["steps"]
    print(f"\n=== {scores['run_id']}  (split={scores['split']}, {s['n_outputs']} outputs)")
    print(f"validity        {s['validity_rate']:.2f}")
    print("top-level       " + "  ".join(f"{f}={v:.2f}" for f, v in s["top_level"].items()))
    print(f"steps           P={st['precision']:.2f}  R={st['recall']:.2f}  F1={st['f1']:.2f}  "
          f"(matched {st['n_matched']} of {st['n_gt']} true, {st['n_pred']} predicted)")
    print("field accuracy  " + "  ".join(f"{f}={c}/{t}" for f, (c, t) in s["field_counts"].items()))
    print("segments        " + "  ".join(f"{k}={v:.2f}" for k, v in s["segments"].items()))
    for img, sub in scores["per_image"].items():
        print(f"  {img:<10} valid={sub['validity_rate']:.2f}  step_F1={sub['steps']['f1']:.2f}  "
              f"all_segments={sub['all_segments_match']:.2f}")


def print_comparison(all_scores: list[dict]) -> None:
    print(f"\n{'run':<45} {'valid':>6} {'stepF1':>7} {'segs':>6}")
    for sc in all_scores:
        s = sc["overall"]
        print(f"{sc['run_id']:<45} {s['validity_rate']:>6.2f} {s['steps']['f1']:>7.2f} {s['all_segments_match']:>6.2f}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("run_dirs", nargs="*", type=Path, help="runs/<run_id> folders (default: newest run)")
    p.add_argument("--all", action="store_true", help="score every run in runs/")
    p.add_argument("--split", default="all", choices=["dev", "test", "all"],
                   help="only score examples of this split in dataset.csv")
    args = p.parse_args()

    all_runs = sorted(d for d in RUNS_DIR.iterdir() if d.is_dir())
    run_dirs = all_runs if args.all else (args.run_dirs or all_runs[-1:])

    gt = load_ground_truth(args.split)
    all_scores = []
    for run_dir in run_dirs:
        scores = score_run(run_dir, gt, args.split)
        if scores:
            print_report(scores)
            all_scores.append(scores)
    if len(all_scores) > 1:
        print_comparison(all_scores)


if __name__ == "__main__":
    main()