import json
import urllib.request
import db
from config import OLLAMA_URL

def backend():
    return db.get_setting("brain_backend", "ollama")

def _llamacpp_available():
    try:
        import llama_cpp  # noqa
        return True
    except Exception:
        return False

def is_available():
    if backend() == "llamacpp":
        return _llamacpp_available() and bool(db.get_setting("llama_model_path", ""))
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            return True
    except Exception:
        return False

def list_models():
    if backend() == "llamacpp":
        p = db.get_setting("llama_model_path", "")
        return [p] if p else []
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            j = json.loads(r.read())
            return [m["name"] for m in j.get("models", [])]
    except Exception:
        return []

_llama_cache = {"path": None, "llm": None}

def _get_llama(path):
    global _llama_cache
    if _llama_cache["path"] == path and _llama_cache["llm"] is not None:
        return _llama_cache["llm"]
    from llama_cpp import Llama
    llm = Llama(model_path=path, n_ctx=2048, verbose=False)
    _llama_cache = {"path": path, "llm": llm}
    return llm

def ask(prompt, model=None):
    if backend() == "llamacpp":
        if not _llamacpp_available():
            raise RuntimeError("llama-cpp-python not installed")
        path = db.get_setting("llama_model_path", "")
        if not path:
            raise RuntimeError("no llama model path set")
        llm = _get_llama(path)
        out = llm.create_chat_completion(messages=[{"role": "user", "content": prompt}])
        return out["choices"][0]["message"]["content"], path
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

def set_backend(b):
    db.set_setting("brain_backend", b)

def set_llama_path(p):
    db.set_setting("llama_model_path", p)
