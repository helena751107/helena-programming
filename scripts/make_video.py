#!/usr/bin/env python3
"""
make_video.py — 대화형 영상 제작기
실행하면 물어본다. CLI 기억할 필요 없음.
"""

import os, sys, asyncio, subprocess

sys.path.insert(0, os.path.dirname(__file__))
from webpage_to_video import (
    parse_markdown, parse_html, make_section_html,
    screenshot, tts, frame_to_clip, concat_clips
)
import tempfile


# ── 한글 음성 목록 ──
VOICES = [
    ("ko-KR-SunHiNeural",  "여성", "SunHi - 밝고 부드러운 목소리"),
    ("ko-KR-InJoonNeural", "남성", "InJoon - 차분한 남성 목소리"),
    ("ko-KR-HyunsuMultilingualNeural", "남성", "Hyunsu - 다국어 지원"),
]


def pick_voice():
    print("\n🎙️  TTS 음성을 선택하세요:")
    for i, (_, gender, desc) in enumerate(VOICES, 1):
        print(f"  {i}. [{gender}] {desc}")
    while True:
        try:
            v = input(f"  선택 (1-{len(VOICES)}, Enter=1): ").strip()
            if not v: return VOICES[0][0]
            idx = int(v) - 1
            if 0 <= idx < len(VOICES):
                return VOICES[idx][0]
        except: pass
        print("  1~3 중에 입력")


def pick_file():
    print("\n📄 변환할 파일 또는 URL:")
    while True:
        src = input("  경로/URL: ").strip()
        if not src:
            print("  입력해라")
            continue
        if src.startswith("http"):
            print(f"  ✅ URL: {src}")
            return src
        if os.path.exists(src):
            print(f"  ✅ 파일: {src}")
            return src
        print(f"  ❌ 없음: {src}")


def preview_sections(sections):
    print(f"\n📝 {len(sections)}개 섹션 감지:")
    for i, (title, body) in enumerate(sections, 1):
        print(f"  {i}. {title[:50]}")
        print(f"     {body[:80]}...")
    while True:
        ok = input("  진행할까요? (Enter=진행, q=취소): ").strip().lower()
        if ok in ('q','ㅂ'): sys.exit(0)
        if not ok: return


async def run():
    print("╔══════════════════════════════════╗")
    print("║  🎬 Helena Studio · 영상 제작   ║")
    print("╚══════════════════════════════════╝")

    # 1. 파일 선택
    src = pick_file()

    # 2. 읽기 + 파싱
    print("\n📖 읽는 중...")
    if src.startswith("http"):
        import urllib.request
        with urllib.request.urlopen(src) as r:
            text = r.read().decode("utf-8", errors="replace")
    else:
        text = open(src, encoding="utf-8").read()

    if src.endswith('.md') or not text.strip().startswith('<'):
        sections = parse_markdown(text)
    else:
        sections = parse_html(text)

    if not sections:
        print("❌ 섹션 추출 실패"); return

    sections = sections[:8]
    preview_sections(sections)

    # 3. 음성 선택
    voice = pick_voice()

    # 4. 속도
    print("\n⏱️  말하기 속도:")
    speeds = {"1":"-10%","2":"-5%","3":"+0%","4":"+5%","5":"+10%"}
    print("  1.느리게(-10%) 2.조금느리게 3.보통 4.조금빠르게(기본) 5.빠르게(+10%)")
    rate = "+5%"
    v = input("  선택 (Enter=4): ").strip()
    if v in speeds: rate = speeds[v]

    # 5. 출력
    base = os.path.splitext(os.path.basename(src))[0] if not src.startswith("http") else "video"
    default_out = f"/tmp/{base}.mp3"
    out = input(f"\n💾 출력 파일명 (Enter={default_out}): ").strip()
    if not out: out = f"/tmp/{base}.mp4"

    # 6. 생성
    print(f"\n🎬 생성 시작! ({len(sections)}섹션, {voice})")
    print("-" * 40)

    work = tempfile.mkdtemp(prefix="hstudio_")
    clips = []

    for i, (title, body) in enumerate(sections, 1):
        print(f"[{i}/{len(sections)}] {title[:35]}", end=" ", flush=True)

        html = make_section_html(title, body, i, len(sections))
        png = os.path.join(work, f"f{i:03d}.png")
        screenshot(html, png)
        print("📸", end=" ", flush=True)

        mp3 = os.path.join(work, f"a{i:03d}.mp3")
        await tts(f"{title}. {body}", voice, mp3, rate)
        print("🔊", end=" ", flush=True)

        clip = os.path.join(work, f"c{i:03d}.mp4")
        frame_to_clip(png, mp3, clip)
        print("🎥", flush=True)
        clips.append(clip)

    print("-" * 40)
    print("🔗 클립 이어붙이는 중...")
    concat_clips(clips, out)

    size_mb = os.path.getsize(out)/(1024*1024)
    dur = float(subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","csv=p=0",out], capture_output=True, text=True
    ).stdout.strip() or 0)

    print(f"\n✅ 완료!")
    print(f"   파일: {out}")
    print(f"   크기: {size_mb:.1f}MB")
    print(f"   길이: {int(dur//60)}분{int(dur%60)}초")
    print(f"   섹션: {len(clips)}개")

    # TG 전송
    print(f"\n📤 텔레그램으로 보낼까요? (Enter=건너뛰기, y=보내기)")
    if input("  > ").strip().lower() in ('y','ㅛ'):
        import urllib.request as ur
        token = os.environ.get("TG_TOKEN",""); chat = os.environ.get("TG_CHAT","")
        if not token:
            token = subprocess.run("grep -oP 'TG_TOKEN=\\K.*' /root/.bashrc 2>/dev/null", shell=True, capture_output=True, text=True).stdout.strip().strip('"')
            chat = subprocess.run("grep -oP 'TG_CHAT=\\K.*' /root/.bashrc 2>/dev/null", shell=True, capture_output=True, text=True).stdout.strip().strip('"')
        if token and chat:
            subprocess.run([
                "curl","-s","-X","POST",
                f"https://api.telegram.org/bot{token}/sendVideo",
                "-F", f"chat_id={chat}",
                "-F", f"video=@{out}",
                "-F", "width=720","-F","height=1280",
                "-F", f"caption=🎬 {os.path.basename(out)} · {len(clips)}섹션 · {int(dur//60)}분{int(dur%60)}초"
            ], capture_output=True)
            print("  ✅ 전송 완료")
        else:
            print("  ❌ TG_TOKEN 없음")


if __name__ == "__main__":
    asyncio.run(run())
