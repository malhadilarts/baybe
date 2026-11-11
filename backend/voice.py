import os
import tempfile
import wave
from pathlib import Path
from config import DATA_DIR

VOICE_DIR = DATA_DIR / "voice"
VOICE_DIR.mkdir(exist_ok=True)

_whisper = None

def _whisper_model():
    global _whisper
    if _whisper is None:
        try:
            from faster_whisper import WhisperModel
            _whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
        except Exception as e:
            _whisper = False
            raise RuntimeError(f"whisper unavailable: {e}")
    if _whisper is False:
        raise RuntimeError("whisper unavailable")
    return _whisper

def transcribe(audio_bytes, suffix=".wav"):
    # write to temp file
    fd, path = tempfile.mkstemp(suffix=suffix, dir=str(VOICE_DIR))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio_bytes)
        model = _whisper_model()
        segments, info = model.transcribe(path, language="de")
        text = " ".join(s.text.strip() for s in segments)
        return text.strip()
    finally:
        try:
            os.remove(path)
        except Exception:
            pass

def synthesize(text):
    import pyttsx3
    out_path = str(VOICE_DIR / "tts_out.wav")
    engine = pyttsx3.init()
    engine.setProperty("rate", 160)
    engine.save_to_file(text, out_path)
    engine.runAndWait()
    if os.path.exists(out_path):
        with open(out_path, "rb") as f:
            data = f.read()
        try:
            os.remove(out_path)
        except Exception:
            pass
        return data
    raise RuntimeError("tts failed")
