import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "baybe.db"
IDENTITY_PATH = DATA_DIR / "identity.json"
MODEL_PATH = DATA_DIR / "intent_net.pt"
VOCAB_PATH = DATA_DIR / "vocab.json"

HOST = "127.0.0.1"
PORT = 7890
DEVICE = "cpu"
OLLAMA_URL = "http://127.0.0.1:11434"
VERSION = "0.1.0"
APP_NAME = "Bay Be"
TAGLINE = "A safe harbor to learn. A being free to grow."
