---
date: 2026-07-17
task: Fusion 라이브 뷰어에 정면/측면 뷰 추가(1단계) + 자유 회전 3D orbit 뷰(2단계)
planner: Claude
executor: codex
status: done
---

# PLAN03 — Fusion 뷰어 다시점(정면·측면·자유회전 3D)

> 파일: `docs/plans/2026_07/17_PLAN03_fusion_views.md` (식별자 = PLAN03).

## 역할 (v2 기준)
**Claude 기획 → 사용자 승인 → codex 구현.** 2026-07-17 v2 템플릿 채택으로 워크스페이스 기본
역할이 이렇게 정리됐고, 이 plan 도 그 규칙을 따른다. 1단계는 이미 done, 2단계 orbit 은
사용자가 "3D 포즈 플랜 실행" 을 지시해 `status: approved` 가 됐다.

## 한 줄 결론
`scripts/zed_fusion_viz.py` 의 world 창을 **다시점**으로 일반화한다.
**1단계(이번 구현): `--view {top,front,side}` + 실행 중 숫자키 전환**, 기본 **front(정면)**.
**2단계(이어서 구현): `--view orbit` 자유 회전 3D**(cv2 회전 정사영, OpenGL 불필요, 키로 az/el 조절).
카메라 오버레이 창(raw 2D)은 그대로 둔다.

## 이번 codex 실행 범위 (2단계 = orbit 3D) — 반드시 준수

> **1단계(top/front/side + 숫자키 1/2/3)는 이미 구현·검증 완료다.** 이번 실행은 **2단계 orbit 만**
> 추가한다. 아래 "## 2단계 스펙" 절이 이번 구현의 명세다.

- **이번 실행 = 자유 회전 3D orbit 구현.** 문서 하단 **"## 2단계 스펙"** 을 그대로 구현한다:
  `_project_world` 의 `orbit` 분기(회전 정사영), `_draw_world_view` 의 orbit 렌더 + world 축 삼각대,
  런타임 키(`4`=orbit, `j/l`=az, `i/k`=el, `u`=리셋), HUD 의 az/el 표시.
- 지금 `scripts/zed_fusion_viz.py` 에 있는 **orbit stub**(`_draw_orbit_stub`, "orbit: 2단계 예정(미구현)"
  안내)을 **실제 orbit 렌더로 대체**한다. 이미 파싱만 해 두던 `--az`/`--el` 을 실제로 사용한다.
- 🚨 **기존 front/side/top 뷰는 절대 건드리지 말 것 (사용자 명시 지시).**
  - `_project_world` 의 `top`(h=+X,v=+Y) / `front`(h=-Y,v=+Z) / `side`(h=+X,v=+Z) 분기와
    `_world_origin`, `_draw_world_reference`(바닥선·눈금), 숫자키 `1/2/3` 전환, 기본 `--view front`
    는 **현재 동작 그대로 유지**한다. 리팩터·정리·부호 변경 금지.
  - orbit 은 **순수 추가**여야 한다. front 뷰가 지금과 조금이라도 다르게 보이면 실패로 간주한다.
- 카메라 오버레이 창(raw 2D, BODY_18), `--save` 합성 레이아웃, headless 규칙, @30 고정도 불변.
- **완료 후 이 plan 의 `status` 를 `done` 으로 바꾼다**(2단계까지 끝나므로).

## 왜 이 plan이 필요한가
현재 뷰어(PLAN02)의 융합 창은 **top-down(X-Y) 한 뷰뿐**이라, 사람이 서 있는 **포즈 자체**가
납작하게 보인다. 포즈 확인에는 **정면(Y-Z, 좌우×높이)** 이 자연스럽고, 전후 기울임/뻗음은 **측면(X-Z)**,
입체 파악은 **자유 회전 3D** 가 낫다. 융합 결과는 이미 world 3D 좌표라, 시점 추가는 "어느 축으로
투영하느냐"의 문제이며 대부분 기존 그리기 로직을 일반화하면 된다.

## 지금까지 이어진 맥락 (이미 확정된 사실)
- 융합 스켈레톤 = **BODY_34**, **fusion world frame**, 단위 METER, 좌표계 `RIGHT_HANDED_Z_UP_X_FWD`
  → **X=전방, Y=좌, Z=상**.
- 현재 뷰어 `scripts/zed_fusion_viz.py`:
  - 창 2개: `CAMERA_WINDOW="cameras (raw 2D)"`(BODY_18 오버레이, 좌|우), `TOPDOWN_WINDOW="fusion top-down (world)"`.
  - world 창은 `zed_fusion_bodytrack.py` 의 `_draw_topdown(cv2, np, size, scale, fused, raw_by_serial, joints)`
    를 import 해 그린다. 그 투영식은 `sx=ox+X*scale`, `sy=oy-Y*scale` (즉 수평=X, 수직=Y, -Z 방향으로 내려다봄).
  - `--topdown-size`(기본 900), `--topdown-scale`(기본 180 px/m), `--save`(합성 MP4), headless 규칙,
    `q`/ESC 종료, @30 고정 등은 PLAN02 에서 확정.
- 뷰어는 bodytrack 에서 `_draw_topdown, _init_fusion, _open_sender, _read_config, _joint_indices,
  _available_serials, FUSED_BODY_FORMAT_NAME` 를 import 중(모듈은 `__main__` 가드).

## 지금 기준 판단
- world 창의 투영을 **뷰어 안에서 일반화**한다. `zed_fusion_bodytrack.py` 는 **건드리지 않는다**
  (`_draw_topdown` 은 그대로 두고, 뷰어에 새 `_draw_world_view` 를 만든다).
- 시점 선택은 **런타임 토글**로 통합: 숫자키 `1`=top, `2`=front, `3`=side, (2단계) `4`=orbit.
  `--view` 로 초기값 지정(기본 front). 한 창(`WORLD_WINDOW`)에서 현재 뷰만 표시.
- 정사영(orthographic) 유지 — 원근 없음(스켈레톤 비교엔 정사영이 더 읽기 쉬움). orbit 도 회전 정사영.

## 이번에 할 것 (1단계 = 이번 구현)
1. world 창 투영을 top/front/side 로 일반화하고, 실행 중 숫자키로 전환.
2. 기본 뷰를 **front(정면)** 로. 창 제목/HUD 에 현재 뷰와 축을 표시.
3. 바닥 기준선(Z=0) 과 스케일 눈금 등 최소 참조를 front/side 에도 그려 방향을 알기 쉽게.

## 이어서 할 것 (2단계 = 다음 구현, 이 plan 안에서 스펙 확정)
4. `--view orbit`: 회전 정사영 3D. 키로 방위각(az)·고도각(el) 조절, 자유 회전.

## 구현해야 할 것 (파일 단위)
- **수정 대상은 `scripts/zed_fusion_viz.py` 하나.** (bodytrack/​make_config 불변.)
- **import 보강**: 그리기 일반화를 위해 `zed_fusion_bodytrack` 에서 `BONES_34, _ok_keypoint, _tolist`
  를 추가로 import(없으면 뷰어에 동일 내용 최소 복제). 기존 `_draw_topdown` import 는 유지하거나 제거.
- **투영 함수 신설** `_project_world(point, view, az, el)` → `(h, v)` (미터 단위, 화면 부호 적용 전):
  - `top`   : `h = +X, v = +Y`      (현재 top-down 과 동일; 내려다봄)
  - `front` : `h = -Y, v = +Z`      (정면; 좌우=Y, 높이=Z. Y 부호는 좌우가 실제와 맞도록 조정 가능)
  - `side`  : `h = +X, v = +Z`      (측면; 전후=X, 높이=Z)
  - `orbit` : **이번(2단계)에 구현** — 회전 정사영. 식·기본각·키맵은 하단 "2단계 스펙" 참조.
    기존 top/front/side 분기는 그대로 두고 orbit 분기만 추가한다.
  - 화면 매핑은 공통: `sx = ox + h*scale`, `sy = oy - v*scale` (v 가 위로). 원점 `ox=size/2`,
    `oy`는 뷰별로 조정(top 은 기존처럼 `0.72*size`, front/side/orbit 은 사람이 화면 안에 들어오게 `0.85*size` 부근).
- **`_draw_world_view(cv2, np, size, scale, view, fused, raw_by_serial, joints, az, el)`** 신설:
  - `_project_world` 로 각 keypoint 투영 → `BONES_34` 로 뼈, keypoint 점(색 = 신뢰도 빨강→초록,
    기존 top-down 색 규칙 재사용). `_ok_keypoint` 로 유효성 필터.
  - raw world 포인트(옅은 회색) 오버레이는 기존 top-down 과 동일하게 유지.
  - **참조 그래픽**: front/side 는 바닥선(Z=0 수평선) + 세로 높이 눈금; orbit 는 원점에서 world 축
    X(빨강)/Y(초록)/Z(파랑) 짧은 축 삼각대(triad)를 같은 투영으로 그림(방향 감).
  - HUD: `view=<현재뷰> axes=<...>` + (orbit) `az/el` 값, 융합 body 수, live fps.
- **런타임 전환**: `1/2/3` → top/front/side (**이미 구현됨 — 변경 금지**), `q`/ESC 종료 유지.
  이번엔 `4` → orbit 실렌더로 바꾸고 회전키 `j/l`(az ∓/±), `i/k`(el ±/∓), `u`(리셋)를 추가한다.
- **CLI**: `--view {top,front,side,orbit}`(기본 `front`), `--az`(기본 30, deg), `--el`(기본 20, deg)
  추가. 나머지 인자(`--config`, `--fps`, `--save`, `--topdown-size`, `--topdown-scale`, headless 규칙 등)
  는 그대로. 창 이름은 `WORLD_WINDOW="fusion world view"` 로 하고 제목/HUD 로 현재 뷰 구분(기존
  `TOPDOWN_WINDOW` 상수는 유지하되 실사용은 새 이름으로; 합성 저장도 현재 뷰 프레임을 사용).
- **합성 저장(`--save`)**: 기존 `_composite_frame`(카메라 패널 + world 패널 vconcat) 은 그대로 쓰되,
  world 패널을 현재 선택 뷰로 렌더한 이미지로 넣는다. 출력 크기·레이아웃 고정 유지.

## 참고해야 할 것 (왜 보는지 함께)
- `scripts/zed_fusion_viz.py` — 수정 본체. 현재 world 창 렌더/`_composite_frame`/`_show`/키 처리/HUD 위치.
- `scripts/zed_fusion_bodytrack.py` `_draw_topdown` — 투영·뼈·색·raw 오버레이·바닥선 그리는 방식의
  레퍼런스(그대로 일반화). `BONES_34`, `_ok_keypoint`, `_tolist`, `joints` 인덱스도 여기.
- 좌표계 `RIGHT_HANDED_Z_UP_X_FWD` (X 전방/Y 좌/Z 상) — 각 뷰의 축 선택 근거.

## 신경써야 할 것 (가드레일)
- **기존 파일 런타임 동작 변경 금지**: `zed_fusion_bodytrack.py` / `zed_make_fusion_config.py` 의 CLI·동작
  불변. 그리기 일반화는 **뷰어 안에서만**. `_draw_topdown` 을 개조하지 말고 새 함수 추가.
- **카메라 오버레이 창은 불변**: 이번 변경은 world 창(다시점)만. BODY_18 2D 오버레이 로직 그대로.
- **좌표/포맷 구분 유지**: 카메라 창 = 픽셀 2D(BODY_18), world 창 = world 3D(BODY_34) 투영.
- **@30 고정**, headless(`DISPLAY` 없음)면 `--save` 강제 규칙(PLAN02) 그대로.
- **좌우 방향**: front 에서 Y 부호를 잘못 주면 사람 좌우가 뒤집힌다. 관찰자 정면 기준 자연스럽게
  (실측으로 좌 카메라 S/N 13870389 쪽이 화면에서 맞는지) 확인하고 부호 고정. 애매하면 주석으로 남김.
- **검출 0 / nan / 화면 밖 좌표**: `_ok_keypoint` 로 건너뛰고 예외 없이 빈 창이라도 떠야 함.
- **샌드박스에 카메라·GPU·디스플레이 없음**: Codex 는 라이브 실행 불가. 검증은 `py_compile` +
  `--help`(새 인자 노출) + `--fps 60` 거부 + headless 가드까지. **라이브 확인은 사용자 `zed` env**.
- **1·2단계 분리**: 1단계에서 orbit 키/렌더가 미완이면 `4`/`--view orbit` 는 "미구현" 안내로 안전 처리
  (크래시 금지). 2단계에서 채운다.

## 이번에는 하지 않는 것 (non-scope)
- OpenGL/GLViewer 기반 본격 3D 렌더(무겁다). orbit 는 cv2 회전 정사영으로만.
- 융합 스켈레톤을 카메라 영상에 재투영(fused-on-camera) — 별도 plan.
- ZED360 캘리브레이션 자체, hand-eye, ROS2, 2×HD720@60, 로그 스키마 변경.

## 근거
- 융합 결과가 world 3D 라 top/front/side 는 투영 축 교체로 거의 무비용. orbit 도 정사영 회전 한 번.
- 사용자 요청: 정면 뷰 먼저, 자유 회전 3D 는 이어서.

## 검증
- 1단계:
  - `python3 -m py_compile scripts/zed_fusion_viz.py` 통과.
  - `python3 scripts/zed_fusion_viz.py --help` 에 `--view/--az/--el` 노출, `--fps 60` 거부, headless 가드 유지.
  - (사용자, `zed` env, 사람) `python3 scripts/zed_fusion_viz.py --config logs/fusion_manual.json`
    → world 창이 **정면**으로 뜨고, 숫자키 `1/2/3` 으로 top/front/side 전환, 사람 서 있는 포즈가
    front 에서 똑바로 보이는지 확인. 필요시 `--save`.
- 2단계:
  - `--view orbit` 로 3/4 시점이 뜨고 `j/l/i/k` 로 회전, `u` 리셋 동작. `el≈90` 에서 top-down 유사,
    `el≈0` 에서 front 유사인지 육안 확인.

## 2단계 스펙 (다음 구현, 이번엔 손대지 않음)
다음 handoff 에서 `zed_fusion_viz.py` 에만 추가:
- `_project_world` 의 `orbit` 분기(회전 정사영):
  - `h = -X*sin(az) + Y*cos(az)`
  - `v = (X*cos(az) + Y*sin(az))*sin(el) + Z*cos(el)`
  - 성질: `el=0`→front, `el≈90°`→top-down 근사, `az`=수직축 궤도 회전. 기본 `--az 30`, `--el 20`(deg).
- `_draw_world_view` 의 orbit 렌더 + 원점 world 축 삼각대(X빨강/Y초록/Z파랑) 같은 투영으로.
- 런타임 키: `4`=orbit 선택, `j/l`=az ∓/± (±5°), `i/k`=el ±/∓, `u`=az·el 리셋,
  `[`/`]`=scale 축소/확대(선택). HUD 에 `az/el` 표시.
- 검증: `--view orbit` 로 3/4 시점, `j/l/i/k` 회전, `u` 리셋, `el≈90`↔top / `el≈0`↔front 수렴 확인.
- 완료 시 이 plan `status` 를 `done` 으로.

## 다음 단계
- (선택) fused-on-camera 재투영 뷰(카메라 pose+intrinsics 사용) 별도 plan.
- ZED360 캘리브레이션 교체 후 다시점 정합 재확인.
