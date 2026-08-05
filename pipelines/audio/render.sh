#!/bin/bash
# 오디오 렌더링 예제 — FFmpeg
# pipelines/audio/ 에 .wav 파일 넣고 push → Actions가 이 스크립트 실행 → out/ 로 출력

set -e
mkdir -p out

echo "🎵 FFmpeg 오디오 렌더링 시작..."
echo ""

# 예제 1: 모든 WAV → MP3 320k
for f in *.wav 2>/dev/null; do
    [ -f "$f" ] || continue
    name="${f%.*}"
    ffmpeg -i "$f" -b:a 320k "out/${name}.mp3" -y 2>/dev/null
    echo "✅ $f → out/${name}.mp3"
done

# 예제 2: FLAC → OGG
for f in *.flac 2>/dev/null; do
    [ -f "$f" ] || continue
    name="${f%.*}"
    ffmpeg -i "$f" -c:a libvorbis -q:a 6 "out/${name}.ogg" -y 2>/dev/null
    echo "✅ $f → out/${name}.ogg"
done

# 예제 3: 모든 오디오 병합 (merge.list 있으면)
if [ -f merge.list ]; then
    ffmpeg -f concat -safe 0 -i merge.list -c copy out/merged.mp3 -y
    echo "✅ merge.list → out/merged.mp3"
fi

echo ""
echo "🎉 렌더링 완료. 결과는 Actions Artifact에서 다운로드."
ls -la out/ 2>/dev/null || echo "(빈 출력)"
