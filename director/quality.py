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


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def png_decode_rgb(path: Path) -> tuple[int, int, bytes] | None:
    """Decode PNG → (w, h, rgb_bytes) with filter types 0–4. RGB/RGBA 8-bit only."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    ihdr = data.find(b"IHDR")
    if ihdr < 0:
        return None
    w, h = struct.unpack(">II", data[ihdr + 4: ihdr + 12])
    bit_depth = data[ihdr + 12]
    color_type = data[ihdr + 13]
    if bit_depth != 8 or color_type not in (2, 6):
        return None
    idats = []
    pos = 8
    while pos < len(data):
        if pos + 8 > len(data):
            break
        length = struct.unpack(">I", data[pos: pos + 4])[0]
        ctype = data[pos + 4: pos + 8]
        chunk = data[pos + 8: pos + 8 + length]
        pos = pos + 12 + length
        if ctype == b"IDAT":
            idats.append(chunk)
        if ctype == b"IEND":
            break
    try:
        raw = zlib.decompress(b"".join(idats))
    except Exception:
        return None
    bpp = 3 if color_type == 2 else 4
    stride = w * bpp
    out = bytearray(h * stride)
    prev = bytearray(stride)
    i = 0
    for y in range(h):
        if i >= len(raw):
            return None
        f = raw[i]
        i += 1
        row = bytearray(raw[i: i + stride])
        i += stride
        if f == 1:
            for x in range(bpp, stride):
                row[x] = (row[x] + row[x - bpp]) & 255
        elif f == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                left = row[x - bpp] if x >= bpp else 0
                row[x] = (row[x] + ((left + prev[x]) // 2)) & 255
        elif f == 4:
            for x in range(stride):
                left = row[x - bpp] if x >= bpp else 0
                up = prev[x]
                ul = prev[x - bpp] if x >= bpp else 0
                row[x] = (row[x] + _paeth(left, up, ul)) & 255
        elif f != 0:
            return None
        out[y * stride: (y + 1) * stride] = row
        prev = row
    if bpp == 4:
        rgb = bytearray(h * w * 3)
        for p in range(w * h):
            rgb[p * 3: p * 3 + 3] = out[p * 4: p * 4 + 3]
        return w, h, bytes(rgb)
    return w, h, bytes(out)


def accent_counts(path: Path) -> dict:
    """Gold / teal overlay accent pixel counts (unfiltered PNG)."""
    decoded = png_decode_rgb(path)
    if not decoded:
        return {"gold": 0, "teal": 0, "ok": False}
    w, h, rgb = decoded
    gold = teal = 0
    n = w * h
    step = max(1, n // 120_000)
    for p in range(0, n, step):
        i = p * 3
        r, g, b = rgb[i], rgb[i + 1], rgb[i + 2]
        if r > 175 and 120 < g < 245 and b < 160 and r > b + 35 and r + g > 320:
            gold += 1
        if 15 < r < 140 and 130 < g < 245 and 110 < b < 230 and g > r + 30 and g > b - 10:
            teal += 1
    return {"gold": gold, "teal": teal, "ok": True, "w": w, "h": h}


def png_stats(path: Path) -> dict:
    """Mean luminance via properly unfiltered PNG (no PIL)."""
    decoded = png_decode_rgb(path)
    if not decoded:
        sz = path.stat().st_size if path.exists() else 0
        return {
            "ok": True, "size": sz,
            "mean_y": None, "black_ratio": None,
            "heuristic": "complex_png", "complex": sz > 25_000,
        }
    w, h, rgb = decoded
    total = black = n = 0
    step = max(1, (w * h) // 80_000)
    for p in range(0, w * h, step):
        i = p * 3
        r, g, b = rgb[i], rgb[i + 1], rgb[i + 2]
        yv = (r * 3 + g * 6 + b) // 10
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
    # intro/card may be dark UI; require meaningful file size + not pure empty
    first_ok = st0.get("size", 0) >= 80_000 or bool(st0.get("complex"))
    if st0.get("mean_y") is not None and st0["mean_y"] < 3 and st0.get("size", 0) < 20_000:
        first_ok = False
    c = {
        "id": "G2_lead_black",
        "pass": first_ok and lead_black < 0.4,
        "detail": f"lead_black={lead_black:.2f}s frame0={st0}",
    }
    checks.append(c)
    ok = ok and c["pass"]

    # mid frame has UI
    fmid = work / "gate_mid.png"
    extract_frame(video, min(dur * 0.4, max(3.0, dur - 2)), fmid)
    stm = png_stats(fmid)
    mid_ok = stm.get("size", 0) > 40_000 or bool(stm.get("complex"))
    # reject near-black mid frames even if "complex" PNG size
    if stm.get("mean_y") is not None and stm["mean_y"] < 8 and (stm.get("black_ratio") or 0) > 0.95:
        mid_ok = False
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

    # G7 — sample multiple body frames for gold/teal overlay accents
    # (pro v3: spotlight ring + chip must appear in the shipped video)
    accent_hits = 0
    accent_detail = []
    sample_ts = [
        max(2.0, dur * 0.12),
        max(3.0, dur * 0.28),
        max(4.0, dur * 0.45),
        max(5.0, dur * 0.62),
        max(6.0, min(dur - 1.5, dur * 0.78)),
    ]
    for i, t in enumerate(sample_ts):
        fp = work / f"gate_accent_{i}.png"
        try:
            extract_frame(video, t, fp)
            st = png_stats(fp)
            ac = accent_counts(fp)
            gold, teal = ac.get("gold", 0), ac.get("teal", 0)
            hit = gold >= 40 and teal >= 10
            if hit:
                accent_hits += 1
            accent_detail.append({
                "t": round(t, 1), "gold": gold, "teal": teal, "hit": hit,
                "mean_y": st.get("mean_y"),
            })
        except Exception as e:
            accent_detail.append({"t": t, "error": str(e), "hit": False})
    # need at least 2 of 5 sampled frames showing overlay accents
    g7_ok = accent_hits >= 2
    c = {
        "id": "G7_overlay_accents",
        "pass": g7_ok,
        "detail": f"hits={accent_hits}/5 samples={accent_detail}",
    }
    checks.append(c)
    ok = ok and c["pass"]

    report = {"pass": ok, "duration": dur, "checks": checks, "accent_hits": accent_hits}
    (work / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[quality] PASS={ok}", flush=True)
    for ch in checks:
        mark = "✓" if ch["pass"] else "✗"
        print(f"  {mark} {ch['id']}: {ch['detail']}", flush=True)
    return report
