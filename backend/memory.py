import db
import re

REMEMBER_PREFIXES = [
    # German
    "merke dir:", "merk dir:", "merke:", "notiere:", "speichere:",
    # English
    "remember:", "remember ", "note:", "note ", "save:", "save ", "store:", "store ",
    # Spanish
    "recuerda:", "recuerda ", "anota:", "anota ", "guarda:", "guarda ",
]

# Normalize subject nouns across languages to a canonical English key
SUBJECT_ALIASES = {
    "hund": "dog", "perro": "dog", "dog": "dog", "chien": "dog",
    "katze": "cat", "gato": "cat", "cat": "cat", "chat": "cat",
    "auto": "car", "coche": "car", "car": "car", "voiture": "car",
    "name": "name", "nombre": "name",
}

def _canon_subject(s):
    return SUBJECT_ALIASES.get(s.lower(), s.lower())

SUBJECT_PATTERNS = [
    # German: "mein X heißt/ist Y"
    r"mein (\w+) (?:hei(?:ß|ss)t|ist|name ist) (.+)",
    # English: "my X is Y", "my X is called Y", "my X name is Y"
    r"my (\w+) (?:is called|is named|name is|is) (.+)",
    # Spanish: "mi X se llama Y", "mi X es Y"
    r"mi (\w+) (?:se llama|es) (.+)",
]

QUESTION_PATTERNS = [
    # German
    r"wie hei(?:ß|ss)t mein (\w+)",
    r"was ist mein (\w+)",
    # English
    r"what(?:'s| is) my (\w+)",
    r"what is the name of my (\w+)",
    r"how (?:is|does) my (\w+)",
    # Spanish
    r"c[oó]mo se llama mi (\w+)",
    r"cu[aá]l es mi (\w+)",
    r"qu[eé] es mi (\w+)",
]

def _strip_prefix(text):
    low = text.lower().strip()
    for prefix in REMEMBER_PREFIXES:
        if low.startswith(prefix):
            return text[len(prefix):].strip(), True
    return text, False

def parse_fact(text):
    t = text.strip()
    body, had_prefix = _strip_prefix(t)
    for pat in SUBJECT_PATTERNS:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            subj, obj = m.group(1), m.group(2).rstrip(".")
            subj = _canon_subject(subj)
            return f"subject={subj};object={obj};text={body}"
    if had_prefix:
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
            db.fact_update(existing[0]["id"], text if False else parsed.split("text=",1)[-1], subject=subj, obj=obj)
            return "updated", existing[0]["id"]
        fid = db.fact_add(parsed.split("text=",1)[-1], subject=subj, predicate="is", obj=obj, source="user")
        return "added", fid
    if parsed:
        fid = db.fact_add(parsed, source="user")
        return "added", fid
    fid = db.fact_add(text, source="user")
    return "added", fid

def correct(text):
    t = text.strip()
    low = t.lower()
    # multilingual correction prefixes
    for prefix in ["korrektur:", "correction:", "correccion:", "corrección:"]:
        if low.startswith(prefix):
            body = t[len(prefix):].strip()
            # try subject pattern
            for pat in SUBJECT_PATTERNS:
                m = re.search(pat, body, re.IGNORECASE)
                if m:
                    subj, obj = m.group(1), m.group(2).rstrip(".")
                    subj = _canon_subject(subj)
                    existing = db.fact_find_by_subject(subj)
                    if existing:
                        db.fact_update(existing[0]["id"], body, subject=subj, obj=obj)
                        db.correction_add(text, body)
                        return "Thanks, updated: your " + subj + " is now " + obj + "."
                    fid = db.fact_add(body, subject=subj, predicate="is", obj=obj, source="user")
                    db.correction_add(text, body)
                    return "Stored: your " + subj + " is " + obj + "."
            db.fact_add(body, source="correction")
            db.correction_add(text, body)
            return "Thanks, updated."
    return None

def answer_question(text):
    low = text.lower()
    for pat in QUESTION_PATTERNS:
        m = re.search(pat, low)
        if m:
            subj = _canon_subject(m.group(1))
            facts = db.fact_find_by_subject(subj)
            if facts:
                f = facts[0]
                return "Your " + subj + " is " + (f["object"] or f["text"]) + ".", f
    hits = db.facts_search(text)
    if hits:
        return None, hits[0]
    return None, None

def list_facts():
    return db.facts_all()
