import json, os
from pathlib import Path

PATH = Path(os.environ.get("APPDATA", Path.home())) / "PCOptimizer" / "config.json"

def load():
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
