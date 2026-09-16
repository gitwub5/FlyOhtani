## 2026-09-16 — Codex 타격 방향 독립 진단

- c812766 코드·B1 in_mid 포수 뒤 영상의 프레임 확인.
-9코스 OracleAimController, seed0 재현. 접촉점 배트 vx 모두 음수. terminal 뒤 마지막 ctrl 유지400 substep(100ms) 진단 연장 시 공 vx 모두 음수. 중앙 배트 vx=-9.319m/s,100ms 뒤 공 vx=-30.858m/s. 상세/한계: [검토](../B1-BATTING-REVIEW.md).
- 영상은 접촉 전5ms/frame, 종료 후0.25ms/frame을 같은30fps로 저장함을 확인. 시간 배율이 바뀌며 타구 추적 근거가 되지 못한다.
- 구현 파일은 수정하지 않았다. 타구 규약과 I-07b-fix를 문서화했다. 기존 전체 테스트 재실행은 하지 않았다.
