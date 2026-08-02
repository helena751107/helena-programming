#!/usr/bin/env python3
"""SRT generation + optional ffmpeg burn-in (community A-bar)."""
from __future__ import annotations

from pathlib import Path


def _ts(sec: float) -> str:
    if sec < 0:
        sec = 0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        s += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt_from_beats(
    beats: list[dict],
    dest: Path,
    *,
    intro_sec: float = 2.0,
) -> Path:
    """
    One subtitle cue per beat, timed to audio_sec + pad after intro.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    t = float(intro_sec)
    lines: list[str] = []
    idx = 1
    for b in beats:
        text = (b.get("narration") or b.get("caption") or b.get("id") or "").strip()
        dur = float(b.get("audio_sec") or 0) + float(b.get("pad_sec") or 0.3)
        if dur < 0.4:
            dur = 0.4
        start, end = t, t + dur
        # soft cue ends 80ms early so next doesn't collide
        end_show = max(start + 0.3, end - 0.05)
        lines.append(str(idx))
        lines.append(f"{_ts(start)} --> {_ts(end_show)}")
        # keep single visual line
        if len(text) > 42:
            mid = text[:42].rfind(" ")
            if mid < 12:
                mid = 42
            text = text[:mid].strip() + "\n" + text[mid:].strip()
        lines.append(text)
        lines.append("")
        t = end
        idx += 1
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def burn_subtitles(
    video_in: Path,
    srt: Path,
    video_out: Path,
    *,
    x264: list[str],
) -> Path:
    """Burn SRT into video via ffmpeg subtitles filter."""
    import subprocess

    # escape path for subtitles filter
    srt_esc = str(srt.resolve()).replace("\\", "/").replace(":", "\\:")
    # force style readable on dark product UI
    style = (
        "FontName=Noto Sans CJK KR,FontSize=16,PrimaryColour=&H00E6F4F4,"
        "OutlineColour=&H80000000,BorderStyle=3,Outline=1,Shadow=0,"
        "MarginV=72,Alignment=2"
    )
    vf = f"subtitles='{srt_esc}':force_style='{style}'"
    cmd = [
        "ffmpeg", "-y", "-i", str(video_in),
        "-vf", vf,
        *x264, "-c:a", "copy",
        "-movflags", "+faststart",
        str(video_out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not video_out.exists():
        # fallback: copy without burn
        import shutil
        shutil.copy(video_in, video_out)
        print(f"  ! subtitle burn failed, copied plain: {r.stderr[-400:]}", flush=True)
    return video_out
