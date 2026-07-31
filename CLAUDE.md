# CLAUDE.md — Helena Programming

> 이 문서는 AI 에이전트(Claude Code)가 이 레포에서 작업할 때 따라야 할 규칙을 정의한다.
> 작업 시작 전 CONSTITUTION.md를 먼저 읽을 것.

## 작업 원칙
- **구조만, 콘텐츠는 넣지 않는다** — Boss(헬레나)가 직접 콘텐츠를 채운다.
- **커밋 자주, 작게** — 기능 단위로 쪼개서 커밋
- **dtslib-apk-lab 패턴을 따른다** — 앱 구조·빌드·CI/CD

## 빌드 규칙
- APK는 GitHub Actions에서만 빌드 — 로컬 Flutter SDK 불필요
- 웹은 Vercel로 자동 배포 — `web/` 디렉토리 변경 시 트리거
- Play Store 등록 구조는 갖추되, 실제 배포는 Boss 결정

## AI 행동 규칙
- 작업 전 `git pull`로 최신 상태 확인
- 완료 후 `git push` 자동 실행
- 커밋 메시지에 작업 맥락 포함
- 구조 변경 시 `app-registry.json` 업데이트

## 참조 자산 (냉장고)
- APK 빌드 구조: `dtslib1979/dtslib-apk-lab`
- MCP 서버 패턴: `dtslib1979/parksy-audio/pre-season/mcp_voice/`
- 도면·웹툰 자산: `dtslib1979/parksy-image/도면/`, `dtslib1979/parksy-image/웹툰/`
- 음성 클론: `dtslib1979/parksy-audio/pre-season/mcp_voice/phone_rvc.py`
