#!/usr/bin/env python3
"""
webpage_to_audiobook.py — 웹페이지 → Edge TTS 오디오북 변환기
=============================================================
S21 폰 단독 실행. PC/WSL 불필요. 외부 API 불필요.

사용:
  python3 scripts/webpage_to_audiobook.py https://example.com/page.html
  python3 scripts/webpage_to_audiobook.py /root/work/notebook/46-fridge-architecture_Claude.html
  python3 scripts/webpage_to_audiobook.py page.html --voice ko-KR-InJoonNeural

의존: edge-tts, ffmpeg (이미 설치되어 있음)
"""

import sys, os, re, asyncio, subprocess, argparse, tempfile
from pathlib import Path
from html.parser import HTMLParser


# ── HTML 텍스트 추출 ──────────────────────────────────────────────────────────

class TextExtractor(HTMLParser):
    """HTML에서 본문 텍스트만 추출 (script/style 제외)"""
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'code', 'pre'):
            self.skip = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'code', 'pre'):
            self.skip = False
        if tag in ('p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'br', 'hr'):
            self.text.append('\n')

    def handle_data(self, data):
        if not self.skip:
            t = data.strip()
            if t:
                self.text.append(t)


def extract_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return '\n'.join(parser.text)


# ── 텍스트 → 음성 세그먼트 분할 ────────────────────────────────────────────────

def split_segments(text: str, max_chars: int = 1500) -> list:
    """긴 텍스트를 TTS 적정 길이로 분할 (문단 단위)"""
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    segments = []
    buf = ""

    for para in paragraphs:
        if len(buf) + len(para) < max_chars:
            buf = (buf + "\n\n" + para).strip()
        else:
            if buf:
                segments.append(buf)
            buf = para

    if buf:
        segments.append(buf)

    return segments


# ── Edge TTS 변환 ─────────────────────────────────────────────────────────────

async def text_to_speech(text: str, voice: str, output: str, rate: str = "+5%"):
    """Microsoft Edge TTS — 무료·무제한·폰단독"""
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate)
    await comm.save(output)
    return output


async def segments_to_audio(segments: list, voice: str, workdir: str, rate: str = "+5%"):
    """모든 세그먼트 → 개별 MP3 파일"""
    files = []
    for i, seg in enumerate(segments):
        out = os.path.join(workdir, f"seg_{i:03d}.mp3")
        print(f"  🔊 [{i+1}/{len(segments)}] {seg[:60]}...")
        await text_to_speech(seg, voice, out, rate)
        files.append(out)
    return files


# ── FFmpeg 오디오 이어붙이기 ──────────────────────────────────────────────────

def concat_audio(files: list, output: str):
    """FFmpeg concat demuxer — 무손실 오디오 이어붙이기"""
    concat_list = os.path.join(os.path.dirname(output), "concat_list.txt")
    with open(concat_list, "w") as f:
        for fp in files:
            f.write(f"file '{fp}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list, "-c", "copy", output
    ], capture_output=True, check=True)

    return output


# ── HTML → 오디오북 메인 ─────────────────────────────────────────────────────

async def webpage_to_audiobook(source: str, voice: str = "ko-KR-SunHiNeural",
                                rate: str = "+5%", output: str = None):
    """웹페이지를 Edge TTS 오디오북으로 변환"""

    # 1. HTML 가져오기
    print(f"📄 소스: {source}")
    if source.startswith("http"):
        import urllib.request
        with urllib.request.urlopen(source) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    else:
        html = Path(source).read_text(encoding="utf-8", errors="replace")

    # 2. 텍스트 추출
    text = extract_text(html)
    if not text:
        print("❌ 추출된 텍스트가 없습니다")
        return None

    print(f"📝 텍스트: {len(text)}자")

    # 3. 세그먼트 분할
    segments = split_segments(text)
    print(f"✂️  세그먼트: {len(segments)}개")

    # 4. Edge TTS 변환
    workdir = tempfile.mkdtemp(prefix="helena_tts_")
    print(f"🔊 Edge TTS 변환 시작 (음성: {voice})")
    audio_files = await segments_to_audio(segments, voice, workdir, rate)

    # 5. FFmpeg 이어붙이기
    if output is None:
        base = Path(source).stem if not source.startswith("http") else "audiobook"
        output = f"/tmp/{base}.mp3"

    print(f"🔗 FFmpeg 이어붙이기 → {output}")
    concat_audio(audio_files, output)

    # 6. 결과
    size_mb = os.path.getsize(output) / (1024 * 1024)
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", output], capture_output=True, text=True
    ).stdout.strip() or 0)

    print(f"\n✅ 완료! {output} ({size_mb:.1f}MB, {duration/60:.1f}분)")
    print(f"   음성: {voice}")
    print(f"   세그먼트: {len(audio_files)}개")

    return output


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="웹페이지 → Edge TTS 오디오북")
    parser.add_argument("source", help="URL 또는 HTML 파일 경로")
    parser.add_argument("--voice", default="ko-KR-SunHiNeural",
                        help="Edge TTS 음성 (기본: ko-KR-SunHiNeural 여성)")
    parser.add_argument("--rate", default="+5%", help="말하기 속도 (기본: +5%%)")
    parser.add_argument("--output", "-o", help="출력 파일 경로")
    parser.add_argument("--list-voices", action="store_true", help="한국어 음성 목록")

    args = parser.parse_args()

    if args.list_voices:
        import edge_tts
        async def list_kr():
            voices = await edge_tts.VoicesManager.create()
            kr = [v for v in voices.voices if 'ko-KR' in v['Locale']]
            for v in kr:
                print(f"  {v['ShortName']:45s} {v['Gender']:8s} {v['FriendlyName']}")
        asyncio.run(list_kr())
        return

    asyncio.run(webpage_to_audiobook(args.source, args.voice, args.rate, args.output))


if __name__ == "__main__":
    main()
