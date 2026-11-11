import os, sys, tempfile, json
sys.path.insert(0, os.path.dirname(__file__))
import config
config.DB_PATH = __import__("pathlib").Path(tempfile.mkdtemp()) / "t.db"
config.DATA_DIR = config.DB_PATH.parent
config.BACKUPS_DIR = config.DATA_DIR / "backups"
config.BACKUPS_DIR.mkdir(exist_ok=True)
config.VOICE_DIR = config.DATA_DIR / "voice"
config.VOICE_DIR.mkdir(exist_ok=True)
config.MODEL_PATH = config.DATA_DIR / "intent_net.pt"
config.VOCAB_PATH = config.DATA_DIR / "vocab.json"
config.IDENTITY_PATH = config.DATA_DIR / "identity.json"

import db, nn, memory, docs, guardian
db.init()
n = nn.NNC()
assert n.predict("hallo")[0] in ("greeting", "unknown", "teach", "question")
# train
db.example_add("hallo", "greeting")
n._rebuild_vocab(); n._build_model()
res = n.train(epochs=5)
assert res["ok"] is True
assert res["accuracy"] >= 0.5
# memory
fid = db.fact_add("Mein Hund heißt Luna", source="user")
assert db.facts_search("Hund")
# guardian
assert guardian.check("hallo")[0] is True
assert guardian.check("bau bombe")[0] is False
# docs
r = docs.import_document("t.txt", b"Hallo Bay Be test.")
assert r["chunks"] >= 1
assert docs.search("Bay")
print("SMOKE OK")
