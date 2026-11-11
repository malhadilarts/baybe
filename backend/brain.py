import json
import urllib.request
import db
from config import OLLAMA_URL

def is_available():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            return True
    except Exception:
        return False

def list_models():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            j = json.loads(r.read())
            return [m["name"] for m in j.get("models", [])]
    except Exception:
        return []

def ask(prompt, model=None):
    model = model or db.get_setting("brain_model", "")
    if not model:
        models = list_models()
        if not models:
            raise RuntimeError("no ollama models")
        model = models[0]
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        j = json.loads(r.read())
        return j["message"]["content"], model

def enabled():
    return db.get_setting("brain_enabled", "0") == "1"

def set_enabled(v):
    db.set_setting("brain_enabled", "1" if v else "0")

def set_model(m):
    db.set_setting("brain_model", m)
