"""python -m ai_core.free_vision  -> free OpenRouter models that accept images"""
import json
import urllib.request

data = json.load(urllib.request.urlopen("https://openrouter.ai/api/v1/models"))["data"]
for m in data:
    free = str(m.get("pricing", {}).get("prompt")) in ("0", "0.0")
    if free and "image" in m.get("architecture", {}).get("input_modalities", []):
        print(m["id"])