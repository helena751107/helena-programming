#!/usr/bin/env python3
"""
Perfect Ship — 만점 강제 프로세스 (코드화된 사다리).

에이전트가 세션마다 품질을 '알아서' 올리지 못하게 한다.
유일한 경로:

  python3 perfect_ship.py --url URL --out out/demo.mp4
  python3 perfect_ship.py --scenario scenarios/helena_phone.json --out out/helena_phone.mp4

1) process/perfect_ship_v1.json 사다리 로드
2) run_director 전체 파이프 (policy+directing 강제)
3) 산출물 재검증 (actions / quality / vision_qa / declared clicks)
4) process_report.json 기록 — SHIP 또는 FAIL+remediation

exit: 0 SHIP · 2 quality · 3 pre_shoot · 4 post_shoot · 5 vision · 6 process
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DIR = Path(__file__).resolve().parent
PROCESS_DIR = DIR / "process"
DEFAULT_PROCESS = "perfect_ship_v1"


def load_process(process_id: str = DEFAULT_PROCESS) -> dict:
    path = PROCESS_DIR / f"{process_id}.json"
    if not path.exists():
        raise SystemExit(f"process missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("id") != process_id:
        raise SystemExit(f"process id mismatch in {path}")
    return data


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def verify_artifacts(
    *,
    process: dict,
    work: Path,
    out: Path,
    scenario: dict | None,
    policy: dict | None,
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    """
    Deterministic ladder verification against on-disk artifacts.
    Returns (pass, stage_results, remediation_ids).
    """
    req = (policy or {}).get("require") or {}
    actions = _read_json(work / "actions_log.json") or {}
    quality = _read_json(work / "gate" / "quality_report.json")
    if quality is None and out.with_suffix(".quality.json").exists():
        quality = _read_json(out.with_suffix(".quality.json"))
    vqa = _read_json(work / "vision_qa" / "vision_qa.json")
    if vqa is None:
        vqa = _read_json(out.with_suffix(".vision_qa.json"))
    scout = _read_json(work / "scout.json")
    directing = _read_json(work / "directing.json")
    scn = scenario or _read_json(work / "scenario.json") or {}

    stages: list[dict[str, Any]] = []
    rem: list[str] = []
    vqa_need = int(req.get("vision_qa_pass_score") or 100)

    def add(sid: str, name: str, ok: bool, detail: str, ap: str | None = None):
        stages.append({"id": sid, "name": name, "pass": ok, "detail": detail})
        if not ok and ap:
            rem.append(ap)

    # L0
    add(
        "L0_SCOUT", "Scout page",
        bool(scout) and (scout.get("interactive_count") is not None or scout.get("sections")),
        f"scout={bool(scout)} interactives={scout.get('interactive_count') if scout else None}",
    )
    # L1
    want_dir = req.get("directing_id") or "product_tour_v1"
    want_pol = (policy or {}).get("id") or "tutorial_v1"
    ok_dir = (scn.get("directing") == want_dir) and bool(directing)
    ok_pol = scn.get("policy") == want_pol
    add(
        "L1_DIRECTING", "Directing + policy stamp",
        ok_dir and ok_pol,
        f"directing={scn.get('directing')} policy={scn.get('policy')}",
        "AP5_llm_freeform" if not (ok_dir and ok_pol) else None,
    )
    # L2 — TTS-first + humanize (Purple Owl / recast)
    tts_ok = bool(actions.get("tts_humanize")) or any(
        (work / "voice").glob("*_raw.mp3")
    ) if (work / "voice").exists() else bool(actions.get("tts_humanize"))
    if actions.get("tts_humanize") is False:
        tts_ok = False
    elif actions.get("tts_humanize") is True:
        tts_ok = True
    tts_first = bool(actions.get("tts_first") or (scn or {}).get("tts_first"))
    add(
        "L2_VOICE", "TTS-first + humanize + multi pad",
        (tts_ok and (tts_first or not req.get("require_tts_first", True)))
        if req.get("require_tts_humanize", True) else True,
        f"tts_humanize={actions.get('tts_humanize')} tts_first={tts_first} "
        f"provider={actions.get('tts_provider')} "
        f"raw={any((work/'voice').glob('*_raw.mp3')) if (work/'voice').exists() else False}",
        "AP5_llm_freeform" if not tts_ok else None,
    )
    # L3
    need_phases = ["establish", "focus", "act", "hold", "release"]
    phases = actions.get("phases_played") or []
    phases_ok = bool(phases) and all(
        [p.get("id") for p in (e.get("phases") or [])] == need_phases for e in phases
    )
    ov = actions.get("overlay_version") or 0
    sh = actions.get("shoot_version") or 0
    cursor_ok = bool(actions.get("cursor_on_primary"))
    if req.get("require_cursor_on_primary", True) and not cursor_ok:
        rem.append("AP1_cursor_on_metrics")
    # declared vs done clicks
    declared = 0
    if scn:
        declared = sum(len(b.get("clicks") or []) for b in (scn.get("beats") or []))
    done = int(actions.get("successful_clicks") or 0)
    fails = actions.get("failed_clicks") or []
    required_fails = [f for f in fails if not f.get("optional", False)]
    all_clicks_ok = (done >= declared >= 1) and not required_fails
    if req.get("require_all_declared_clicks", True) and not all_clicks_ok:
        rem.append("AP3_drop_multiclick")
    zoom_ok = bool(actions.get("auto_zoom")) or bool(actions.get("zoom_events"))
    if req.get("require_auto_zoom", True) and not zoom_ok:
        rem.append("AP7_no_auto_zoom")
    l3_ok = (
        phases_ok
        and ov >= int(req.get("min_overlay_version") or 4)
        and sh >= int(req.get("min_shoot_version") or 5)
        and (cursor_ok or not req.get("require_cursor_on_primary", True))
        and (all_clicks_ok or not req.get("require_all_declared_clicks", True))
        and (zoom_ok or not req.get("require_auto_zoom", True))
    )
    add(
        "L3_SHOOT", "5-act + overlay v4 + cursor lock + auto-zoom + all clicks",
        l3_ok,
        f"phases={len(phases)} overlay={ov} shoot={sh} cursor={cursor_ok} "
        f"zoom={zoom_ok} clicks={done}/{declared} fails={len(required_fails)}",
        "AP1_cursor_on_metrics" if not cursor_ok else None,
    )
    # L4
    vp_ok = bool(actions.get("visual_proof_pass"))
    vp_n = int(actions.get("visual_proof_pass_count") or 0)
    vp_min = int(req.get("min_visual_proof_pass") or 4)
    if not vp_ok or vp_n < vp_min:
        rem.append("AP2_fake_ship_clicks")
    add(
        "L4_PROOF", "Visual proof",
        vp_ok and vp_n >= vp_min,
        f"pass={vp_ok} count={vp_n}>={vp_min}",
        "AP2_fake_ship_clicks" if not (vp_ok and vp_n >= vp_min) else None,
    )
    # L5
    out_ok = out.exists() and out.stat().st_size > 50_000
    add("L5_EDIT", "Output mp4 exists", out_ok, f"out={out} bytes={out.stat().st_size if out.exists() else 0}")
    # L6
    q_ok = bool(quality and quality.get("pass"))
    add(
        "L6_QUALITY", "Quality G1–G7",
        q_ok if req.get("quality_gate_must_pass", True) else True,
        f"quality.pass={quality.get('pass') if quality else None}",
    )
    # L7
    vqa_score = int((vqa or {}).get("score") or 0)
    vqa_pass = bool((vqa or {}).get("pass")) and vqa_score >= vqa_need
    # hard checks V1/V4
    hard_fail = False
    for c in (vqa or {}).get("checks") or []:
        if c.get("id") in ("V1_intro_not_black", "V4_gold_ring") and not c.get("pass"):
            hard_fail = True
    if hard_fail:
        vqa_pass = False
    add(
        "L7_VISION_QA", f"Vision QA ≥{vqa_need}",
        vqa_pass if req.get("vision_qa_required", True) else True,
        f"score={vqa_score} pass_flag={(vqa or {}).get('pass')} grade={(vqa or {}).get('grade')}",
        "AP6_metric_only_vqa" if not vqa_pass else None,
    )
    # L8 meta
    all_prior = all(s["pass"] for s in stages)
    add(
        "L8_PROCESS_VERIFY", "Ladder complete",
        all_prior,
        f"stages_pass={sum(1 for s in stages if s['pass'])}/{len(stages)}",
        "AP5_llm_freeform" if not all_prior else None,
    )
    # L9
    ship = all(s["pass"] for s in stages)
    stages.append({
        "id": "L9_SHIP",
        "name": "SHIP allowed",
        "pass": ship,
        "detail": "TG/deploy OK" if ship else "blocked — fix remediation",
    })

    # unique rem
    rem_u = []
    for r in rem:
        if r and r not in rem_u:
            rem_u.append(r)
    return ship, stages, rem_u


def write_report(
    path: Path,
    *,
    process: dict,
    ship: bool,
    stages: list[dict],
    rem: list[str],
    out: Path,
    work: Path,
) -> Path:
    rmap = process.get("remediation_map") or {}
    report = {
        "process_id": process.get("id"),
        "process_version": process.get("version"),
        "ship": ship,
        "out": str(out),
        "work": str(work),
        "stages": stages,
        "remediation_ids": rem,
        "remediation": [{ "id": rid, "fix": rmap.get(rid, "") } for rid in rem],
        "agent_rules": process.get("agent_rules") or [],
        "one_liner": process.get("one_liner"),
    }
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = path.with_suffix(".md")
    lines = [
        f"# Perfect Ship Report — {'SHIP' if ship else 'FAIL'}",
        "",
        f"- process: `{process.get('id')}` v{process.get('version')}",
        f"- out: `{out}`",
        "",
        "## Ladder",
        "",
        "| Stage | Pass | Detail |",
        "|-------|------|--------|",
    ]
    for s in stages:
        mark = "✓" if s.get("pass") else "✗"
        lines.append(f"| {s.get('id')} {s.get('name')} | {mark} | {s.get('detail')} |")
    if rem:
        lines += ["", "## Remediation (코드 고칠 곳 — 즉흥 금지)", ""]
        for rid in rem:
            lines.append(f"- **{rid}**: {rmap.get(rid, '')}")
    lines += ["", "## Agent rules", ""]
    for rule in process.get("agent_rules") or []:
        lines.append(f"- {rule}")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_director(args: argparse.Namespace, process_id: str) -> int:
    cmd = [
        sys.executable,
        str(DIR / "run_director.py"),
        "--process", process_id,
        "--policy", args.policy,
        "--out", str(args.out),
        "--format", getattr(args, "format", "shorts_1080"),
        "--tts", getattr(args, "tts", "auto"),
    ]
    if args.scenario:
        cmd += ["--scenario", str(args.scenario)]
    if args.url:
        cmd += ["--url", args.url]
    if args.work:
        cmd += ["--work", str(args.work)]
    if args.skip_intro:
        cmd.append("--skip-intro")
    if getattr(args, "subs", False):
        cmd.append("--subs")
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


def main() -> None:
    ap = argparse.ArgumentParser(description="Perfect Ship ladder — 만점 강제 프로세스")
    ap.add_argument("--process", default=DEFAULT_PROCESS, help="process id (default perfect_ship_v1)")
    ap.add_argument("--policy", default="tutorial_v1")
    ap.add_argument("--scenario", type=Path)
    ap.add_argument("--url", type=str)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work", type=Path, default=None)
    ap.add_argument("--skip-intro", action="store_true")
    ap.add_argument(
        "--format",
        default="shorts_1080",
        choices=["shorts", "shorts_1080", "desktop", "desktop_1080"],
        help="Output profile (default shorts_1080 A-bar)",
    )
    ap.add_argument("--subs", action="store_true", help="Burn subtitles")
    ap.add_argument("--tts", default="auto", choices=["auto", "edge", "openai"])
    ap.add_argument(
        "--verify-only",
        action="store_true",
        help="Do not render; only verify existing work/ + out",
    )
    args = ap.parse_args()

    process = load_process(args.process)
    print(f"=== Perfect Ship ({process['id']} v{process.get('version')}) ===", flush=True)
    print(process.get("one_liner", ""), flush=True)

    if not args.verify_only:
        if not args.scenario and not args.url:
            raise SystemExit("Need --url or --scenario")
        rc = run_director(args, process["id"])
        if rc != 0:
            # still try to write partial process report
            print(f"[perfect_ship] director exit={rc} — verifying partial artifacts", flush=True)

    # resolve work dir
    if args.work:
        work = args.work
    else:
        sid = args.scenario.stem if args.scenario else (args.url or "run").rstrip("/").split("/")[-1]
        work = DIR / "out" / f"work_{sid}"

    policy = None
    pol_path = work / "policy.json"
    if pol_path.exists():
        policy = _read_json(pol_path)
    else:
        from enforce import load_policy
        try:
            policy = load_policy(args.policy)
        except Exception:
            policy = {"id": args.policy, "require": {}}

    scenario = _read_json(work / "scenario.json")
    ship, stages, rem = verify_artifacts(
        process=process,
        work=work,
        out=args.out,
        scenario=scenario,
        policy=policy,
    )
    report_path = args.out.with_suffix(".process.json")
    write_report(
        report_path,
        process=process,
        ship=ship,
        stages=stages,
        rem=rem,
        out=args.out,
        work=work,
    )
    # also copy into work
    if work.exists():
        (work / "process_report.json").write_text(
            report_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    print("\n--- Perfect Ship Ladder ---", flush=True)
    for s in stages:
        mark = "✓" if s.get("pass") else "✗"
        print(f"  {mark} {s['id']}: {s.get('detail')}", flush=True)
    if rem:
        print("\nRemediation (fix in code, do not improvise):", flush=True)
        rmap = process.get("remediation_map") or {}
        for rid in rem:
            print(f"  • {rid}: {rmap.get(rid, '')}", flush=True)

    if ship:
        print(f"\n=== SHIP · PERFECT_SHIP PASS · {process['id']} ===", flush=True)
        print(f"report: {report_path}", flush=True)
        sys.exit(0)

    print(f"\n=== FAIL · PERFECT_SHIP · see {report_path} ===", flush=True)
    # if director already failed, preserve its code if non-zero from verify-only path
    sys.exit(6)


if __name__ == "__main__":
    main()
