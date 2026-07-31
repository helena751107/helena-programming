# Director Quality Gate (만점 체크리스트)

렌더 산출물은 아래를 **전부 PASS**해야 텔레그램/배포 가능.

| # | Gate | Fail 조건 |
|---|------|-----------|
| G1 | Intro CJK | 인트로 프레임에 토푸(□) 패턴 또는 글리프 0 |
| G2 | Lead black | 선두 연속 검정 > 0.5s (트림 후에도 남으면 fail) |
| G3 | Has motion UI | 중간 프레임 파일 크기/분산이 단색 미만 |
| G4 | Duration | 12s ≤ duration ≤ 150s |
| G5 | Audio | 오디오 트랙 존재, 무음만 아님 |
| G6 | Scenario | beat ≥ 3, 각 beat에 camera 정의 |

재발일지: `_notebook/48-director-video-recurrence_Grok.md`
