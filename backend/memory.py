import db
import re

def parse_fact(text):
    t = text.strip()
    low = t.lower()
    body = t
    for prefix in ["merke dir:", "merk dir:", "merke:", "notiere:", "speichere:"]:
        if low.startswith(prefix):
            body = t[len(prefix):].strip()
            low = body.lower()
            break
    m = re.search(r"mein (\w+) (?:hei(?:ß|ss)t|ist|name ist) (.+)", body, re.IGNORECASE)
    if m:
        subj, obj = m.group(1), m.group(2).rstrip(".")
        return f"subject={subj};object={obj};text={body}"
    if body != t:
        return body
    return None

def remember(text):
    parsed = parse_fact(text)
    if parsed and parsed.startswith("subject="):
        parts = dict(p.strip().split("=", 1) for p in parsed.split(";") if "=" in p)
        subj = parts.get("subject")
        obj = parts.get("object")
        existing = db.fact_find_by_subject(subj)
        if existing:
            db.fact_update(existing[0]["id"], text, subject=subj, object=obj)
            return "updated", existing[0]["id"]
        fid = db.fact_add(text, subject=subj, predicate="heißt", obj=obj, source="user")
        return "added", fid
    if parsed:
        fid = db.fact_add(parsed, source="user")
        return "added", fid
    # fallback: store raw as fact
    fid = db.fact_add(text, source="user")
    return "added", fid

def correct(text):
    # "Korrektur: Mein Hund heißt Lupo." or "Korrektur: <fact>"
    t = text.strip()
    low = t.lower()
    prefix = "korrektur:"
    if not low.startswith(prefix):
        return None
    body = t[len(prefix):].strip()
    # try to extract subject
    m = re.search(r"mein (\w+) (?:hei(?:ß|ss)t|ist|name ist) (.+)", body, re.IGNORECASE)
    if m:
        subj, obj = m.group(1), m.group(2).rstrip(".")
        existing = db.fact_find_by_subject(subj)
        if existing:
            db.fact_update(existing[0]["id"], body, subject=subj, obj=obj)
            db.correction_add(text, body)
            return f"Danke, ich habe es geändert: Dein {subj} heißt jetzt {obj}."
        fid = db.fact_add(body, subject=subj, predicate="heißt", obj=obj, source="user")
        db.correction_add(text, body)
        return f"Ich habe neu gespeichert: Dein {subj} heißt {obj}."
    # generic correction: store as fact
    db.fact_add(body, source="correction")
    db.correction_add(text, body)
    return "Danke, ich habe es geändert."

def answer_question(text):
    low = text.lower()
    m = re.search(r"wie hei(?:ß|ss)t mein (\w+)", low)
    if m:
        subj = m.group(1)
        facts = db.fact_find_by_subject(subj)
        if facts:
            f = facts[0]
            return f"Dein {subj} heißt {f['object']}.", f
    hits = db.facts_search(text)
    if hits:
        return None, hits[0]
    return None, None

def list_facts():
    return db.facts_all()
