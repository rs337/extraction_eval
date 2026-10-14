"""Run: uv run python run_inference.py [--model NAME] [--prompt extract_v2] [--repeat 1] [--temperature 0]

Runs the extractor on every screenshot and saves one JSON per image under runs/<run_id>/.
Evaluation (score.py, judge.py) later reads these saved files, never the live model.

Note: at temperature 0 every repeat gives the same output, so use --repeat together with
--temperature > 0 (e.g. 0.5) if you want to measure variance.
"""
import argparse
import base64
import hashlib
import json
import re
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError

from schema import Workout

BASE_URL = "http://localhost:11434/v1"   # Ollama's OpenAI-compatible endpoint
MAX_TOKENS = 2048

client = OpenAI(base_url=BASE_URL, api_key="none", timeout=300)  # local VLMs can be slow


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="qwen3-vl-8b-instruct-16k")
    p.add_argument("--prompt", default="extract_v2", help="name of a file in prompts/ (without .txt)")
    p.add_argument("--images", default="screenshots", help="folder containing the screenshots")
    p.add_argument("--repeat", type=int, default=1, help="runs per image, to measure variance")
    p.add_argument("--temperature", type=float, default=0.0,
                   help="sampling temperature; repeats only differ when this is > 0")
    return p.parse_args()


def git_commit() -> str | None:
    """Short hash of the current commit, with '-dirty' if there are uncommitted changes."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", ".", ":!runs"],
                               capture_output=True, text=True, check=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def make_run_dir(model: str) -> tuple[str, Path]:
    safe_model = re.sub(r"[^A-Za-z0-9._-]", "-", model)       # "qwen3-vl:8b" -> "qwen3-vl-8b"
    run_id = f"{datetime.now():%Y%m%d_%H%M%S}_{safe_model}"
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True)
    return run_id, run_dir

def extract(image_path: Path, model: str, prompt_text: str, prompt_version: str,
            prompt_sha: str, commit: str | None, temperature: float, seed: int) -> dict:
    """Call the model on one image and return a result record. Never raises."""
    record = {
        "image": image_path.name,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha,
        "git_commit": commit,
        "temperature": temperature,
        "seed": seed,
        "max_tokens": MAX_TOKENS,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "latency_s": None,
        "raw_output": None,
        "valid": False,
        "validation_error": None,
        "api_error": None,
        "usage": None,
        "parsed": None,
        "finish_reason": None,
        "reasoning": None,
    }

    img_b64 = base64.b64encode(image_path.read_bytes()).decode()

    # --- 1) the API call (can fail: Ollama down, model missing, timeout) ---
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ]}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "workout", "schema": Workout.model_json_schema()}},
            temperature=temperature,
            seed=seed,   # Ollama otherwise reuses one fixed seed, making every repeat identical
            max_tokens=MAX_TOKENS,
        )
    except Exception as e:
        record["latency_s"] = round(time.perf_counter() - t0, 2)
        record["api_error"] = f"{type(e).__name__}: {e}"
        return record
    record["latency_s"] = round(time.perf_counter() - t0, 2)

    record["raw_output"] = resp.choices[0].message.content
    msg = resp.choices[0].message
    record["finish_reason"] = resp.choices[0].finish_reason
    extra = msg.model_extra or {}
    record["reasoning"] = extra.get("reasoning") or extra.get("reasoning_content")
    if resp.usage:
        record["usage"] = {"prompt_tokens": resp.usage.prompt_tokens,
                           "completion_tokens": resp.usage.completion_tokens}

    # --- 2) validation (separate try, so the raw text is kept when this fails) ---
    try:
        workout = Workout.model_validate_json(record["raw_output"] or "")
        record["valid"] = True
        record["parsed"] = workout.model_dump(mode="json")
    except ValidationError as e:
        record["validation_error"] = str(e)

    return record

def write_summary(run_dir: Path, run_id: str, model: str, prompt_version: str, results: list[dict],
                  temperature: float = 0.0) -> dict:
    latencies = [r["latency_s"] for r in results if r["latency_s"] is not None]
    n_valid = sum(r["valid"] for r in results)
    summary = {
        "run_id": run_id,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_sha256": results[0]["prompt_sha256"] if results else None,
        "git_commit": results[0]["git_commit"] if results else None,
        "temperature": temperature,
        "n_outputs": len(results),
        "n_valid": n_valid,
        "validity_rate": round(n_valid / len(results), 3) if results else None,
        "n_api_errors": sum(r["api_error"] is not None for r in results),
        "latency_mean_s": round(statistics.mean(latencies), 2) if latencies else None,
        "latency_max_s": max(latencies) if latencies else None,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary

def main() -> None:
    args = parse_args()

    prompt_text = Path(f"prompts/{args.prompt}.txt").read_text().strip()
    images = sorted(Path(args.images).glob("*.png"))
    if not images:
        raise SystemExit(f"No .png files found in {args.images}/")

    prompt_sha = hashlib.sha256(prompt_text.encode()).hexdigest()[:12]
    commit = git_commit()

    run_id, run_dir = make_run_dir(args.model)
    print(f"Run {run_id}: {len(images)} images x {args.repeat} repeat(s), "
          f"prompt={args.prompt} ({prompt_sha}), temperature={args.temperature}, commit={commit}\n")

    results = []
    for image_path in images:
        for r in range(1, args.repeat + 1):
            record = extract(image_path, args.model, prompt_text, args.prompt,
                             prompt_sha, commit, args.temperature, seed=r)
            record["repeat"] = r

            suffix = f"_r{r}" if args.repeat > 1 else ""
            out_path = run_dir / f"{image_path.stem}{suffix}.json"
            out_path.write_text(json.dumps(record, indent=2))
            results.append(record)

            status = "valid" if record["valid"] else ("API ERROR" if record["api_error"] else f"INVALID ({record['finish_reason']})")
            print(f"{image_path.name:<14} r{r}  {status:<9} {record['latency_s']}s")

    summary = write_summary(run_dir, run_id, args.model, args.prompt, results, args.temperature)
    print(f"\nValid: {summary['n_valid']}/{summary['n_outputs']}  "
          f"mean latency: {summary['latency_mean_s']}s  -> {run_dir}/")


if __name__ == "__main__":
    main()