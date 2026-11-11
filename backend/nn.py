import json
import os
import re
import torch
import torch.nn as nn
from config import VOCAB_PATH, MODEL_PATH, DEVICE

INTENTS = ["greeting", "teach", "question", "unknown"]
INTENT_LABELS_DE = {
    "greeting": "Begrüßung",
    "teach": "Lehraussage",
    "question": "Wissensfrage",
    "unknown": "unbekannt",
}

# seed examples
SEED_EXAMPLES = [
    ("hallo", "greeting"),
    ("hi", "greeting"),
    ("guten tag", "greeting"),
    ("moin", "greeting"),
    ("hey", "greeting"),
    ("merke dir", "teach"),
    ("merk dir", "teach"),
    ("speichere", "teach"),
    ("notiere", "teach"),
    ("mein hund heißt", "teach"),
    ("wie heißt", "question"),
    ("was ist", "question"),
    ("wer ist", "question"),
    ("wann", "question"),
    ("wo ist", "question"),
    ("erkläre", "question"),
    ("was weißt du", "question"),
    ("xyzabc nonsense", "unknown"),
]

def _tokenize(text):
    text = text.lower()
    text = re.sub(r"[^a-zäöüß0-9 ]", " ", text)
    return [w for w in text.split() if w]

class IntentNet(nn.Module):
    def __init__(self, vocab_size, hidden=32, num_classes=4):
        super().__init__()
        self.fc1 = nn.Linear(vocab_size, hidden)
        self.act = nn.ReLU()
        self.fc2 = nn.Linear(hidden, num_classes)

    def forward(self, x):
        return self.fc2(self.act(self.fc1(x)))

class NNC:
    def __init__(self):
        self.vocab = {}
        self.model = None
        self._load_vocab()
        self._build_model()
        self._seed_if_empty()

    def _load_vocab(self):
        if os.path.exists(VOCAB_PATH):
            try:
                self.vocab = json.load(open(VOCAB_PATH, encoding="utf-8"))
            except Exception:
                self.vocab = {}
        if not self.vocab:
            self._rebuild_vocab()

    def _rebuild_vocab(self):
        words = set()
        for text, _ in SEED_EXAMPLES:
            for w in _tokenize(text):
                words.add(w)
        # also include db examples
        try:
            import db
            for t, _ in db.examples_all():
                for w in _tokenize(t):
                    words.add(w)
        except Exception:
            pass
        self.vocab = {w: i for i, w in enumerate(sorted(words))}
        self._save_vocab()

    def _save_vocab(self):
        with open(VOCAB_PATH, "w", encoding="utf-8") as f:
            json.dump(self.vocab, f, ensure_ascii=False, indent=1)

    def _build_model(self):
        vs = max(1, len(self.vocab))
        self.model = IntentNet(vs).to(DEVICE)
        if os.path.exists(MODEL_PATH):
            try:
                self.model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE))
            except Exception:
                pass

    def _vectorize(self, text):
        v = torch.zeros(len(self.vocab), device=DEVICE)
        for w in _tokenize(text):
            if w in self.vocab:
                v[self.vocab[w]] += 1.0
        # normalize
        n = v.norm()
        if n > 0:
            v = v / n
        return v

    def _seed_if_empty(self):
        import db
        if not db.examples_all():
            for text, label in SEED_EXAMPLES:
                db.example_add(text, label)
        # rebuild vocab including any new words
        self._rebuild_vocab()
        self._build_model()

    def predict(self, text):
        if not self.vocab:
            return "unknown", 0.0
        # Do NOT mutate vocab/model during inference: unknown words are ignored
        # (OOV). Mutating here would resize the net and discard learned weights.
        with torch.no_grad():
            x = self._vectorize(text).unsqueeze(0)
            logits = self.model(x)
            probs = torch.softmax(logits, dim=1)
            idx = int(torch.argmax(probs, dim=1).item())
            conf = float(probs[0, idx].item())
        # If no known words, force unknown
        if not any(w in self.vocab for w in _tokenize(text)):
            return "unknown", 0.0
        return INTENTS[idx], conf

    def train(self, examples=None, epochs=20, lr=0.01):
        import db
        if examples is None:
            examples = db.examples_all()
        if not examples:
            return {"ok": False, "reason": "no examples"}
        # rebuild vocab
        self._rebuild_vocab()
        self._build_model()
        xs = torch.stack([self._vectorize(t) for t, _ in examples])
        ys = torch.tensor([INTENTS.index(l) for _, l in examples], dtype=torch.long, device=DEVICE)
        opt = torch.optim.Adam(self.model.parameters(), lr=lr)
        loss_fn = nn.CrossEntropyLoss()
        losses = []
        for _ in range(epochs):
            opt.zero_grad()
            logits = self.model(xs)
            loss = loss_fn(logits, ys)
            loss.backward()
            opt.step()
            losses.append(float(loss.item()))
        torch.save(self.model.state_dict(), MODEL_PATH)
        db.set_setting("trained_at", __import__("time").time())
        # accuracy
        with torch.no_grad():
            preds = torch.argmax(self.model(xs), dim=1)
            acc = float((preds == ys).float().mean().item())
        return {"ok": True, "epochs": epochs, "final_loss": losses[-1], "accuracy": acc,
                "examples": len(examples), "vocab_size": len(self.vocab)}

    # Held-out paraphrases (never trained on) for generalization testing
    UNSEEN = {
        "greeting": ["guten morgen", "servus", "na du", "gruess dich", "morgen zusammen"],
        "teach": ["speicher das bitte", "notier dir das", "das ist wichtig", "behalte das", "schreib dir auf"],
        "question": ["erklare mir das", "wann passiert das", "wo finde ich das", "wer bist du", "was kannst du"],
        "unknown": ["asdfghjkl", "blubber quark", "xzyqwp", "random noise text", "12345 abc"],
    }

    def eval_unseen(self):
        results = {}
        correct = 0
        total = 0
        for label, phrases in self.UNSEEN.items():
            hits = 0
            for p in phrases:
                pred, conf = self.predict(p)
                ok = (pred == label)
                if ok:
                    hits += 1
                    correct += 1
                total += 1
                results.setdefault(label, []).append({"text": p, "pred": pred, "conf": round(conf, 3), "ok": ok})
        per_intent = {k: sum(1 for r in v if r["ok"]) / len(v) for k, v in results.items()}
        return {
            "per_intent": per_intent,
            "overall": correct / total if total else 0.0,
            "correct": correct,
            "total": total,
            "details": results,
        }
