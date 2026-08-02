#!/usr/bin/env python3
"""
Voice engine — community A-bar (Purple Owl / playwright-recast style).

Priority:
  1) OpenAI tts-1-hd  if OPENAI_API_KEY set
  2) edge-tts + broadcast humanize (always free fallback)

Also: multi-click pad, loudnorm chain.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

VOICE_DEFAULT = "ko-KR-SunHiNeural"
OPENAI_VOICE_DEFAULT = "nova"  # multilingual OK for short KO lines


def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip() or "0")


def humanize_tts(src: Path, dest: Path) -> None:
    """Broadcast chain — edge-tts 기계음 완화."""
    af = (
        "highpass=f=90,"
        "equalizer=f=2800:t=q:w=1.1:g=2.4,"
        "equalizer=f=6500:t=q:w=1.0:g=1.6,"
        "acompressor=threshold=-20dB:ratio=3.5:attack=5:release=70:makeup=2.2,"
        "loudnorm=I=-16:TP=-1.5:LRA=11"
    )
    r = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(src), "-af", af,
            "-ar", "24000", "-ac", "1",
            "-c:a", "libmp3lame", "-q:a", "3", str(dest),
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 200:
        shutil.copy(src, dest)


async def tts_edge(text: str, voice: str, dest: Path, retries: int = 4) -> float:
    import edge_tts

    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if dest.exists():
                dest.unlink()
            # rate slightly slower = more natural product-demo cadence
            communicate = edge_tts.Communicate(text, voice, rate="-8%")
            await communicate.save(str(dest))
            if dest.stat().st_size < 100:
                raise RuntimeError(f"TTS empty: {dest}")
            return ffprobe_duration(dest)
        except Exception as e:
            last_err = e
            await asyncio.sleep(min(8, attempt * 2))
    raise RuntimeError(f"edge-tts failed: {last_err}")


def tts_openai(text: str, dest: Path, voice: str | None = None) -> float:
    """OpenAI Audio Speech API — A-bar voice when key present."""
    import urllib.request
    import json

    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_KEY")
    if not key:
        raise RuntimeError("no OPENAI_API_KEY")
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "model": os.environ.get("OPENAI_TTS_MODEL", "tts-1-hd"),
        "voice": voice or os.environ.get("OPENAI_TTS_VOICE", OPENAI_VOICE_DEFAULT),
        "input": text,
        "response_format": "mp3",
        "speed": float(os.environ.get("OPENAI_TTS_SPEED", "0.95")),
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        dest.write_bytes(resp.read())
    if dest.stat().st_size < 200:
        raise RuntimeError("openai tts empty")
    return ffprobe_duration(dest)


async def synthesize_beat(
    text: str,
    *,
    dest: Path,
    raw_dest: Path,
    edge_voice: str = VOICE_DEFAULT,
    prefer: str = "auto",
) -> tuple[float, str]:
    """
    Returns (duration_sec, provider_id).
    prefer: auto | edge | openai
    """
    provider = "edge"
    use_openai = prefer == "openai" or (
        prefer == "auto" and bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_KEY"))
    )
    if use_openai:
        try:
            dur = await asyncio.to_thread(tts_openai, text, raw_dest)
            provider = "openai-tts-1-hd"
            humanize_tts(raw_dest, dest)  # light polish still helps
            return ffprobe_duration(dest), provider
        except Exception as e:
            print(f"  ! openai tts fallback to edge: {e}", flush=True)

    dur = await tts_edge(text, edge_voice, raw_dest)
    humanize_tts(raw_dest, dest)
    return ffprobe_duration(dest), "edge+humanize"


def multi_click_pad(n_clicks: int, base_hold_ms: int = 400) -> float:
    """Airtime so act never drops 2nd click — pro: breath room without 2× overshoot."""
    pad = base_hold_ms / 1000.0
    if n_clicks >= 2:
        return max(pad, 0.55 + (n_clicks - 1) * 1.35)
    if n_clicks == 1:
        return max(pad, 0.65)
    return max(pad, 0.4)
