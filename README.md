# Helena Programming — 온디바이스 + 웹MCP 콘텐츠 스튜디오

> **뼈대 전용 레포.** 콘텐츠는 Boss(헬레나)가 직접 채운다.
> AI 에이전트는 구조·파이프·자동화만 담당.

## 아키텍처

```
📱 온디바이스                          🌐 웹MCP
   Flutter APK                           Vercel + MCP Server
   ├── 다이어그램 렌더링                 ├── MCP API (/api/mcp)
   ├── 음성 더빙 (RVC)                    ├── 대시보드 (/)
   ├── SVG 합성                           └── 원격 렌더링
   └── 폰 네이티브 브릿지
```

## 퀵스타트

```bash
# 레포 클론
gh repo clone helena751107/helena-programming

# 온디바이스: APK 빌드 (GitHub Actions 수동 트리거)
gh workflow run build-apk.yml

# 웹MCP: Vercel 배포
cd web && vercel deploy --prod
```

## 디렉토리 구조

```
helena-programming/
├── apps/                    # 온디바이스 — Flutter APK 모노레포
│   └── helena-studio/       # 메인 스튜디오 앱
│       ├── android/         # Kotlin/Android
│       ├── lib/             # Dart/Flutter
│       └── assets/          # WebView launcher
├── web/                     # 웹MCP — Vercel 배포
│   ├── api/mcp/             # MCP 서버 엔드포인트
│   └── public/              # 대시보드
├── mcp/                     # Python MCP 서버 (로컬/WSL)
└── .github/workflows/       # CI/CD
```

## 라이선스

CONSTITUTION.md 제2조: 코드는 선물.
