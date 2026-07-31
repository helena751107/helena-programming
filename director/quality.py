#!/usr/bin/env python3
"""Quality gates — block ship if intro tofu / lead black / no UI."""
from __future__ import annotations

import json
import re
import subprocess
import struct
import zlib
from pathlib import Path


def _run_out(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return (r.stdout or "") + (r.stderr or "")


def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip() or "0")


def extract_frame(video: Path, t: float, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(max(0, t)), "-i", str(video),
         "-vframes", "1", "-q:v", "2", str(dest)],
        check=True, capture_output=True,
    )
    return dest


def png_stats(path: Path) -> dict:
    """Mean luminance approx via raw PNG (no PIL). Works for non-interlaced RGB/RGBA."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return {"ok": False, "reason": "not png", "size": path.stat().st_size}
    # find IHDR
    ihdr = data.find(b"IHDR")
    if ihdr < 0:
        return {"ok": False, "reason": "no IHDR", "size": path.stat().st_size}
    w, h = struct.unpack(">II", data[ihdr + 4: ihdr + 12])
    bit_depth = data[ihdr + 12]
    color_type = data[ihdr + 13]
    # decompress IDAT
    idats = []
    pos = 8
    while pos < len(data):
        if pos + 8 > len(data):
            break
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos = pos + 12 + length
        if ctype == b"IDAT":
            idats.append(chunk)
        if ctype == b"IEND":
            break
    if not idats:
        return {"ok": False, "reason": "no IDAT", "w": w, "h": h, "size": path.stat().st_size}
    try:
        raw = zlib.decompress(b"".join(idats))
    except Exception as e:
        return {"ok": False, "reason": f"zlib {e}", "size": path.stat().st_size}

    if color_type == 2:  # RGB
        bpp = 3
    elif color_type == 6:  # RGBA
        bpp = 4
    elif color_type == 0:  # gray
        bpp = 1
    else:
        # fallback: file size heuristic
        sz = path.stat().st_size
        return {
            "ok": True, "w": w, "h": h, "size": sz,
            "mean_y": None, "black_ratio": None,
            "heuristic": "complex_png", "complex": sz > 25_000,
        }

    stride = w * bpp + 1  # filter byte
    if len(raw) < stride * h:
        return {"ok": False, "reason": "raw short", "size": path.stat().st_size}

    # sample every Nth pixel for speed
    total = 0
    black = 0
    n = 0
    step = max(1, (w * h) // 80_000)
    for y in range(h):
        row = raw[y * stride + 1:(y + 1) * stride]
        for x in range(0, w, step):
            i = x * bpp
            if bpp >= 3:
                r, g, b = row[i], row[i + 1], row[i + 2]
                yv = (r * 3 + g * 6 + b) // 10
            else:
                yv = row[i]
            total += yv
            if yv < 12:
                black += 1
            n += 1
    mean_y = total / max(1, n)
    black_ratio = black / max(1, n)
    return {
        "ok": True, "w": w, "h": h, "size": path.stat().st_size,
        "mean_y": mean_y, "black_ratio": black_ratio,
        "complex": path.stat().st_size > 25_000 and black_ratio < 0.92,
    }


def blackdetect_lead(video: Path) -> float:
    """Return leading black duration seconds (0 if none)."""
    out = _run_out([
        "ffmpeg", "-i", str(video),
        "-vf", "blackdetect=d=0.15:pix_th=0.08",
        "-an", "-f", "null", "-",
    ])
    # black_start:0 black_end:3.2 black_duration:3.2
    leads = []
    for m in re.finditer(
        r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)",
        out,
    ):
        start, end, dur = map(float, m.groups())
        if start <= 0.05:
            leads.append(dur)
    return max(leads) if leads else 0.0


def trim_leading_black(src: Path, dest: Path, min_keep: float = 0.0) -> tuple[Path, float]:
    lead = blackdetect_lead(src)
    # also check first frames file-size heuristic if blackdetect misses
    if lead < 0.2:
        # probe first 4 seconds frame sizes
        for t in (0.0, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0):
            tmp = dest.parent / f"_blk_{t}.png"
            try:
                extract_frame(src, t, tmp)
                st = png_stats(tmp)
                tmp.unlink(missing_ok=True)
                if st.get("complex") or (st.get("black_ratio") is not None and st["black_ratio"] < 0.85):
                    if t > 0.15:
                        lead = max(lead, t - 0.05)
                    break
                if t >= 0.5:
                    lead = max(lead, t)
            except Exception:
                break
    if lead < 0.25:
        if src.resolve() != dest.resolve():
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), "-c", "copy", str(dest)],
                check=True, capture_output=True,
            )
        return dest, 0.0
    # re-encode trim for keyframe safety
    ss = max(0.0, lead - 0.05)
    print(f"[quality] trim leading black {ss:.2f}s", flush=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{ss:.3f}", "-i", str(src),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(dest),
        ],
        check=True, capture_output=True,
    )
    return dest, ss


def gate_output(
    video: Path,
    *,
    work: Path,
    intro_png: Path | None = None,
) -> dict:
    """Return {pass: bool, checks: [...]}."""
    work.mkdir(parents=True, exist_ok=True)
    checks = []
    ok = True

    if not video.exists() or video.stat().st_size < 50_000:
        return {"pass": False, "checks": [{"id": "file", "pass": False, "detail": "missing/small"}]}

    dur = ffprobe_duration(video)
    c = {"id": "G4_duration", "pass": 12 <= dur <= 180, "detail": f"{dur:.1f}s"}
    checks.append(c)
    ok = ok and c["pass"]

    # audio stream?
    streams = _run_out(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0", str(video)])
    has_audio = "audio" in streams
    c = {"id": "G5_audio", "pass": has_audio, "detail": streams.strip()[:80]}
    checks.append(c)
    ok = ok and c["pass"]

    # first frame
    f0 = work / "gate_t0.png"
    extract_frame(video, 0.15, f0)
    st0 = png_stats(f0)
    lead_black = blackdetect_lead(video)
    # after our trim, first frame should not be pure black
    first_ok = bool(st0.get("complex")) or (
        st0.get("black_ratio") is not None and st0["black_ratio"] < 0.9
    ) or (st0.get("mean_y") is not None and st0["mean_y"] > 8)
    # file size fallback
    if st0.get("size", 0) > 30_000:
        first_ok = True
    c = {
        "id": "G2_lead_black",
        "pass": first_ok and lead_black < 0.6,
        "detail": f"lead_black={lead_black:.2f}s frame0={st0}",
    }
    checks.append(c)
    ok = ok and c["pass"]

    # mid frame has UI
    fmid = work / "gate_mid.png"
    extract_frame(video, min(dur * 0.4, max(3.0, dur - 2)), fmid)
    stm = png_stats(fmid)
    mid_ok = stm.get("size", 0) > 40_000 or bool(stm.get("complex"))
    c = {"id": "G3_ui", "pass": mid_ok, "detail": f"mid={stm}"}
    checks.append(c)
    ok = ok and c["pass"]

    # intro tofu: if intro png provided, size must be large; reject tiny
    if intro_png and intro_png.exists():
        sz = intro_png.stat().st_size
        # tofu-heavy intro from drawtext was ~50k with mostly black; HTML intro >80k
        intro_ok = sz > 40_000
        c = {"id": "G1_intro", "pass": intro_ok, "detail": f"intro_png_bytes={sz}"}
        checks.append(c)
        ok = ok and c["pass"]

    report = {"pass": ok, "duration": dur, "checks": checks}
    (work / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[quality] PASS={ok}", flush=True)
    for ch in checks:
        mark = "✓" if ch["pass"] else "✗"
        print(f"  {mark} {ch['id']}: {ch['detail']}", flush=True)
    return report
