import base64, json
from openai import OpenAI
from schema import Workout

client = OpenAI(base_url="http://localhost:11434/v1", api_key="none")  # vLLM/Ollama/provider

img = base64.b64encode(open("screenshots/image_1.png", "rb").read()).decode()
resp = client.chat.completions.create(
    model="qwen3-vl:8b",   # swap this line to compare model sizes
    messages=[{"role": "user", "content": [
    {"type": "text", "text": "Extract the workout from this screenshot. Only include what is written; use null if a value is not stated."},
    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}},
    ]}],
    response_format={"type": "json_schema",
                     "json_schema": {"name": "workout", "schema": Workout.model_json_schema()}},
    temperature=0,
    max_tokens=8192
)
# After line 19, before line 20, add:
print("Response:", resp)
print("Content:", resp.choices[0].message.content)
print("Full message:", resp.choices[0].message)
workout = Workout.model_validate_json(resp.choices[0].message.content)
