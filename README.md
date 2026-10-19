# extraction_eval

Evaluate local vision models that extract structured workouts from training-plan screenshots.

Schema contract: [SCHEMA.md](SCHEMA.md) (code: `schema.py`).

## Layout

- `dataset.csv` - the manifest: one row per example with its split (`dev`/`test`), reference date and tags
- `screenshots/image_N.png` - inputs
- `ground_truth/image_N.json` - expected output for each screenshot (same N)
- `dataset.py` - loads the manifest; holds the year rule (`nearest_date`)
- `prompts/` - versioned prompts; never edit one after using it in a run, add a new version. `{reference_date}` is filled per example
- `modelfiles/` - Ollama Modelfiles (larger context window variants)
- `runs/<run_id>/` - saved outputs per run (gitignored; regenerable)
- `run_inference.py` - run a model over one split and save the outputs
- `score.py` - score saved runs against the ground truth
- `validate_ground_truth.py` - check the manifest, screenshots and ground truth agree and pass the schema

## Commands

```bash
# one-off: create the Ollama model variants (needs Ollama running)
ollama create qwen3-vl-8b-instruct-16k -f modelfiles/qwen3-vl-8b-instruct-16k.Modelfile
ollama create qwen3-vl-8b-16k          -f modelfiles/qwen3-vl-8b-16k.Modelfile

uv run python validate_ground_truth.py
uv run python run_inference.py                                   # defaults: dev split, instruct-16k, extract_v3, temp 0
uv run python run_inference.py --repeat 3 --temperature 0.5      # variance needs temperature > 0
uv run python score.py                                           # newest run
uv run python score.py --all --split dev                         # compare every run on dev only

# only when a prompt/model choice is final:
uv run python run_inference.py --split test && uv run python score.py
```

Each saved record stores the model, prompt name, prompt hash, git commit, temperature, split, reference date, raw output, and validation result.

## Adding an example

1. Screenshot one session card (header with title and date, the session label, and the full body text). Save it as `screenshots/image_N.png` with the next unused N.
2. Add a row to `dataset.csv`: `image_N,<dev|test>,<day you took the screenshot>,<source>,<tag;tag>,<notes>`.
3. Write `ground_truth/image_N.json` from the image, following the annotation rules in [SCHEMA.md](SCHEMA.md). Do not start from model output.
4. Run `uv run python validate_ground_truth.py` and fix anything marked FAIL.

A split is fixed once assigned. Do not look at model outputs for `test` examples while tuning prompts.

## Notes

- a markdown file with a map of marathon pace - an actual target pace same for hm pace
- easy could be bpm range then find it in garmin??
