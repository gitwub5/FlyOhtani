# README 이미지

루트 README에 쓰는 그림. 전부 이 저장소의 코드로 만들었고, 스윙은 **스크립트**다.

| 파일 | 내용 | 만든 방법 |
| --- | --- | --- |
| `hit.gif` | 안타 에피소드 (실제보다 8배 느리게) | `python -m flyohtani.record pitch --out runs/record/hit` (커밋 `c4646d2`)의 `video.mp4`를 640 px로 줄여 GIF로 변환 |
| `batter-ready.jpg` | 준비 자세 | `flyohtani.world.batter`의 장면을 `READY_POSE`로 렌더링 (커밋 `84ae63d`) |
| `swing-strip.jpg` | 35 ms 데모 스윙 7장면 | 같은 장면에서 `swing_targets`를 따라가며 균등 간격으로 렌더링 |
| `fly-eyes.png` | 눈 카메라 입력 32×32 | `render_eyes` 출력을 6배 확대. 왼쪽 눈 3장(공이 멀리→가까이) + 오른쪽 눈 1장. 빨간 원은 설명용으로 덧그린 것 |
| `brain-circuit.jpg` | 뇌 지도 위 회로 4단계 | `flyohtani.brain.replay.wiring_replay`를 `viewer/`에 띄우고 headless Chrome으로 캡처. 밝기는 시냅스 수(활동 아님) |
| `viewer.jpg` | 뷰어 전체 화면 | `hit` 에피소드를 내보낸 뒤 `vite preview` 화면을 headless Chrome으로 캡처 |
