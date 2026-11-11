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
- **Optionales Sprachgehirn:** Ollama als zusaetzliches, abschaltbares Gehirn (llama.cpp optional). Oberflaeche zeigt klar, welcher Kern antwortet (Bay Be vs. Brain).
- **Identitaet:** echtes Ed25519-Schluesselpaar, lokal gespeichert, Export und Wiederherstellung.
- **Schlafmodus:** Training mit Wiederholung aelterer Beispiele, Backup des vorherigen Stands, Ergebnispruefung, Dokumentation des Gelernten.
- **Erinnerungen:** exportierbar/importierbar (JSON), einsehbar aber nicht direkt editierbar; Korrekturen als neue Eintraege; Loeschen und vollstaendiger Reset.
- **Dokumente:** TXT, PDF (eigener Extractor), EPUB.

## What works (v0.1)
1. App runs locally, fully offline (pure PyTorch, no model download).
2. Teach: "Merke dir: Mein Hund heisst Luna." -> asks "Wie heisst mein Hund?" -> "Dein Hund heisst Luna."
3. Correction: "Korrektur: Mein Hund heisst Lupo." updates the fact.
4. Persistence across restart.
5. TXT/PDF/EPUB import + search (PDF/EPUB extraction is basic).
6. Training: add examples -> "Mit Beispielen trainieren" -> weights change, accuracy shown.
7. Unknown questions -> "Das weiss ich noch nicht."
8. Guardian: blocks violence/self-harm/abuse instructions.

## Limits (honest)
- Voice: STT via faster-whisper (tiny, CPU, ~few seconds latency); TTS via pyttsx3 (Windows SAPI5).
- Brain: requires Ollama running locally (optional). Direct llama.cpp requires llama-cpp-python (not installed by default).
- Identity: Ed25519 is real crypto, but there is no registry (AIBSN-style) — local only. Private key stored unencrypted at rest (warn).
- Sleep mode trains on all examples with replay; no selective example picking yet.
- Virtual world, exchange market, learning workshop: future ideas.
- The net is a small intent classifier, not a language model.

## Tech
Python, PyTorch (CPU), FastAPI, SQLite, cryptography (Ed25519), faster-whisper, pyttsx3.
Dependencies: see requirements.txt.

## First-run notes
- faster-whisper downloads the "tiny" model (~75 MB) on first STT use.
- pyttsx3 uses the OS text-to-speech (Windows SAPI5).
- Ollama is optional for the brain; Bay Be works fully without it.
