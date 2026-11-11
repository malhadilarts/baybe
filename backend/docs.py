import io
import re
import zipfile
import db

def _chunk(text, size=900):
    out = []
    cur = ""
    for para in text.split("\n"):
        if len(cur) + len(para) > size:
            if cur.strip():
                out.append(cur.strip())
            cur = para + "\n"
        else:
            cur += para + "\n"
    if cur.strip():
        out.append(cur.strip())
    return out

def extract_text_pdf(data: bytes) -> str:
    # minimal PDF text extractor: find text between BT/ET, Tj/TJ
    text = ""
    try:
        # decode streams roughly
        import zlib
        # find all stream...endstream
        for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
            raw = m.group(1)
            try:
                d = zlib.decompress(raw)
            except Exception:
                d = raw
            # extract text operators
            for tm in re.finditer(rb"\((?:\\.|[^()])*\)\s*Tj", d):
                s = tm.group(0)
                # extract parenthesized
                for pm in re.finditer(rb"\((?:\\.|[^()])*\)", s):
                    val = pm.group(0)[1:-1]
                    try:
                        val = val.decode("latin-1")
                    except Exception:
                        val = val.decode("utf-8", errors="replace")
                    # handle escapes
                    val = val.replace("\\n", "\n").replace("\\r", "").replace("\\t", "\t")
                    val = re.sub(r"\\(\d{3})", lambda x: chr(int(x.group(1), 8)), val)
                    text += val + " "
            for tm in re.finditer(rb"\[(.*?)\]\s*TJ", d, re.S):
                arr = tm.group(1)
                for pm in re.finditer(rb"\((?:\\.|[^()])*\)", arr):
                    val = pm.group(0)[1:-1]
                    try:
                        val = val.decode("latin-1")
                    except Exception:
                        val = val.decode("utf-8", errors="replace")
                    val = val.replace("\\n", "\n")
                    text += val
                text += " "
    except Exception as e:
        text += f"\n[PDF extract error: {e}]"
    # fallback: if no text found, try raw
    if len(text.strip()) < 10:
        try:
            text = data.decode("latin-1", errors="replace")
        except Exception:
            pass
    return text

def extract_text_epub(data: bytes) -> str:
    text = ""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        for name in z.namelist():
            if name.lower().endswith((".xhtml", ".html", ".htm", ".xml")):
                raw = z.read(name)
                try:
                    s = raw.decode("utf-8", errors="replace")
                except Exception:
                    s = raw.decode("latin-1", errors="replace")
                # strip tags
                s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
                s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
                s = re.sub(r"<[^>]+>", " ", s)
                s = re.sub(r"\s+", " ", s)
                text += s + "\n"
    except Exception as e:
        text += f"\n[EPUB extract error: {e}]"
    return text

def extract_text_txt(data: bytes) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")

def import_document(name, data: bytes):
    low = name.lower()
    if low.endswith(".pdf"):
        text = extract_text_pdf(data)
    elif low.endswith(".epub"):
        text = extract_text_epub(data)
    else:
        text = extract_text_txt(data)
    chunks = _chunk(text)
    did = db.doc_add(name, text, len(chunks))
    for ch in chunks:
        db.chunk_add(did, ch)
    return {"id": did, "name": name, "chunks": len(chunks), "chars": len(text)}

def search(query, k=5):
    return db.chunks_search(query, k=k)
