# 🔧 헬레나 CPU 파이프라인

> GitHub Actions public repo = Actions **무제한** + **7GB RAM** + Ubuntu 24.04.
> 이걸로 APK·오디오·CAD·범용 컴퓨트 전부 공짜로 돌린다.

## 파이프라인 목록

| 파이프 | workflow | 트리거 | 설명 |
|--------|----------|--------|------|
| **APK 빌드** | `build-apk.yml` | push / 수동 | Flutter APK |
| **오디오** | `render-audio.yml` | push / 수동 | FFmpeg + Reaper 렌더링 |
| **CAD** | `render-cad.yml` | push / 수동 | FreeCAD 파라메트릭 |
| **컴퓨트** | `compute.yml` | push / 수동 | 범용 Python·Shell |
| **Deploy** | `deploy-vercel.yml` | push | Vercel 자동 배포 |
| **Guard** | `constitution-guard.yml` | PR | 헌법 강제 |

## 디렉토리 구조

```
pipelines/
├── README.md           ← 이 파일
├── audio/              ← 오디오 프로젝트·render.sh
│   ├── render.sh       ← 자동 실행됨
│   ├── out/            ← 렌더 출력 (mp3/wav)
│   └── *.wav *.rpp     ← 소스 파일
├── cad/                ← FreeCAD 프로젝트
│   ├── render.py       ← 자동 실행됨
│   ├── out/            ← 출력 (stl/step)
│   └── *.FCStd         ← FreeCAD 모델
└── compute/            ← 범용 스크립트
    ├── run.sh / run.py ← 자동 실행됨
    └── out/            ← 출력 파일
```

## 사용법

### APK 빌드

```bash
# apps/helena-studio/ 밑에 Flutter 코드 넣고 push → 자동 빌드
# 또는 Actions 탭에서 "Build Helena Studio APK" → Run workflow
```

### 오디오 렌더링

```bash
# 1. pipelines/audio/ 밑에 .wav .rpp 파일 넣기
# 2. render.sh 작성 (선택 — 없으면 모든 wav→mp3 자동)
# 3. push → Actions에서 자동 렌더링
```

### CAD

```bash
# 1. pipelines/cad/render.py 작성
# 2. push → FreeCAD CLI에서 실행
```

### 범용 컴퓨트

```bash
# Actions 탭 → CPU Compute → Run workflow → 명령어 입력
# 예: bash build-something.sh
#     python3 heavy-analysis.py
```

## 스펙

| 리소스 | 제공량 |
|--------|--------|
| CPU | 2코어 x86_64 |
| RAM | **7GB** |
| 디스크 | 14GB (임시) |
| OS | Ubuntu 24.04 |
| 제한 | 6시간/실행, 무제한 실행 |
| 비용 | **PUBLIC REPO = FREE** |
