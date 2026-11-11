import base64
import json
import time
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

import db
from config import IDENTITY_PATH, DATA_DIR

EXPORT_DIR = DATA_DIR / "identity_exports"
EXPORT_DIR.mkdir(exist_ok=True)

def _load():
    if IDENTITY_PATH.exists():
        try:
            return json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def _save(d):
    IDENTITY_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")

def create(name):
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    pub_b64 = base64.b64encode(priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).decode("ascii")
    d = {
        "name": name,
        "public_key_pem": pub_pem,
        "public_key_b64": pub_b64,
        "private_key_pem": priv_pem,
        "created_at": time.time(),
        "registered": False,
        "reg_code": None,
    }
    _save(d)
    # also mirror name in db for convenience
    c = db.conn()
    c.execute("INSERT OR REPLACE INTO identity(id,name,pubkey,privkey,created_at,registered) VALUES (1,?,?,?,?,0)",
              (name, pub_b64, priv_pem, time.time()))
    c.commit()
    c.close()
    return {"name": name, "public_key": pub_b64, "created_at": d["created_at"]}

def get():
    d = _load()
    if not d:
        return None
    return {
        "name": d["name"],
        "public_key": d["public_key_b64"],
        "created_at": d["created_at"],
        "registered": d.get("registered", False),
        "reg_code": d.get("reg_code"),
    }

def sign(message):
    d = _load()
    if not d:
        return None
    priv = serialization.load_pem_private_key(d["private_key_pem"].encode("utf-8"), password=None)
    sig = priv.sign(message.encode("utf-8"))
    return base64.b64encode(sig).decode("ascii")

def verify(message, signature_b64, public_key_b64=None):
    d = _load()
    if public_key_b64 is None and d:
        public_key_b64 = d["public_key_b64"]
    if not public_key_b64:
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        raw = base64.b64decode(public_key_b64)
        pub = Ed25519PublicKey.from_public_bytes(raw)
        pub.verify(base64.b64decode(signature_b64), message.encode("utf-8"))
        return True
    except (InvalidSignature, Exception):
        return False

def export_identity():
    d = _load()
    if not d:
        return None
    path = EXPORT_DIR / f"{d['name']}_identity.json"
    # export includes private key - warn
    path.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return str(path)

def restore_identity(data: dict):
    if "private_key_pem" not in data or "public_key_b64" not in data:
        raise ValueError("invalid identity file")
    _save(data)
    return {"name": data["name"], "public_key": data["public_key_b64"]}

def register(code):
    d = _load()
    if not d:
        return False
    d["registered"] = True
    d["reg_code"] = code
    _save(d)
    return True
