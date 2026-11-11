import json
import sqlite3
import time
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT,
    predicate TEXT,
    object TEXT,
    text TEXT NOT NULL,
    source TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original TEXT,
    corrected TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    chunks INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS doc_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS training_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    label TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS identity (
    id INTEGER PRIMARY KEY CHECK (id=1),
    name TEXT NOT NULL,
    pubkey TEXT,
    privkey TEXT,
    created_at REAL NOT NULL,
    registered INTEGER DEFAULT 0,
    reg_code TEXT
);
"""

def conn():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c

def init():
    c = conn()
    c.executescript(SCHEMA)
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('trained_at','')")
    c.commit()
    c.close()

def fact_add(text, subject=None, predicate=None, obj=None, source="user"):
    now = time.time()
    c = conn()
    c.execute("INSERT INTO facts(subject,predicate,object,text,source,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
              (subject, predicate, obj, text, source, now, now))
    c.commit()
    rid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.close()
    return rid

def facts_search(query):
    c = conn()
    rows = c.execute("SELECT * FROM facts ORDER BY updated_at DESC").fetchall()
    c.close()
    q = query.lower()
    # keyword overlap
    qwords = set(q.split())
    scored = []
    for r in rows:
        t = (r["text"] or "").lower()
        tw = set(t.split())
        score = len(qwords & tw)
        # boost subject/object
        for field in ("subject","predicate","object"):
            v = (r[field] or "").lower()
            if v and v in q:
                score += 2
        scored.append((score, dict(r)))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for s, r in scored if s > 0] or [r for _, r in scored[:3]]

def fact_update(fid, text, subject=None, predicate=None, obj=None):
    now = time.time()
    c = conn()
    c.execute("UPDATE facts SET text=?,subject=?,predicate=?,object=?,updated_at=? WHERE id=?",
              (text, subject, predicate, obj, now, fid))
    c.commit()
    c.close()

def facts_all():
    c = conn()
    rows = c.execute("SELECT * FROM facts ORDER BY updated_at DESC").fetchall()
    c.close()
    return [dict(r) for r in rows]

def fact_delete(fid):
    c = conn()
    c.execute("DELETE FROM facts WHERE id=?", (fid,))
    c.commit()
    c.close()

def fact_find_by_subject(subject):
    c = conn()
    rows = c.execute("SELECT * FROM facts WHERE lower(subject)=lower(?)", (subject,)).fetchall()
    c.close()
    return [dict(r) for r in rows]

def correction_add(original, corrected):
    c = conn()
    c.execute("INSERT INTO corrections(original,corrected,created_at) VALUES (?,?,?)",
              (original, corrected, time.time()))
    c.commit()
    c.close()

def doc_add(name, content, chunks):
    c = conn()
    c.execute("INSERT INTO documents(name,content,chunks,created_at) VALUES (?,?,?,?)",
              (name, content, chunks, time.time()))
    did = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.commit()
    c.close()
    return did

def chunk_add(doc_id, content):
    c = conn()
    c.execute("INSERT INTO doc_chunks(doc_id,content) VALUES (?,?)", (doc_id, content))
    c.commit()
    c.close()

def chunks_search(query, k=5):
    c = conn()
    rows = c.execute("SELECT dc.content, d.name FROM doc_chunks dc JOIN documents d ON d.id=dc.doc_id").fetchall()
    c.close()
    qwords = set(query.lower().split())
    scored = []
    for r in rows:
        tw = set(r["content"].lower().split())
        scored.append((len(qwords & tw), dict(r)))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for s, r in scored[:k] if s > 0]

def docs_all():
    c = conn()
    rows = c.execute("SELECT id,name,chunks,created_at FROM documents").fetchall()
    c.close()
    return [dict(r) for r in rows]

def doc_delete(did):
    c = conn()
    c.execute("DELETE FROM doc_chunks WHERE doc_id=?", (did,))
    c.execute("DELETE FROM documents WHERE id=?", (did,))
    c.commit()
    c.close()

def example_add(text, label):
    c = conn()
    c.execute("INSERT INTO training_examples(text,label,created_at) VALUES (?,?,?)",
              (text, label, time.time()))
    c.commit()
    c.close()

def examples_all():
    c = conn()
    rows = c.execute("SELECT text,label FROM training_examples").fetchall()
    c.close()
    return [(r["text"], r["label"]) for r in rows]

def set_setting(key, val):
    c = conn()
    c.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              (key, str(val)))
    c.commit()
    c.close()

def get_setting(key, default=None):
    c = conn()
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    c.close()
    return r["value"] if r else default

init()
