#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# record_voice_samples.sh — AI 성우 학습용 음성 샘플 녹음
#
# 사용법:
#   bash scripts/record_voice_samples.sh              # 30문장 전체
#   bash scripts/record_voice_samples.sh --quick 10   # 앞 10문장만
#   bash scripts/record_voice_samples.sh --single 5   # 5번 문장만
#
# 출력: voice_samples/0001.wav ~ 0030.wav (16kHz mono)
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SAMPLES_DIR="${REPO_ROOT}/voice_samples"
SENTENCES_FILE="${SAMPLES_DIR}/_sentences.txt"

# ── 기본값 ────────────────────────────────────────────────────────
TOTAL_SENTENCES=30
FIRST_SENTENCE=1
SAMPLE_RATE=16000
CHANNELS=1
DURATION_PER_SENTENCE=8  # 최대 녹음 시간 (초) — 충분히 읽고 여유

mkdir -p "$SAMPLES_DIR"

# ── 30문장 코퍼스 (한국어 음소 다양성 + 자연스러운 문장) ──────────
write_sentences() {
  cat > "$SENTENCES_FILE" << 'CORPUS'
안녕하세요, 저는 인공지능 성우입니다.
오늘 날씨가 정말 좋네요.
스마트폰 하나로 서버를 만들 수 있습니다.
리눅스는 자유롭고 강력한 운영체제입니다.
깃허브 액션으로 공짜 클라우드를 쓸 수 있어요.
터미널에서 명령어를 입력해 보세요.
파이썬으로 간단한 프로그램을 작성했습니다.
유튜브 채널을 개설하고 영상을 올렸습니다.
텔레그램 봇이 메시지를 보내 줍니다.
마크다운으로 문서를 작성하는 것이 편리합니다.
오픈소스 생태계는 정말 놀랍습니다.
음성 합성 기술이 나날이 발전하고 있어요.
딥러닝 모델을 학습시키는 과정은 재미있습니다.
프로그래밍을 배우면 세상이 달라 보여요.
작은 아이디어가 큰 변화를 만듭니다.
포기하지 않고 꾸준히 하는 것이 중요합니다.
에러 메시지를 읽는 것이 디버깅의 첫걸음입니다.
하나를 알면 열을 깨닫는 기쁨이 있습니다.
커피 한 잔 마시면서 코딩하는 시간이 좋아요.
기록하는 습관이 천재를 이깁니다.
작게 시작해서 크게 키우는 전략이 효과적입니다.
모르는 것을 부끄러워하지 마세요.
질문하는 사람이 결국 더 빨리 배웁니다.
매일 조금씩 성장하는 자신을 발견해 보세요.
혼자보다 함께할 때 더 멀리 갈 수 있습니다.
기술은 사람을 위한 도구일 뿐입니다.
좋은 코드는 읽기 쉬운 코드입니다.
완벽함보다 완성함이 더 중요합니다.
내일의 나는 오늘보다 나을 것입니다.
끝까지 들어 주셔서 감사합니다.
CORPUS
}

# ── 녹음 함수 ──────────────────────────────────────────────────────
record_one() {
  local idx="$1"
  local outfile="$2"
  local sentence="$3"

  printf '\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
  printf '🎤 문장 %02d/%d:\n' "$idx" "$TOTAL_SENTENCES"
  printf '   %s\n' "$sentence"
  printf '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
  printf '⏺ 녹음 준비... 엔터를 누르면 %d초간 녹음합니다\n' "$DURATION_PER_SENTENCE"
  printf '  (다시 하려면 Ctrl+C 후 --single %d 로 재시도)\n' "$idx"
  read -r

  # ffmpeg alsa 녹음 (proot Ubuntu / Termux)
  #   -f alsa -i default → 기본 마이크
  #   -f avfoundaton / -f dshow 도 자동 폴백
  local recorded=false

  # 시도 1: ALSA (proot Ubuntu 기본)
  if ffmpeg -y -f alsa -i default \
       -t "$DURATION_PER_SENTENCE" \
       -ar "$SAMPLE_RATE" -ac "$CHANNELS" \
       -sample_fmt s16 \
       "$outfile" 2>/dev/null; then
    recorded=true
  fi

  # 시도 2: PulseAudio
  if [ "$recorded" != true ]; then
    if ffmpeg -y -f pulse -i default \
         -t "$DURATION_PER_SENTENCE" \
         -ar "$SAMPLE_RATE" -ac "$CHANNELS" \
         -sample_fmt s16 \
         "$outfile" 2>/dev/null; then
      recorded=true
    fi
  fi

  # 시도 3: termux-microphone-recorder (Termux 환경)
  if [ "$recorded" != true ]; then
    if command -v termux-microphone-recorder &>/dev/null; then
      printf '  → Termux 마이크 API 사용\n'
      termux-microphone-recorder -f "$outfile" \
        -r "$SAMPLE_RATE" -c "$CHANNELS" \
        -b 16 -l "$DURATION_PER_SENTENCE" 2>/dev/null && recorded=true
    fi
  fi

  if [ "$recorded" != true ]; then
    printf '\n❌ 녹음 실패 — 마이크를 찾을 수 없습니다.\n'
    printf '   수동 녹음 방법:\n'
    printf '   1. 다른 앱으로 "%s" 녹음\n' "$sentence"
    printf '   2. 16kHz mono WAV로 저장 → %s\n' "$outfile"
    printf '   3. 엔터로 다음 문장 진행\n'
    read -r
    return 1
  fi

  # 정규화 (무음 트림 + loudnorm)
  local tmp="${outfile%.wav}_norm.wav"
  ffmpeg -y -i "$outfile" \
    -af "silenceremove=start_periods=1:start_duration=1:start_threshold=-50dB,
         loudnorm=I=-16:TP=-1.5:LRA=11" \
    -ar "$SAMPLE_RATE" -ac "$CHANNELS" \
    "$tmp" 2>/dev/null && mv "$tmp" "$outfile"

  local dur
  dur=$(ffprobe -v error -show_entries format=duration \
    -of default=nw=1:nk=1 "$outfile" 2>/dev/null || echo "0")
  printf '  ✅ 저장 완료: %s (%.1f초)\n' "$outfile" "$dur"
  return 0
}

# ── 메인 ────────────────────────────────────────────────────────────
main() {
  local quick=""
  local single=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --quick) quick="${2:-10}"; shift 2 ;;
      --single) single="$2"; shift 2 ;;
      *) echo "Usage: $0 [--quick N] [--single N]"; exit 1 ;;
    esac
  done

  write_sentences
  mapfile -t sentences < "$SENTENCES_FILE"

  if [ -n "$single" ]; then
    FIRST_SENTENCE="$single"
    TOTAL_SENTENCES="$single"
    local pad
    pad=$(printf '%04d' "$single")
    local outfile="${SAMPLES_DIR}/${pad}.wav"
    record_one "$single" "$outfile" "${sentences[$((single - 1))]}"
    echo ""
    echo "✅ 단일 문장 녹음 완료: $outfile"
    echo "   확인: ffplay $outfile"
    exit 0
  fi

  if [ -n "$quick" ]; then
    TOTAL_SENTENCES="$quick"
  fi

  echo "╔══════════════════════════════════════════════════════╗"
  echo "║  🎙 AI 성우 학습용 음성 샘플 녹음                      ║"
  echo "║  총 $TOTAL_SENTENCES 문장 · 문장당 ${DURATION_PER_SENTENCE}초 · 출력 16kHz mono   ║"
  echo "╚══════════════════════════════════════════════════════╝"
  echo ""
  echo "  팁: 조용한 곳에서, 자연스러운 속도로 읽어주세요."
  echo "  실수해도 괜찮습니다 — --single N 으로 재녹음 가능."
  echo ""

  for ((i = FIRST_SENTENCE; i <= TOTAL_SENTENCES; i++)); do
    local pad
    pad=$(printf '%04d' "$i")
    local outfile="${SAMPLES_DIR}/${pad}.wav"
    local sentence="${sentences[$((i - 1))]}"

    record_one "$i" "$outfile" "$sentence" || {
      printf '\n⏸  녹음 중단 (문장 %d). 이어서 하려면:\n' "$i"
      printf '   bash %s --quick $(( %d - %d + 1 ))\n' "$0" "$TOTAL_SENTENCES" "$((i - 1))"
      exit 1
    }
  done

  echo ""
  echo "╔══════════════════════════════════════════════════════╗"
  echo "║  🎉 녹음 완료!                                         ║"
  echo "║                                                      ║"
  echo "║  다음 단계:                                           ║"
  echo "║  python3 scripts/train_voice.py \\                    ║"
  echo "║    --samples voice_samples/ \\                        ║"
  echo "║    --out voice_models/my_voice.onnx \\                ║"
  echo "║    --base-model kokoro-ko                            ║"
  echo "╚══════════════════════════════════════════════════════╝"
}

main "$@"
