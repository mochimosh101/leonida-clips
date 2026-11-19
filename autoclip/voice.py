"""Rico Neon's voice: free Microsoft Edge TTS by default, ElevenLabs optional."""
import asyncio
import os

import requests


def speak(text: str, out_path: str, host: dict) -> str:
    if host.get("voice_engine") == "elevenlabs" and os.environ.get("ELEVENLABS_API_KEY"):
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

    import edge_tts

    async def _run():
        tts = edge_tts.Communicate(text, host["edge_voice"], rate=host["edge_rate"], pitch=host["edge_pitch"])
        await tts.save(out_path)

    asyncio.run(_run())
    return out_path
