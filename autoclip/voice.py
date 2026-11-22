"""Rico Neon's voice.

Engines (config host.voice_engine):
- "chatterbox": free open-source model that copies Brian's voice but speaks with real emotion
  (Mochi 2026-11-22: Brian alone sounded robotic). Needs the Chatterbox env from the workflow
  (CHATTERBOX_PYTHON). Falls back to Edge Brian if it's missing, fails, or the audio looks wrong.
- "edge": free Microsoft Edge voice (Brian).
- "elevenlabs": paid, needs ELEVENLABS_API_KEY + host.elevenlabs_voice_id.
"""
import asyncio
import os
import subprocess
import tempfile

import requests

# ~20 s of Brian that Chatterbox copies the voice from (made once per run with Edge).
REF_LINE = ("Yo, what's up Leonida, it's your boy Rico Neon. Today we're looking at the wildest clips "
            "from GTA 6, and trust me, some of these are straight up unbelievable. Let's get into it.")
_ref_wav = None


def _edge(text: str, out_path: str, host: dict) -> str:
    import edge_tts

    async def _run():
        tts = edge_tts.Communicate(text, host["edge_voice"], rate=host["edge_rate"], pitch=host["edge_pitch"])
        await tts.save(out_path)

    asyncio.run(_run())
    return out_path


def _duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def _reference(host: dict) -> str:
    global _ref_wav
    if _ref_wav and os.path.exists(_ref_wav):
        return _ref_wav
    d = tempfile.mkdtemp(prefix="rico-ref-")
    mp3 = _edge(REF_LINE, os.path.join(d, "ref.mp3"), host)
    _ref_wav = os.path.join(d, "ref.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", mp3, "-ar", "24000", "-ac", "1", _ref_wav], check=True)
    return _ref_wav


def _chatterbox(text: str, out_path: str, host: dict) -> str | None:
    py = os.environ.get("CHATTERBOX_PYTHON")
    if not py or not os.path.exists(py):
        print("chatterbox env missing; using Edge voice")
        return None
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "cbx_tts.py")
    words = max(1, len(text.split()))
    expected = words / 2.6  # seconds, normal speaking pace
    for seed in (7, 21):
        wav = out_path + ".wav"
        try:
            subprocess.run([py, script, "--ref", _reference(host), "--out", wav, "--text", text,
                            "--exaggeration", str(host.get("chatterbox_exaggeration", 0.65)),
                            "--cfg", str(host.get("chatterbox_cfg", 0.4)), "--seed", str(seed)],
                           check=True, timeout=600,
                           env={**os.environ, "HF_HOME": os.environ.get("CHATTERBOX_HF_HOME", os.path.expanduser("~/.cache/cbx-hf"))})
            dur = _duration(wav)
        except Exception as e:  # noqa: BLE001
            print(f"chatterbox failed ({e}); using Edge voice")
            return None
        # The model sometimes cuts a line short or rambles; retry once, then fall back.
        if 0.55 * expected <= dur <= 2.2 * expected + 1.5:
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-b:a", "160k", out_path], check=True)
            os.remove(wav)
            return out_path
        print(f"chatterbox audio {dur:.1f}s for ~{expected:.1f}s of text (seed {seed}); retrying")
    print("chatterbox audio looked wrong twice; using Edge voice")
    return None


def speak(text: str, out_path: str, host: dict) -> str:
    engine = host.get("voice_engine", "edge")
    if engine == "elevenlabs" and os.environ.get("ELEVENLABS_API_KEY"):
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{host['elevenlabs_voice_id']}",
            headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "accept": "audio/mpeg"},
            json={"text": text, "model_id": "eleven_multilingual_v2"},
            timeout=120,
        )
        r.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(r.content)
        return out_path
    if engine == "chatterbox" and _chatterbox(text, out_path, host):
        return out_path
    return _edge(text, out_path, host)
