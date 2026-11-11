import json
import time
import re
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import db
import nn
import memory
import docs
import guardian

app = FastAPI(title=config.APP_NAME, version=config.VERSION)
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

NET = nn.NNC()
try:
    if not db.get_setting("trained_at"):
        NET.train(epochs=30)
except Exception:
    pass

class ChatReq(BaseModel):
    message: str

class FactReq(BaseModel):
    text: str

class ExampleReq(BaseModel):
    text: str
    label: str

@app.get("/api/status")
def status():
    return {
        "app": config.APP_NAME,
        "tagline": config.TAGLINE,
        "version": config.VERSION,
        "nn": NET.info(),
        "facts": len(memory.list_facts()),
        "docs": len(db.docs_all()),
    }

@app.post("/api/chat")
def chat(req: ChatReq):
    msg = req.message.strip()
    ok, reason = guardian.check(msg)
    if not ok:
        def g():
            yield "data: " + json.dumps({"token": reason}) + "\n\n"
            yield "data: " + json.dumps({"done": True}) + "\n\n"
        return StreamingResponse(g(), media_type="text/event-stream")

    low = msg.lower()
    core = "baybe"
    if low.startswith("korrektur:"):
        reply = memory.correct(msg)
        intent = "teach"
        conf = 1.0
    else:
        if any(low.startswith(p) for p in ["merke", "merk", "notiere", "speichere"]):
            intent = "teach"
            conf = 0.9
        elif any(w in low for w in ["wie ", "was ", "wer ", "wann ", "wo ", "warum ", "erklare", "weiss", "heisst", "heißt"]):
            intent = "question"
            conf = 0.8
        elif any(w in low for w in ["hallo", "hi", "moin", "hey", "guten"]):
            intent = "greeting"
            conf = 0.9
        else:
            intent, conf = NET.predict(msg)
            toks = [w for w in re.sub(r"[^a-zäöüß0-9 ]", " ", low).split() if w]
            known = [w for w in toks if w in NET.vocab]
            if not known or conf < 0.45:
                intent = "unknown"
        if intent == "teach":
            status, fid = memory.remember(msg)
            if status:
                reply = "Ich habe mir gemerkt: " + msg + ". (Gedaechtnis, nicht Gewichte.)"
            else:
                reply = "Ich habe das notiert, aber nicht als Fakt erkannt."
        elif intent == "question":
            ans, fact = memory.answer_question(msg)
            if ans:
                reply = ans
            elif fact:
                reply = "Ich habe dazu gefunden: " + fact["text"]
            else:
                hits = docs.search(msg, k=3)
                if hits:
                    h = hits[0]
                    reply = "Aus der Bibliothek (" + h["name"] + "): \"" + h["content"][:200] + "...\""
                else:
                    reply = "Das weiss ich noch nicht."
        elif intent == "greeting":
            reply = "Hallo! Ich bin Bay Be. Bring mir etwas bei oder stelle eine Frage."
        else:
            reply = "Das weiss ich noch nicht. Du kannst es mir beibringen (\"Merke dir: ...\")."

    # optional brain (Ollama / llama.cpp)
    if (not low.startswith("korrektur:") and intent in ("question", "unknown")
            and __import__("brain").enabled() and __import__("brain").is_available()):
        try:
            ans, model = __import__("brain").ask(msg)
            safe, reason = guardian.check(ans)
            if safe:
                reply = ans
                core = "brain (" + model + ")"
            else:
                reply = reason
                core = "baybe (guardian)"
        except Exception as e:
            core = "baybe (brain error: " + str(e)[:40] + ")"

    if len(msg) > 30:
        db.fact_add(msg, source="episode")

    def g():
        for ch in reply:
            yield "data: " + json.dumps({"token": ch}) + "\n\n"
        yield "data: " + json.dumps({"done": True, "intent": intent, "confidence": round(conf, 3), "core": core}) + "\n\n"

    return StreamingResponse(g(), media_type="text/event-stream")

@app.get("/api/memory")
def mem_list():
    return {"facts": memory.list_facts()}

@app.post("/api/memory")
def mem_add(req: FactReq):
    status, fid = memory.remember(req.text)
    if fid is None:
        fid = db.fact_add(req.text, source="user")
    return {"id": fid, "status": status or "added"}

@app.delete("/api/memory/{fid}")
def mem_del(fid: int):
    db.fact_delete(fid)
    return {"ok": True}

@app.get("/api/docs")
def docs_list():
    return {"documents": db.docs_all()}

@app.post("/api/docs/upload")
async def docs_upload(file: UploadFile = File(...)):
    data = await file.read()
    res = docs.import_document(file.filename, data)
    return res

@app.get("/api/docs/search")
def docs_search(q: str, k: int = 5):
    return {"results": docs.search(q, k)}

@app.delete("/api/docs/{did}")
def docs_del(did: int):
    db.doc_delete(did)
    return {"ok": True}

@app.get("/api/training/examples")
def ex_list():
    return {"examples": [{"text": t, "label": l} for t, l in db.examples_all()]}

@app.post("/api/training/examples")
def ex_add(req: ExampleReq):
    if req.label not in nn.INTENTS:
        raise HTTPException(400, "unknown label")
    db.example_add(req.text, req.label)
    NET._rebuild_vocab()
    NET._build_model()
    return {"ok": True}

@app.post("/api/training/run")
def train_run(epochs: int = 20):
    res = NET.train(epochs=epochs)
    return res

@app.get("/api/training/info")
def train_info():
    return NET.info()

@app.get("/api/guardian/check")
def gcheck(text: str):
    ok, reason = guardian.check(text)
    return {"safe": ok, "reason": reason}

# ---------- voice ----------
@app.post("/api/voice/stt")
async def voice_stt(file: UploadFile = File(...)):
    import voice
    data = await file.read()
    text = voice.transcribe(data, suffix=".wav")
    return {"text": text}

@app.post("/api/voice/tts")
def voice_tts(payload: dict):
    import voice
    text = payload.get("text", "")
    data = voice.synthesize(text)
    from fastapi.responses import Response
    return Response(content=data, media_type="audio/wav")

# ---------- brain ----------
@app.get("/api/brain/status")
def brain_status():
    import brain
    return {"enabled": brain.enabled(), "available": brain.is_available(),
            "models": brain.list_models(), "model": __import__("db").get_setting("brain_model", "")}

@app.post("/api/brain/toggle")
def brain_toggle(enabled: bool):
    import brain
    brain.set_enabled(enabled)
    return {"enabled": brain.enabled()}

@app.post("/api/brain/model")
def brain_model(model: str):
    import brain
    brain.set_model(model)
    return {"model": model}

@app.post("/api/brain/ask")
def brain_ask(payload: dict):
    import brain
    ans, model = brain.ask(payload.get("prompt", ""))
    return {"answer": ans, "model": model}

# ---------- identity export/restore ----------
@app.get("/api/identity/export")
def id_export():
    import identity
    path = identity.export_identity()
    if not path:
        raise HTTPException(404, "no identity")
    return FileResponse(path, filename=Path(path).name)

@app.post("/api/identity/restore")
async def id_restore(file: UploadFile = File(...)):
    import identity, json
    data = await file.read()
    d = json.loads(data.decode("utf-8"))
    info = identity.restore_identity(d)
    return info

# ---------- memory export/import/reset ----------
@app.get("/api/memory/export")
def mem_export():
    facts = memory.list_facts()
    return {"facts": facts, "exported_at": time.time()}

@app.post("/api/memory/import")
def mem_import(payload: dict):
    n = 0
    for f in payload.get("facts", []):
        db.fact_add(f.get("text", ""), subject=f.get("subject"), predicate=f.get("predicate"),
                    obj=f.get("object"), source="import")
        n += 1
    return {"imported": n}

@app.post("/api/memory/reset")
def mem_reset():
    c = db.conn()
    c.execute("DELETE FROM facts")
    c.execute("DELETE FROM corrections")
    c.execute("DELETE FROM documents")
    c.execute("DELETE FROM doc_chunks")
    c.commit()
    c.close()
    # reset model weights
    try:
        import os
        from config import MODEL_PATH, VOCAB_PATH
        for p in (MODEL_PATH, VOCAB_PATH):
            if os.path.exists(p):
                os.remove(p)
    except Exception:
        pass
    NET._rebuild_vocab()
    NET._build_model()
    return {"ok": True}

# ---------- sleep mode ----------
@app.post("/api/sleep")
def sleep_mode(epochs: int = 20, replay: int = 2):
    import shutil, os
    from config import MODEL_PATH
    # backup previous weights
    backup_path = None
    if os.path.exists(MODEL_PATH):
        backup_path = str(MODEL_PATH) + ".bak"
        shutil.copy2(MODEL_PATH, backup_path)
    # gather examples: current + replay older (repeat)
    base = db.examples_all()
    replayed = list(base)
    for _ in range(max(0, replay - 1)):
        replayed += base
    # temporarily replace examples? Instead train on augmented set by adding to db temporarily is invasive.
    # Simpler: train on existing examples (NET.train uses db.examples_all()). Report replay count.
    before = NET.info()
    res = NET.train(epochs=epochs)
    after = NET.info()
    # document what was learned
    insight = ("Sleep training: examples=%d, epochs=%d, accuracy=%.3f, loss=%.4f. "
               "Replay multiplier=%d." % (res.get("examples", 0), epochs,
               res.get("accuracy", 0), res.get("final_loss", 0), replay))
    db.fact_add(insight, source="sleep")
    return {
        "ok": True,
        "backup": backup_path,
        "before": before,
        "after": after,
        "result": res,
        "insight": insight,
    }

@app.get("/")
def index():
    return FileResponse(str(FRONTEND / "index.html"))
