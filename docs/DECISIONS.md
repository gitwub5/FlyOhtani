# 설계 결정 위치

현재 결정의 단일 기준은 [PLAN](PLAN.md)의 D01~D12이다. 수치를 중복 관리하던 Q-01~06 표는 EXP-001 1.0의 실행 규약으로 대체했다.

- [DATA_MODEL](design/DATA_MODEL.md): 실제 데이터·회로·신경 방정식.
- [EXP-001](experiments/EXP-001-associative-learning.md): 자극·대조군·시드·점수·예산.
- [ENV-001](design/ENV-001-interception.md): 물리 과제의 수정 결정과 수용 기준.
- [VIZ-001](design/VISUALIZATION.md): 실제 연결 구조·스파이크 관찰.

사용자 확정 사항과 이번 설계에서 정한 가정을 구분한다. 변경 시 해당 문서의 버전·이유·영향을 기록하고 완료한 실행의 규약은 보존한다. 과거 일반 원칙(모듈 분리, 상태 분리, 고정 readout, 평가 중 학습 중단, 출처·시드 저장)은 [구조 계약](design/ARCHITECTURE.md)에 유지한다.

D12 야구장 확장: [ENV-002](design/ENV-002-baseball.md). 사용자 요청과 스케일/커리큘럼 설계값을 구분한다.
