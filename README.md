# extraction_eval

Evaluate local vision models that extract structured workouts from training-plan screenshots.

Schema contract: [SCHEMA.md](SCHEMA.md) (code: `schema.py`).

## Layout

- `screenshots/image_N.png` - inputs
- `ground_truth/image_N.json` - expected output for each screenshot (same N)
- `prompts/` - versioned prompts; never edit one after using it in a run, add a new version
- `modelfiles/` - Ollama Modelfiles (larger context window variants)
- `runs/<run_id>/` - saved outputs per run (gitignored; regenerable)
- `run_inference.py` - run a model over all screenshots and save the outputs
- `validate_ground_truth.py` - check that the ground truth passes the schema

## Commands

```bash
# one-off: create the Ollama model variants (needs Ollama running)
ollama create qwen3-vl-8b-instruct-16k -f modelfiles/qwen3-vl-8b-instruct-16k.Modelfile
ollama create qwen3-vl-8b-16k          -f modelfiles/qwen3-vl-8b-16k.Modelfile

uv run python validate_ground_truth.py
uv run python run_inference.py                                   # defaults: instruct-16k, extract_v2, temp 0
uv run python run_inference.py --repeat 3 --temperature 0.5      # variance needs temperature > 0
```

Each saved record stores the model, prompt name, prompt hash, git commit, temperature, raw output, and validation result.

## Notes

- a markdown file with a map of marathon pace - an actual target pace same for hm pace
- easy could be bpm range then find it in garmin??
