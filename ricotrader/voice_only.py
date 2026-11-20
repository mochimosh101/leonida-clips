"""Write just the host's voice track for an episode (to feed a talking-head tool like Hedra).

  python -m ricotrader.voice_only episode.json out.mp3
"""
import json
import subprocess
import sys
import tempfile

from ricotrader.render import build_audio

if __name__ == "__main__":
    ep = json.load(open(sys.argv[1]))
    wav, _, _, _ = build_audio(ep["scenes"], ep.get("voice", "en-US-AvaMultilingualNeural"), tempfile.mkdtemp())
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-b:a", "192k", sys.argv[2]], check=True)
    print("wrote", sys.argv[2])
