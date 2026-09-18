"""FlyShohei -- 던지는 쪽.

오타니는 치기도 하고 던지기도 한다. 이 저장소에서 `flyohtani`가 타석의 파리라면
`flyshohei`는 마운드의 파리다. 투구에 대해 정해야 하는 것(구종, 구속, 비행 시간,
릴리스 지점, 마운드 위에 선 몸)은 전부 여기 있다.

왜 나눴나: 투구 상수가 `flyohtani/world/batter.py`(장면 만들기) 안에 섞여 있었고, 구종을
늘리려면 타자 코드를 건드려야 했다. 실제로 릴리스 지점이 존을 따라 움직이는
버그가 거기서 나왔다.

두 모듈로 나뉘어 있고, **그 순서가 중요하다**:

    pitch   투구의 수치와 기하. `units` 말고는 아무것도 임포트하지 않는다
            (leaf). 그래서 `flyohtani.world.batter`가 이걸 임포트해도 순환이 없다.
    body    마운드 위 투수 파리의 MJCF. `flyohtani.world.batter`의 몸 만들기를 쓰므로
            **반대 방향**이다 -- 장면을 만드는 쪽에서 늦게 임포트한다.

이 `__init__`은 `pitch`만 끌어온다. `body`를 여기서 임포트하면 그 순환이 생긴다.
"""
from __future__ import annotations

from flyshohei.pitch import ARSENAL, STANDARD, Pitch, geometry, get

__all__ = ["ARSENAL", "STANDARD", "Pitch", "geometry", "get"]
