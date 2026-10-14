from schema import Workout
import json
print(json.dumps(Workout.model_json_schema(), indent=2))