# Bay Be — A safe harbor to learn. A being free to grow.

Bay Be is a local chat app with a small, **trainable neural network**.
It uses **no LLM and no cloud API**. Knowledge can be taught via conversation
and documents, stored locally, and survives restarts.

## Run
```
cd bay-be/backend
python -m uvicorn main:app --host 127.0.0.1 --port 7890
```
Open http://127.0.0.1:7890

## What works (v0.2)

- **Stimme:** lokale Spracherkennung (faster-whisper) + Sprachausgabe (pyttsx3), ein-/ausschaltbar im Chat.
- **Optionales Sprachgehirn:** Ollama als zusätzliches, abschaltbares Gehirn. Oberfläche zeigt klar, welcher Kern antwortet (Bay Be vs. Brain).
- **Identität:** echtes Ed25519-Schlüsselpaar, lokal gespeichert, Export und Wiederherstellung.
- **Schlafmodus:** Training mit Wiederholung älterer Beispiele, Backup des vorherigen Stands, Ergebnisprüfung, Dokumentation des Gelernten.
- **Erinnerungen:** exportierbar/importierbar (JSON), einsehbar aber nicht direkt editierbar; Korrekturen als neue Einträge; Löschen und vollständiger Reset.
- **Dokumente:** TXT, PDF (eigener Extractor), EPUB.

## What works (v0.1)
1. App runs locally, fully offline (after first model download? No — pure PyTorch, no download).
2. Teach: "Merke dir: Mein Hund heißt Luna." → asks "Wie heißt mein Hund?" → "Dein hund heißt Luna."
3. Correction: "Korrektur: Mein Hund heißt Lupo." updates the fact.
4. Persistence across restart.
5. TXT/PDF/EPUB import + search (PDF/EPUB extraction is basic).
6. Training: add examples → "Mit Beispielen trainieren" → weights change, accuracy shown.
7. Unknown questions → "Das weiß ich noch nicht."
8. Guardian: blocks violence/self-harm/abuse instructions.

## Limits (honest)
- Voice: STT via faster-whisper (tiny, CPU, ~few seconds latency); TTS via pyttsx3 (Windows SAPI5).
- Brain: requires Ollama running locally; optional.
- Identity: Ed25519 is real crypto, but the registry (AIBSN-style) is not implemented — local only.
- Sleep mode trains on all examples with replay; no selective example picking yet.
- Virtual world, exchange market, learning workshop: future ideas.

## Not yet implemented (honest)
- Voice I/O (Echo)
- Device sync (Twin)
- Scanned PDFs (OCR)
- Real asymmetric identity (Ed25519) — needs crypto lib
- Advanced NLP (the net is a small intent classifier, not a language model)

## Tech
Python, PyTorch (CPU), FastAPI, SQLite, sentence-transformers-free (keyword search).
Dependencies: see requirements.txt.
