# CONSTITUTION.md — Helena Programming

> 제정: 2026-07-31
> 이 문서는 Helena Programming 프로젝트의 근본 목적과 불변 원칙을 규정한다.
> 모든 AI 에이전트는 작업 시작 전 이 문서를 먼저 읽어야 한다.

---

## 전문 — 온디바이스 + 웹MCP 듀얼스택

Helena Programming은 **콘텐츠 제작을 온디바이스(APK)와 웹MCP(Vercel)로 양분한 스튜디오**다.

```
온디바이스 (Flutter APK)          웹MCP (Vercel + MCP Server)
  │                                  │
  ├── 다이어그램 생성 (Mermaid)      ├── MCP API 엔드포인트
  ├── 음성 더빙 (RVC 클론)           ├── 대시보드 (HTML)
  ├── SVG/도면 합성                  ├── 원격 렌더링
  └── 폰 네이티브 기능                └── GitHub Actions 연동
```

## 제1조 — 콘텐츠는 사람이, 구조는 코드가

- 이 레포는 **구조(structure)** 만 제공한다.
- 콘텐츠 제작·채우기는 Boss(헬레나)의 영역.
- AI 에이전트는 뼈대·파이프·자동화를 담당.

## 제2조 — dtslib1979 냉장고 상속

- `dtslib-apk-lab`의 APK 빌드 구조를 계승한다.
- `parksy-audio`의 MCP 서버 패턴을 계승한다.
- `parksy-image`의 도면·웹툰 자산을 참조할 수 있다.
- 모든 상속 자산은 CONSTITUTION.md 제2조(코드는 선물)에 따른다.

## 제3조 — 빌드 원칙

- APK: GitHub Actions → Flutter 빌드 → APK 아티팩트
- 웹: GitHub Actions → Vercel 배포
- 모든 빌드는 CI에서만 — 로컬 Android Studio 불필요
- Play Store 등록 구조는 갖추되, 실제 배포는 Boss 결정

## 제4조 — 불변 원칙

1. 사용자는 Boss(헬레나) 한 명.
2. 콘텐츠 ≠ 코드 — 이 레포에 실제 콘텐츠(글·이미지·음원)는 넣지 않는다.
3. 외부 API 의존 최소화 — 냉장고 자산 + 온디바이스 우선.
4. 구조는 dtslib-apk-lab을 따르되, 목적은 콘텐츠 스튜디오.

---

## 부칙 — 관련 문서

- 모레포: `helena751107/helena_phone` (워크스페이스)
- 냉장고: `dtslib1979/*` (28종 자산 풀)
- 전문: `_notebook/46-fridge-architecture_Claude.md`
