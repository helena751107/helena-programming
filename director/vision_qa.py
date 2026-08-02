#!/usr/bin/env python3
"""
Vision QA — self-grading tutorial video against big-tech demo bar.

Compares shipped mp4 frames to a Claude/Screen-Studio-class checklist:
  V1 Intro visible (not pure black)
  V2 Step chip present (PRODUCT TOUR / n/N)
  V3 Caption bar present (STEP …)
  V4 Gold focus ring / spotlight accents
  V5 Teal chrome (progress / chip / outline)
  V6 Not stuck mid-wrong-section (beat vs content heuristic)
  V7 Mean luminance band (readable dark UI, not void)
  V8 Click proof density (from actions_log visual_proof)

Outputs vision_qa.json + vision_qa.md with score /100 and fail reasons.
Exit 0 if score >= pass_score (default 85), else 2.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from quality import accent_counts, extract_frame, ffprobe_duration, png_stats


# Big-tech tutorial rubric (weights sum 100)
RUBRIC = [
    {"id": "V1_intro_not_black", "w": 15, "desc": "t≈0.3–2.5s not pure black"},
    {"id": "V2_chip", "w": 12, "desc": "PRODUCT TOUR / step chip visible mid-tour"},
    {"id": "V3_caption", "w": 12, "desc": "STEP caption bar bottom visible"},
    {"id": "V4_gold_ring", "w": 18, "desc": "gold focus ring on ≥40% body samples"},
    {"id": "V5_teal_chrome", "w": 12, "desc": "teal accents (chip/progress) mid samples"},
    {"id": "V6_readable", "w": 12, "desc": "mean_y in [10, 80] on body samples"},
    {"id": "V7_proof_clicks", "w": 12, "desc": "actions visual_proof pass rate ≥70%"},
    {"id": "V8_no_void_span", "w": 7, "desc": "no ≥1.5s pure-black after t=1s"},
]


def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return (r.stdout or "") + (r.stderr or "")


def _blackdetect_all(video: Path) -> list[tuple[float, float, float]]:
    out = _run([
        "ffmpeg", "-i", str(video),
        "-vf", "blackdetect=d=0.4:pix_th=0.08",
        "-an", "-f", "null", "-",
    ])
    import re
    spans = []
    for m in re.finditer(
        r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)",
        out,
    ):
        spans.append(tuple(map(float, m.groups())))
    return spans


def sample_timeline(dur: float) -> list[float]:
    """Key sample times: early body, quarters, late."""
    if dur < 8:
        return [min(1.0, dur * 0.2), dur * 0.5, max(0.5, dur - 1)]
    pts = [
        0.4, 1.2, 2.0,  # intro / first paint
        max(3.0, dur * 0.12),
        max(5.0, dur * 0.25),
        max(8.0, dur * 0.40),
        max(10.0, dur * 0.55),
        max(12.0, dur * 0.70),
        max(14.0, min(dur - 1.5, dur * 0.85)),
    ]
    return [min(t, max(0.1, dur - 0.2)) for t in pts]


def grade_frame(path: Path) -> dict:
    st = png_stats(path)
    ac = accent_counts(path)
    mean = st.get("mean_y")
    black = st.get("black_ratio")
    gold = ac.get("gold", 0)
    teal = ac.get("teal", 0)
    # region heuristics via full accent counts
    chip_like = teal >= 25  # progress + chip
    ring_like = gold >= 60
    caption_like = teal >= 15 and mean is not None and mean > 8
    void = (mean is not None and mean < 4) or (black is not None and black > 0.97)
    return {
        "mean_y": mean,
        "black_ratio": black,
        "gold": gold,
        "teal": teal,
        "chip_like": chip_like,
        "ring_like": ring_like,
        "caption_like": caption_like,
        "void": void,
        "size": st.get("size"),
    }


def vision_qa(
    video: Path,
    *,
    work: Path,
    actions_log: dict | None = None,
    pass_score: int = 85,
) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    frames_dir = work / "vqa_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    if not video.exists() or video.stat().st_size < 40_000:
        report = {
            "pass": False, "score": 0, "max": 100,
            "errors": ["video missing/small"], "checks": [],
        }
        (work / "vision_qa.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report

    dur = ffprobe_duration(video)
    times = sample_timeline(dur)
    samples = []
    for i, t in enumerate(times):
        fp = frames_dir / f"vqa_{i:02d}_t{t:.1f}.png"
        try:
            extract_frame(video, t, fp)
            g = grade_frame(fp)
            g["t"] = round(t, 2)
            g["file"] = fp.name
            samples.append(g)
        except Exception as e:
            samples.append({"t": t, "error": str(e), "void": True, "gold": 0, "teal": 0})

    body = [s for s in samples if s.get("t", 0) >= 2.5 and not s.get("error")]
    early = [s for s in samples if s.get("t", 0) < 2.5]

    checks = []
    score = 0
    errors = []

    # V1 intro not black — majority of early samples must have content
    w = 15
    early_good = [
        s for s in early
        if not s.get("void")
        and (s.get("mean_y") or 0) > 6
        and (s.get("size") or 0) > 15_000
        and (s.get("black_ratio") is None or s.get("black_ratio", 1) < 0.96)
    ]
    # hard fail if ANY sample in 1.5–3.0s is pure void (post-intro black hole)
    mid_early_void = [
        s for s in samples
        if 1.5 <= (s.get("t") or 0) <= 3.2 and s.get("void")
    ]
    early_ok = len(early_good) >= max(1, (len(early) + 1) // 2) and not mid_early_void
    got = w if early_ok else (w // 2 if early_good else 0)
    score += got
    checks.append({
        "id": "V1_intro_not_black", "w": w, "got": got, "pass": early_ok,
        "detail": f"early_good={len(early_good)}/{len(early)} mid_void={len(mid_early_void)}",
    })
    if not early_ok:
        errors.append("V1: early frames pure black / empty intro (or black hole 1.5–3s)")

    # V2 chip (teal mid)
    w = 12
    chip_hits = sum(1 for s in body if s.get("chip_like") or (s.get("teal") or 0) >= 20)
    chip_ok = chip_hits >= max(1, len(body) // 3)
    got = w if chip_ok else int(w * chip_hits / max(1, len(body)))
    score += got
    checks.append({"id": "V2_chip", "w": w, "got": got, "pass": chip_ok,
                   "detail": f"chip_hits={chip_hits}/{len(body)}"})
    if not chip_ok:
        errors.append("V2: PRODUCT TOUR chip / teal chrome missing mid-tour")

    # V3 caption (teal + not void on bottom-heavy frames — approximate via teal)
    w = 12
    cap_hits = sum(1 for s in body if s.get("caption_like") or (s.get("teal") or 0) >= 15)
    cap_ok = cap_hits >= max(1, len(body) // 3)
    got = w if cap_ok else int(w * cap_hits / max(1, len(body)))
    score += got
    checks.append({"id": "V3_caption", "w": w, "got": got, "pass": cap_ok,
                   "detail": f"cap_hits={cap_hits}/{len(body)}"})
    if not cap_ok:
        errors.append("V3: STEP caption bar weak/missing")

    # V4 gold ring
    w = 18
    ring_hits = sum(1 for s in body if s.get("ring_like") or (s.get("gold") or 0) >= 60)
    need = max(2, int(len(body) * 0.4))
    ring_ok = ring_hits >= need
    got = w if ring_ok else int(w * ring_hits / max(1, need))
    score += got
    checks.append({"id": "V4_gold_ring", "w": w, "got": got, "pass": ring_ok,
                   "detail": f"ring_hits={ring_hits}/{len(body)} need≥{need}"})
    if not ring_ok:
        errors.append("V4: gold focus ring not visible enough (Screen Studio bar)")

    # V5 teal chrome
    w = 12
    teal_hits = sum(1 for s in body if (s.get("teal") or 0) >= 15)
    teal_ok = teal_hits >= max(2, len(body) // 3)
    got = w if teal_ok else int(w * teal_hits / max(1, len(body)))
    score += got
    checks.append({"id": "V5_teal_chrome", "w": w, "got": got, "pass": teal_ok,
                   "detail": f"teal_hits={teal_hits}/{len(body)}"})
    if not teal_ok:
        errors.append("V5: teal progress/chip accents sparse")

    # V6 readable luminance
    w = 12
    readable = [
        s for s in body
        if s.get("mean_y") is not None and 8 <= s["mean_y"] <= 90
    ]
    read_ok = len(readable) >= max(2, len(body) // 2)
    got = w if read_ok else int(w * len(readable) / max(1, len(body)))
    score += got
    checks.append({"id": "V6_readable", "w": w, "got": got, "pass": read_ok,
                   "detail": f"readable={len(readable)}/{len(body)}"})
    if not read_ok:
        errors.append("V6: body frames too dark/bright to read UI")

    # V7 proof clicks
    w = 12
    proof_ok = False
    proof_detail = "no actions_log"
    if actions_log:
        proofs = actions_log.get("visual_proof") or []
        if proofs:
            p_pass = sum(1 for p in proofs if p.get("pass"))
            rate = p_pass / len(proofs)
            proof_ok = rate >= 0.70 and p_pass >= 4
            proof_detail = f"pass={p_pass}/{len(proofs)} rate={rate:.0%}"
        elif actions_log.get("visual_proof_pass"):
            proof_ok = True
            proof_detail = "visual_proof_pass flag"
        else:
            # fallback: successful clicks only — partial credit
            sc = actions_log.get("successful_clicks") or 0
            proof_ok = sc >= 4
            proof_detail = f"clicks_only={sc} (no proof frames)"
            if proof_ok:
                got = w // 2
                score += got
                checks.append({"id": "V7_proof_clicks", "w": w, "got": got, "pass": False,
                               "detail": proof_detail + " partial"})
                errors.append("V7: no visual_proof frames — clicks-only partial")
                proof_ok = None  # mark handled
    if proof_ok is not None:
        got = w if proof_ok else 0
        score += got
        checks.append({"id": "V7_proof_clicks", "w": w, "got": got, "pass": bool(proof_ok),
                       "detail": proof_detail})
        if not proof_ok:
            errors.append(f"V7: visual proof weak ({proof_detail})")

    # V8 no void span mid-video
    w = 7
    spans = _blackdetect_all(video)
    bad_spans = [s for s in spans if s[0] >= 1.0 and s[2] >= 1.5]
    void_ok = len(bad_spans) == 0
    got = w if void_ok else 0
    score += got
    checks.append({"id": "V8_no_void_span", "w": w, "got": got, "pass": void_ok,
                   "detail": f"bad_spans={bad_spans[:3]}"})
    if not void_ok:
        errors.append(f"V8: black void mid-video {bad_spans[:2]}")

    score = min(100, int(score))
    passed = score >= pass_score and not any(
        c["id"] in ("V1_intro_not_black", "V4_gold_ring") and not c["pass"]
        for c in checks
    )
    # hard fail on V1
    if any(c["id"] == "V1_intro_not_black" and not c["pass"] for c in checks):
        passed = False

    report = {
        "pass": passed,
        "score": score,
        "pass_score": pass_score,
        "max": 100,
        "grade": (
            "S" if score >= 95 else
            "A" if score >= 85 else
            "B" if score >= 70 else
            "C" if score >= 55 else "F"
        ),
        "duration": dur,
        "samples": samples,
        "checks": checks,
        "errors": errors,
        "rubric": "bigtech_tutorial_vision_v1",
        "compare_to": [
            "Screen Studio: cursor path + click ripple always readable",
            "Arcade/Storylane: one spotlight focus per step",
            "Playwright Generator: verified role clicks, no dead nav",
            "Claude Code demos: step caption sync with visible section",
        ],
    }

    (work / "vision_qa.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = [
        f"# Vision QA — score {score}/100 · grade {report['grade']} · "
        f"{'PASS' if passed else 'FAIL'}",
        "",
        f"- video: `{video}`",
        f"- duration: {dur:.1f}s",
        f"- pass_score: {pass_score}",
        "",
        "## Checks",
        "",
        "| id | got/w | pass | detail |",
        "|----|-------|------|--------|",
    ]
    for c in checks:
        md.append(
            f"| {c['id']} | {c['got']}/{c['w']} | "
            f"{'✓' if c['pass'] else '✗'} | `{c.get('detail','')[:80]}` |"
        )
    if errors:
        md += ["", "## Errors", ""]
        for e in errors:
            md.append(f"- {e}")
    md += [
        "",
        "## Compare bar",
        "",
    ]
    for line in report["compare_to"]:
        md.append(f"- {line}")
    (work / "vision_qa.md").write_text("\n".join(md), encoding="utf-8")

    print(f"[vision_qa] score={score}/100 grade={report['grade']} PASS={passed}", flush=True)
    for c in checks:
        mark = "✓" if c["pass"] else "✗"
        print(f"  {mark} {c['id']}: {c['got']}/{c['w']} {c.get('detail','')[:60]}", flush=True)
    for e in errors:
        print(f"  ! {e}", flush=True)
    return report


def main():
    ap = argparse.ArgumentParser(description="Vision QA for Director tutorials")
    ap.add_argument("video", type=Path)
    ap.add_argument("--work", type=Path, default=None)
    ap.add_argument("--actions", type=Path, default=None)
    ap.add_argument("--pass-score", type=int, default=85)
    args = ap.parse_args()
    work = args.work or (args.video.parent / "vqa_work")
    actions = None
    if args.actions and args.actions.exists():
        actions = json.loads(args.actions.read_text(encoding="utf-8"))
    # also try sibling .actions.json
    sib = args.video.with_suffix(".actions.json")
    if actions is None and sib.exists():
        actions = json.loads(sib.read_text(encoding="utf-8"))
    report = vision_qa(args.video, work=work, actions_log=actions, pass_score=args.pass_score)
    raise SystemExit(0 if report.get("pass") else 2)


if __name__ == "__main__":
    main()
