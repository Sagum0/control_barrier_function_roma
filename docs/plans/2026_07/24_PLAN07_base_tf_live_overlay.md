---
date: 2026-07-24
task: 라이브 ZED LEFT 영상에 base(로봇) 좌표축을 실시간 오버레이하는 새 뷰어. 시작 시 ArUco 큐브를 1회 측정해 base_T_cam 을 고정한 뒤, 이후 매 프레임 base 원점 좌표축을 그려 imshow 로 확인
planner: Claude
executor: codex
status: done
---

# PLAN07 — base 좌표축 라이브 오버레이 뷰어

> 파일: `docs/plans/2026_07/24_PLAN07_base_tf_live_overlay.md` (식별자 = PLAN07).

## 한 줄 결론

새 스크립트 `scripts/base_tf_live.py` 를 추가한다. 뷰어를 켜면 **시작 시 ArUco 큐브를 잠깐
보고 base_T_cam 을 1회 측정해 고정**하고, 그 뒤로는 **라이브 LEFT 영상에 base(로봇) 원점의
좌표축(빨강=X, 초록=Y, 파랑=Z)을 매 프레임 겹쳐 그려 `imshow`** 한다. 카메라·큐브가 고정이라
매 프레임 재측정하지 않는다 — 한 번 딴 값을 화면에 계속 얹어 **TF 가 실제 위치에 맞는지 육안으로
실시간 확인**하는 것이 목적이다. **기존 검증된 스크립트는 안 건드리고 새 파일만 추가한다.**

## 왜 이 plan 이 필요한가

PLAN06 으로 base 기준 카메라 pose(`base_T_cam`)와 `base_T_world` 를 측정해 yaml·ROS2 static
TF 까지 발행했지만, **그 측정이 맞는지 확인하려면 지금은 RViz2/tf2 를 띄워야 한다.** 사용자는
그보다 가볍게, **카메라가 찍은 실제 영상 위에 base 좌표축이 실제 로봇/큐브 자리에 얹히는지를
라이브로 보고 싶다.** 축 뭉치가 실제 base 위치에 딱 맞으면 측정이 옳고, 삐뚤어져 있으면 좌표계
(optical↔body, 방향 부호) 오류가 눈에 바로 드러난다. RViz2 없이 `imshow` 한 창으로 끝난다.

## 지금까지 이어진 맥락 (이 plan 만 읽어도 되게 재서술)

프레임 표기: `T_A_B` = B 좌표의 점을 A 좌표로 보냄 (`p_A = T_A_B · p_B`).

1. **하드웨어/환경**: ZED-M 2대 (S/N `13870389`=zed1, `19321109`=zed2), SDK 5.4, pyzed 는 conda
   `zed` env(Python 3.10), Ubuntu 22.04. USB 컨트롤러 1개 → 카메라는 **동시에 한 대씩만** 여는 게
   안전. 해상도 **HD720@30 고정**(@60 붕괴).
2. **좌표계 통일**: 전 구간 `RIGHT_HANDED_Z_UP_X_FWD` / METER (X=전방, Y=좌, Z=상).
3. **base 프레임 정의(PLAN06, CAD 확정)**: 원점 = ArUco 큐브의 마커 **1** 중심, +X=정면 법선,
   +Z=위, +Y=왼쪽. 큐브는 세 면(마커 0/1/2)이 90°로 배치. 데이텀은
   `logs/base_cube_datum.json`(사용자 확정 파일; 없으면 `logs/base_cube_datum.example.json`).
4. **이미 있는 검출/변환 자산(재사용 대상)**:
   - `scripts/aruco_cube_datum.py` (PLAN06, pyzed 의존 없음) — 순수 변환 라이브러리.
     - `R_BODY_OPTICAL`, 4×4 `T_BODY_OPTICAL` — optical(X우·Y하·Z전) → body(X전·Y좌·Z상) 고정 회전.
     - `load_datum(path) -> markers{ id: T_base_marker(4×4) }, tag_size_m, dictionary`.
     - `pnp_cam_optical_T_marker(corners_px, tag_size_m, K) -> [(optical_T_marker(4×4), reproj_err), ...]`
       (재투영오차 오름차순, `SOLVEPNP_IPPE_SQUARE` 두 해).
     - `base_T_cam_from_marker(T_base_marker, optical_T_marker) -> base_T_cam(body 4×4)`.
     - `average_poses(list_of_4x4) -> 4×4` (병진 중앙값 + Markley 쿼터니언 평균).
     - `mat_to_xyzquat`, `_mat_to_quat`, `_quat_to_mat` (yaml 왕복용).
   - `scripts/measure_base_cam.py` (PLAN06, pyzed) — 측정 도구. 아래 헬퍼를 **import 재사용**한다
     (이 파일은 수정하지 않는다):
     - `open_camera(serial)` — serial 지정 open, HD720/30, depth NONE, `disable_self_calib=True`,
       COORD/UNIT 설정, 열린 serial 검증까지 포함.
     - `camera_matrix(zed)` — rectified LEFT intrinsic K(distortion 0).
     - `make_detector(dictionary)` — `cv2.aruco.ArucoDetector`.
     - `parse_serial_map`, `child_frame`, `DEFAULT_SERIAL_MAP`, `COORD`, `UNIT`.
     - 측정 게이팅 상수/로직(`--max-reproj`, `--ambiguity-ratio`)의 의미는 §구현에서 동일하게 이식.
   - `logs/fusion_zed360.json` (읽기 전용) — `sl.read_fusion_configuration_file` 로 `world_T_cam`
     을 얻는 원천. **이번 plan 에서는 필요 없다**(base 축만 그림; fusion_world 는 non-scope).

## 지금 기준 판단 (사용자와 확정)

- **측정은 시작 시 1회, 그 뒤 고정.** 카메라·큐브가 고정이므로 매 프레임 재측정하지 않는다.
  큐브는 시작 warmup 동안만 보이면 되고, 라이브 중에는 치워도 된다.
- 그릴 것은 **base 원점 좌표축 하나**다. fusion_world 축·스켈레톤 변환은 이번 범위 밖.
- 측정 품질 게이트(재투영오차·IPPE 모호성·ID 화이트리스트)는 **PLAN06 measure_base_cam 과 동일
  기준**을 쓴다(같은 함수/상수 재사용). 새 게이트를 발명하지 않는다.
- 카메라는 **기본 두 대를 순차로** 확인한다(한 대 측정→라이브 창→`q` 로 다음 대). `--serial` 로 한
  대만 지정 가능. 동시 2대 open 은 USB 제약상 하지 않는다.
- 큐브 없이 이미 저장된 값으로만 보고 싶을 때를 위해 `--from-yaml` 로 PLAN06 산출물
  (`logs/base_cam_extrinsics.yaml`)에서 `base_T_cam` 을 복원해 warmup 측정을 건너뛰는 경로도 둔다.

## 이번에 할 것

`scripts/base_tf_live.py` (신규) 하나만 추가한다. pyzed + cv2 + numpy, conda `zed` env 에서
실행. ROS2 import 없음. 화면 출력만 하고 파일은 만들지 않는다(옵션 `--save-frame` 제외).

## 구현해야 할 것 (파일 단위)

### 신규 `scripts/base_tf_live.py`

import 재사용(새로 짜지 말 것):
```
from aruco_cube_datum import (T_BODY_OPTICAL, load_datum, pnp_cam_optical_T_marker,
                              base_T_cam_from_marker, average_poses, mat_to_xyzquat)
from measure_base_cam import (open_camera, camera_matrix, make_detector,
                              parse_serial_map, child_frame, DEFAULT_SERIAL_MAP, COORD, UNIT)
```

CLI(argparse):
- `--datum PATH` (기본 `logs/base_cube_datum.json`) — base_T_marker 데이텀 + tag_size + dictionary.
- `--serial-map "13870389=zed1,19321109=zed2"` (기본 `DEFAULT_SERIAL_MAP`) — serial→이름.
- `--serial N` (선택) — 지정 시 그 serial 한 대만. 없으면 serial-map 전체를 **순차** 확인.
- `--warmup N` (기본 60) — 시작 시 base_T_cam 측정에 쓸 프레임 수.
- `--max-reproj PX` (기본 1.0), `--ambiguity-ratio R` (기본 0.3) — measure_base_cam 과 동일 게이트.
- `--axis-len M` (기본 0.2) — 그릴 base 좌표축 길이(미터).
- `--from-yaml PATH` (선택) — 지정 시 warmup 측정을 건너뛰고 이 yaml 에서 base_T_cam 을 복원.
- `--save-frame PATH` (선택, 헤드리스) — 마지막 오버레이 프레임 1장 저장. 지정 시 imshow 없이 동작 가능.

흐름(카메라 한 대 기준, 여러 대면 순차 반복):
1. `load_datum(args.datum)` → markers, tag_size, dictionary. `make_detector(dictionary)`.
2. `open_camera(serial)` → `K = camera_matrix(zed)`.
3. **base_T_cam 확정**:
   - `--from-yaml` 이면: yaml 의 `transforms` 에서 `child == child_frame(name)` 인 항목의
     translation+rotation_quat 로 base_T_cam(4×4) 복원(회전은 `aruco_cube_datum._quat_to_mat`).
     이 경로는 warmup 프레임 grab 없이 바로 라이브로 넘어간다.
   - 아니면(기본): `--warmup` 프레임 동안 grab → `retrieve_image(LEFT)` → BGRA→GRAY →
     `detectMarkers` → datum 화이트리스트 ID 만 → `pnp_cam_optical_T_marker` →
     게이트(재투영오차 ≤ `--max-reproj`, `err0/err1 ≤ --ambiguity-ratio`, 유한값) 통과분마다
     `base_T_cam_from_marker(markers[id], optical_T_marker)` 후보 수집 → `average_poses` 로 확정.
     후보가 0개면 그 카메라는 경고 출력 후 건너뛴다(다음 대로).
4. **라이브 오버레이 루프**(무한, `q`/ESC 종료):
   - grab → `retrieve_image(LEFT)` → BGRA→BGR.
   - **base 원점 좌표축을 optical 프레임으로 옮겨 그린다.** base_T_cam 은 `T_base_cam_body`
     (cam body 원점을 base 로). 화면(optical)에 base 원점을 그리려면 `T_optical_base` 가 필요:
     `T_optical_base = inv(T_BODY_OPTICAL) @ inv(base_T_cam)`.
     `rvec = cv2.Rodrigues(T_optical_base[:3,:3])[0]`, `tvec = T_optical_base[:3,3]`.
     `cv2.drawFrameAxes(bgr, K, None, rvec, tvec, args.axis_len)`.
   - HUD 텍스트(선택, 가벼움): serial/이름, "base origin", 측정 방식(measured/from-yaml).
   - `--save-frame` 이면 매 프레임 마지막 프레임을 보관. imshow 가능하면 `cv2.imshow(...)` +
     `cv2.waitKey(1)`; `q`/ESC 로 이 카메라 종료(다음 대 or 전체 종료).
5. `zed.close()`. 순차 모드면 다음 serial 로. 헤드리스(`--save-frame` 만, DISPLAY 없음)면
   imshow 대신 `--warmup` 만큼만 돌고 마지막 프레임을 저장 후 종료(measure_base_cam 의 헤드리스
   가드와 동일한 판단).

## 참고해야 할 것 (왜 보는지 함께)

- `scripts/measure_base_cam.py` — `open_camera`/`camera_matrix`/`make_detector`/`parse_serial_map`/
  `child_frame`/`DEFAULT_SERIAL_MAP`/`COORD`/`UNIT` 를 그대로 import 재사용. 측정 게이팅 로직
  (`--max-reproj`, `--ambiguity-ratio`, 화이트리스트, 유한값)의 **정확한 기준**과 `measure_camera`
  의 프레임 처리 순서(BGRA→GRAY, `detectMarkers`, `pnp_cam_optical_T_marker` 두 해)를 그대로 따른다.
- `scripts/aruco_cube_datum.py` — `T_BODY_OPTICAL`(optical↔body), `base_T_cam_from_marker`,
  `average_poses`, `_quat_to_mat`(from-yaml 복원). 이 파일의 프레임 규약을 벗어나지 말 것.
- `logs/base_cube_datum.example.json` — `--datum` 입력 스키마(coordinate_system/unit/dictionary/
  tag_size_m/markers). 사용자 실파일이 없을 때의 형식 참조.
- PLAN06 산출 yaml `logs/base_cam_extrinsics.yaml` — `--from-yaml` 복원 대상. `transforms` 리스트의
  parent/child/translation/rotation_quat 포맷. (measure_base_cam `write_extrinsics` 가 만드는 형식.)

## 신경써야 할 것 (가드레일)

- **검증된 런타임 변경 금지**: `measure_base_cam.py`·`aruco_cube_datum.py`·`zed_fusion_viz.py`·
  `zed_fusion_bodytrack.py`·`zed_make_fusion_config.py`·`run_fusion.py`·`aruco_zed_test.py` **수정
  없음.** 이들에서 **import 만** 한다. 새 파일 `scripts/base_tf_live.py` 하나만 생성.
- **프레임 변환 정확성(핵심)**: base_T_cam 은 body(Z-up) 프레임의 `T_base_cam_body`. 화면 그리기는
  optical 프레임이므로 반드시 `T_optical_base = inv(T_BODY_OPTICAL) @ inv(base_T_cam)` 로 변환해서
  `drawFrameAxes` 에 넘긴다. optical↔body 를 빠뜨리면 축이 90°씩 틀어져 그려진다.
- **측정 게이트를 새로 발명하지 말 것**: 재투영오차·IPPE 모호성·ID 화이트리스트 기준은 PLAN06 과
  동일하게(같은 상수·같은 부등호). 값 게이트(NaN/inf pose 제외)도 유지.
- **distortion=0**: rectified `retrieve_image(LEFT)` + `camera_matrix`(raw 아님). `drawFrameAxes`
  의 distCoeffs 는 `None`.
- **HD720@30 / 카메라 한 대씩**: 해상도·fps 는 `open_camera` 기본을 그대로 쓴다. 동시 2대 open
  금지(순차만). `--serial` 미지정 시에도 순차.
- **`logs/**` 기존 파일 수정 금지**: 전부 읽기 전용. `--save-frame` 은 사용자가 지정한 경로에만 쓰고
  기본값 없음(실수로 logs 를 덮지 않게).
- **헤드리스 가드**: DISPLAY 없고 `--save-frame` 도 없으면 명확한 에러/안내로 종료(measure_base_cam
  의 preview 가드와 같은 톤). imshow 를 무조건 호출해 죽지 않게.
- **샌드박스 한계**: codex 는 카메라·GPU·디스플레이가 없어 라이브 실행 불가. 정적 검증
  (`py_compile`, `--help`, from-yaml/헤드리스 분기의 인자 파싱)까지만. **라이브 육안 확인은 사용자.**

## 코드 스타일 (사용자 요청 — "AI 티 안 나게")

PLAN06 산출물(`measure_base_cam.py`) 과 **같은 결**로 쓴다. 표면(주석·레이아웃·네이밍)에만
적용하고 정확성 가드레일은 타협하지 않는다.

- 주석은 **한국어로 "왜"** 를 설명한다(줄마다 기계적으로 되풀이 금지). 프레임 변환처럼 헷갈리는
  지점에만 개념 메모를 단다.
- 논리 국면이 바뀌면 **빈 줄**로 끊는다. 과한 docstring(`Args:/Returns:/Raises:`) 금지 — 짧은 한
  줄 주석으로 대체. 타입힌트는 도움되는 곳만 가볍게.
- 과설계 금지: 불필요한 클래스/추상화, 모든 줄을 감싸는 방어적 try/except 지양. 절차를 위에서
  아래로 곧게. 이모지·장식 구분선·과장 로그 금지. 네이밍은 짧고 실용적으로(`T`, `q`, `K`, `bgr`).
- 파일 상단은 `#!/usr/bin/env python3` + `# -*- coding: utf-8 -*-`.

## 이번에는 하지 않는 것 (non-scope)

- **fusion_world 축 그리기 / 스켈레톤을 base 프레임으로 변환해 표시**. base 원점 축만. (다음 plan.)
- **매 프레임 재측정**(트래킹). 카메라 고정 가정이라 시작 1회 측정으로 충분.
- **SVO 재생·오프라인 로그 오버레이**. 라이브(또는 `--from-yaml` + 라이브)만.
- **두 대 동시 open / 다창 동시 표시**. USB 1컨트롤러 제약상 순차만.
- **ROS2 연동**(토픽/TF 발행). 이 뷰어는 화면 확인 전용, ROS2 import 없음.
- **기존 스크립트 수정·측정 게이트 튜닝·ArUco 파라미터 변경**.

## 근거

- 사용자와 확정: 카메라·큐브 고정 → 시작 1회 측정 후 고정, 라이브로 base 축이 실제 위치에 맞는지
  육안 확인, RViz2 대신 `imshow`.
- PLAN06 이 이미 base_T_cam 측정·프레임 변환·측정 게이트를 검증된 형태로 제공 → 이 뷰어는 그
  자산을 import 재사용하고 "라이브 루프 + drawFrameAxes 오버레이"만 새로 얹는다(중복 구현 없음).

## 검증

**정적 (codex, 샌드박스에서 가능):**
- `python3 -m py_compile scripts/base_tf_live.py` 통과.
- `python3 scripts/base_tf_live.py --help` 가 모든 옵션을 노출.
- import 경로 확인: `aruco_cube_datum`·`measure_base_cam` 에서 재사용하는 심볼이 실제로 존재하는지
  (오타/시그니처 불일치 없이) `python3 -c "import ..."` 수준으로 확인.
- (가능하면) 합성 base_T_cam·K 로 `T_optical_base` 조합과 `cv2.Rodrigues`/`drawFrameAxes` 인자
  shape 가 맞는지 최소 단위 확인(하드웨어 없이 numpy/cv2 만으로).

**라이브 (사용자, conda `zed` env + 하드웨어):**
- `python3 scripts/base_tf_live.py --serial 13870389` → warmup 동안 큐브를 비추면 측정 후,
  라이브 영상에 base 좌표축이 뜬다. **축 원점이 실제 큐브(마커1) 중심에, +X 가 큐브 정면, +Z 가
  위로 향하는지** 눈으로 확인.
- 카메라를 큐브에서 떨어뜨려도(큐브 치워도) 축이 그 자리에 고정돼 화면에 남는지 확인(고정 검증).
- `--from-yaml logs/base_cam_extrinsics.yaml --serial 13870389` → 큐브 없이도 저장값으로 같은 축이
  뜨는지, warmup 측정과 위치가 일치하는지 비교.
- (판정) 축 방향이 상식과 맞는가. 어긋나면 optical↔body 변환/부호 오류가 여기서 드러난다.

## 다음 단계

- 축 정합이 확인되면: **fusion_world 축**과 **라이브 스켈레톤(BODY_34)을 base 프레임으로 변환해
  같은 화면(또는 3D 뷰)에 오버레이**하는 확장. base_T_cam·base_T_world 는 이미 있으므로 변환 한 번.
- 이 뷰어를 PLAN06 라이브 검증 절차(`measure_base_cam` 직후)에 붙여, 측정 결과를 즉시 눈으로
  확인하는 루틴으로 사용.
