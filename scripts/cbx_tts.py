"""Speak one line with Chatterbox (free, open-source, runs on CPU). Called by autoclip/voice.py
from its own Python env, so its pinned packages don't clash with the bot's.

usage: cbx_tts.py --ref ref.wav --out out.wav --text "..." [--exaggeration 0.65] [--cfg 0.4] [--seed 7]
"""
import argparse

import torch
import torchaudio
from chatterbox.tts import ChatterboxTTS

ap = argparse.ArgumentParser()
ap.add_argument("--ref", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--text", required=True)
ap.add_argument("--exaggeration", type=float, default=0.65)
ap.add_argument("--cfg", type=float, default=0.4)
ap.add_argument("--seed", type=int, default=7)
a = ap.parse_args()

torch.manual_seed(a.seed)
m = ChatterboxTTS.from_pretrained(device="cpu")
wav = m.generate(a.text, audio_prompt_path=a.ref, exaggeration=a.exaggeration, cfg_weight=a.cfg)
torchaudio.save(a.out, wav, m.sr)
