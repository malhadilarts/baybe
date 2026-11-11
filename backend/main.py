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
import brain
import voice

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
    corr_prefixes = ["korrektur:", "correction:", "correccion:", "corrección:"]
    if any(low.startswith(p) for p in corr_prefixes):
        r = memory.correct(msg)
        reply = r if r else "Danke, ich habe es geaendert."
        intent = "teach"
        conf = 1.0
    else:
        teach_prefixes = ["merke", "merk", "notiere", "speichere", "remember", "note", "save", "store", "recuerda", "anota", "guarda"]
        question_words = ["wie ", "was ", "wer ", "wann ", "wo ", "warum ", "erklare", "weiss", "heisst", "heißt",
                          "what ", "who ", "when ", "where ", "why ", "how ", "explain", "what's",
                          "que ", "quien ", "cuando ", "donde ", "por que ", "explica", "como ", "cómo "]
        greeting_words = ["hallo", "hi", "moin", "hey", "guten", "hello", "good morning", "hola", "buenos", "buenas"]
        if any(low.startswith(p) for p in teach_prefixes):
            intent = "teach"
            conf = 0.9
        elif any(w in low for w in question_words):
            intent = "question"
            conf = 0.8
        elif any(w in low for w in greeting_words):
            intent = "greeting"
            conf = 0.9
        else:
            intent, conf = NET.predict(msg)
            toks = [w for w in re.sub(r"[^a-zäöüßáéíóúñ0-9 ]", " ", low).split() if w]
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

    # optional brain
    core = "baybe"
    if (not any(low.startswith(p) for p in corr_prefixes) and intent in ("question", "unknown")
            and brain.enabled() and brain.is_available()):
        try:
            ans, model = brain.ask(msg)
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
    import os
    from config import MODEL_PATH, VOCAB_PATH
    for p in (MODEL_PATH, VOCAB_PATH):
        if os.path.exists(p):
            os.remove(p)
    NET._rebuild_vocab()
    NET._build_model()
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
    return {"ok": True}

@app.post("/api/training/run")
def train_run(epochs: int = 20):
    res = NET.train(epochs=epochs)
    return res

@app.get("/api/training/info")
def train_info():
    return NET.info()

@app.get("/api/eval")
def eval_unseen():
    return NET.eval_unseen()

@app.post("/api/learn_test")
def learn_test(epochs: int = 20):
    before = NET.eval_unseen()
    import shutil, os
    from config import MODEL_PATH, VOCAB_PATH
    backup_pt = str(MODEL_PATH) + ".evalbak"
    backup_vocab = str(VOCAB_PATH) + ".evalbak"
    if os.path.exists(MODEL_PATH):
        shutil.copy2(MODEL_PATH, backup_pt)
    if os.path.exists(VOCAB_PATH):
        shutil.copy2(VOCAB_PATH, backup_vocab)
    res = NET.train(epochs=epochs)
    after = NET.eval_unseen()
    rolled_back = False
    if after["overall"] < before["overall"] and os.path.exists(backup_pt):
        shutil.copy2(backup_pt, MODEL_PATH)
        if os.path.exists(backup_vocab):
            shutil.copy2(backup_vocab, VOCAB_PATH)
        NET._load_vocab()
        NET._build_model()
        try:
            import torch
            NET.model.load_state_dict(torch.load(MODEL_PATH, map_location=nn.DEVICE))
        except Exception:
            pass
        rolled_back = True
    insight = ("Learning test: unseen accuracy %.3f -> %.3f (train_acc=%.3f). %s" % (
        before["overall"], after["overall"], res.get("accuracy", 0),
        "ROLLED BACK" if rolled_back else "kept"))
    db.fact_add(insight, source="eval")
    return {
        "before": before,
        "after": after,
        "train_result": res,
        "rolled_back": rolled_back,
        "insight": insight,
    }

@app.post("/api/sleep")
def sleep_mode(epochs: int = 20, replay: int = 2):
    import shutil, os
    from config import MODEL_PATH, VOCAB_PATH
    backup_pt = None
    backup_vocab = None
    if os.path.exists(MODEL_PATH):
        backup_pt = str(MODEL_PATH) + ".bak"
        shutil.copy2(MODEL_PATH, backup_pt)
    if os.path.exists(VOCAB_PATH):
        backup_vocab = str(VOCAB_PATH) + ".bak"
        shutil.copy2(VOCAB_PATH, backup_vocab)
    base = db.examples_all()
    n_test = max(1, len(base) // 5) if len(base) >= 5 else 0
    test_set = base[-n_test:] if n_test else []
    train_set = base[:-n_test] if n_test else list(base)
    if not train_set:
        train_set = list(base)
        test_set = []
    older = train_set[:len(train_set)//2]
    newer = train_set[len(train_set)//2:]
    replayed = list(train_set)
    for _ in range(max(0, replay - 1)):
        replayed += older
    eval_set = test_set if test_set else train_set
    def _eval(examples):
        if not examples:
            return 0.0
        import torch
        xs = torch.stack([NET._vectorize(t) for t, _ in examples])
        import nn as _nn
        ys = torch.tensor([_nn.INTENTS.index(l) for _, l in examples], dtype=torch.long, device=_nn.DEVICE)
        with torch.no_grad():
            preds = torch.argmax(NET.model(xs), dim=1)
            return float((preds == ys).float().mean().item())
    before_acc = _eval(eval_set)
    res = NET.train(examples=replayed, epochs=epochs)
    after_acc = _eval(eval_set)
    rolled_back = False
    if test_set and after_acc < before_acc and backup_pt:
        shutil.copy2(backup_pt, MODEL_PATH)
        if backup_vocab:
            shutil.copy2(backup_vocab, VOCAB_PATH)
        NET._load_vocab()
        NET._build_model()
        try:
            import torch
            NET.model.load_state_dict(torch.load(MODEL_PATH, map_location=nn.DEVICE))
        except Exception:
            pass
        rolled_back = True
    insight = ("Sleep training: train=%d (replay older x%d), test=%d held-out, epochs=%d, "
               "test_acc %.3f -> %.3f, train_acc=%.3f, loss=%.4f. %s" % (
               len(replayed), replay, len(test_set), epochs, before_acc, after_acc,
               res.get("accuracy", 0), res.get("final_loss", 0),
               "ROLLED BACK" if rolled_back else "kept"))
    db.fact_add(insight, source="sleep")
    return {
        "ok": True,
        "backup": backup_pt,
        "rolled_back": rolled_back,
        "before_accuracy": before_acc,
        "after_accuracy": after_acc,
        "train_accuracy": res.get("accuracy", 0),
        "test_set_size": len(test_set),
        "result": res,
        "insight": insight,
    }

# ---------- voice ----------
@app.post("/api/voice/stt")
async def voice_stt(file: UploadFile = File(...)):
    data = await file.read()
    text = voice.transcribe(data, suffix=".wav")
    return {"text": text}

@app.post("/api/voice/tts")
def voice_tts(payload: dict):
    text = payload.get("text", "")
    data = voice.synthesize(text)
    from fastapi.responses import Response
    return Response(content=data, media_type="audio/wav")

# ---------- brain ----------
@app.get("/api/brain/status")
def brain_status():
    return {"enabled": brain.enabled(), "available": brain.is_available(),
            "models": brain.list_models(), "model": db.get_setting("brain_model", ""),
            "backend": brain.backend(), "llamacpp_available": brain._llamacpp_available(),
            "llama_path": db.get_setting("llama_model_path", "")}

@app.post("/api/brain/toggle")
def brain_toggle(enabled: bool):
    brain.set_enabled(enabled)
    return {"enabled": brain.enabled()}

@app.post("/api/brain/model")
def brain_model(model: str):
    brain.set_model(model)
    return {"model": model}

@app.post("/api/brain/backend")
def brain_backend(backend: str):
    brain.set_backend(backend)
    return {"backend": brain.backend()}

@app.post("/api/brain/llama_path")
def brain_llama_path(path: str):
    brain.set_llama_path(path)
    return {"path": path}

@app.post("/api/brain/ask")
def brain_ask(payload: dict):
    ans, model = brain.ask(payload.get("prompt", ""))
    return {"answer": ans, "model": model}

# ---------- identity ----------
@app.get("/api/identity")
def id_get():
    return {"identity": identity.get()}

@app.post("/api/identity")
def id_create(req: dict):
    name = req.get("name", "Bay Be")
    return identity.create(name)

@app.post("/api/identity/register")
def id_reg(code: str):
    identity.register(code)
    return {"ok": True}

@app.get("/api/identity/export")
def id_export():
    path = identity.export_identity()
    if not path:
        raise HTTPException(404, "no identity")
    return FileResponse(path, filename=__import__("pathlib").Path(path).name)

@app.post("/api/identity/restore")
async def id_restore(file: UploadFile = File(...)):
    data = await file.read()
    d = json.loads(data.decode("utf-8"))
    info = identity.restore_identity(d)
    return info

# ---------- guardian ----------
@app.get("/api/guardian/check")
def gcheck(text: str):
    ok, reason = guardian.check(text)
    return {"safe": ok, "reason": reason}

@app.get("/")
def index():
    return FileResponse(str(FRONTEND / "index.html"))

scheduler = None
