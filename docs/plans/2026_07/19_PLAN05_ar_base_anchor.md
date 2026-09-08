---
date: 2026-07-19
task: AR 태그로 fusion world → robot base 앵커(base_T_world) 1회 산출 + 오프라인 base 프레임 재표현
planner: Claude
executor: codex
status: draft
---

# PLAN05 — AR 태그 base 앵커 + base 프레임 재표현

> 파일: `docs/plans/2026_07/19_PLAN05_ar_base_anchor.md` (식별자 = PLAN05).

## 한 줄 결론

로봇 베이스에 **CAD로 위치를 아는 AR 태그**를 붙이고, ZED 캘브 직후 그 태그를 검출해
**`base_T_world`(fusion world → robot base) 4×4 를 1회 산출**해 파일로 저장한다. 이후엔 융합
스켈레톤(BODY_34)에 이 상수 행렬을 곱하기만 하면 **robot base 프레임의 human pose** 가 나온다.
카메라는 캘브 후 안 움직이므로 앵커는 그 세션 내내 유효하다. **기존 검증된 스크립트는 안 건드리고
새 파일 3개만 추가한다.**

## 왜 이 plan 이 필요한가

최종 목표는 CBF 안전층에 넣을 **robot base 기준 human pose** 다. 현재 파이프라인은 human 을
**fusion world**(ZED360 캘리브가 정의하는 프레임)로만 낸다. 이 둘을 잇는 변환
`base_T_world` 를 구하는 게 이 plan 이다.

사용자 결정(대화로 확정): **hand-eye 다자세 캘리브는 하지 않는다.** 태그를 로봇 베이스의 **알려진
자리**에 고정하고 `base_T_tag` 를 **설계파일(CAD)에서 뽑은 고정 상수**로 명시하면, 태그 검출 한 번으로
`base_T_world` 가 나온다. 이게 이 리그·이 로봇(PiPER)에 맞는 최소 복잡도 경로다.

## 지금까지 이어진 맥락 (이 plan 만 읽어도 되게 재서술)

프레임 표기: `T_A_B` = B 좌표의 점을 A 좌표로 보냄 (`p_A = T_A_B · p_B`).

1. **fusion world 프레임의 정체** (실측·공식문서 확인):
   ZED360 은 **원점 = 첫 로드 카메라 바로 아래 바닥, Z=중력반대, X=그 카메라 yaw**, 그리고
   **yaw + 병진만 캘리브**(roll/pitch 는 IMU). 우리 실측 `logs/fusion_zed360.json` 에서
   카메라 `13870389` 의 world pose 가 `RIGHT_HANDED_Z_UP_X_FWD` 로 `[0,0,+0.675]`·회전 단위행렬
   (= 기준 카메라), `19321109` 는 `[1.296,−1.756,0.572]`. baseline 2.18 m.
2. **config JSON 이 곧 출력 프레임.** `read_fusion_configuration_file(path, COORD, UNIT)` 가
   각 카메라의 **world_T_cam** 을 요청한 COORD 로 변환해 준다. 손으로 JSON 파싱 금지(SDK 5.4 실파일
   포맷은 문서와 다름 — `pose` 가 4×4 flat 문자열).
3. **human 은 fusion world 로 나온다.** `zed_fusion_bodytrack.py` 의 JSONL 레코드는
   `frame:"fusion_world"`, `kp`(관절별 [x,y,z] 리스트), `kp_conf`, `joints`(name→{xyz,conf}),
   선택적 `position`, `t_ns`, `id` 등. 좌표계 `RIGHT_HANDED_Z_UP_X_FWD` / METER.
4. **SDK 에 마커 검출 없음** → OpenCV `cv2.aruco` 를 직접 쓴다. `retrieve_image()` 는
   **rectified/undistorted** → solvePnP 에 **distortion=0**. intrinsic 은
   `camera_information.camera_configuration.calibration_parameters.left_cam`(fx,fy,cx,cy).
5. **좌표계 함정**: solvePnP 결과는 **OpenCV/IMAGE 프레임**(X우·Y하·Z전). 프로젝트 표준은
   `RIGHT_HANDED_Z_UP_X_FWD`(X전·Y좌·Z상). 이 변환을 빠뜨리면 조용히 틀어진다. 고정 행렬:
   `R_zup_img = [[0,0,1],[−1,0,0],[0,−1,0]]` (det=+1). ⚠️ 이 변환이 ZED 카메라 프레임 규약과
   정확히 맞는지는 **정적으로 100% 확증 불가** → §검증의 라이브 항목으로 사용자가 확인한다.

## 지금 기준 판단

- **새 파일 3개**로 끝낸다. 검증된 런타임(`zed_fusion_viz.py`, `zed_fusion_bodytrack.py`,
  `zed_make_fusion_config.py`, `run_fusion.py`)은 **불변**.
- 순수 수학은 별도 모듈로 분리해 **하드웨어 없이 정적 검증**(합성 입력) 가능하게 한다.
- 태그 자세는 **6-DOF 단일 태그**로 뽑되(사용자 방식), flip 파국을 막는 **공짜 안전장치**
  (IPPE 두 해 + 재투영오차 게이팅)만 넣는다. 위치-only/다태그 Kabsch 는 이번 범위 밖(정확도가
  부족하다고 판명되면 다음 plan).
- 앵커 산출(라이브, 카메라 필요)과 재표현(오프라인, 정적 검증 가능)을 **분리**한다.

## 이번에 할 것

1. `scripts/base_frame.py` (신규) — 순수 변환 라이브러리(정적 검증 대상).
2. `scripts/ar_base_anchor.py` (신규) — 라이브 앵커 산출 도구(사용자 검증).
3. `scripts/rebase_pose_log.py` (신규) — 오프라인 JSONL 재표현(정적 검증 대상).
4. `logs/base_t_tag.example.json` (신규) — `base_T_tag` 상수 입력 템플릿.

## 구현해야 할 것 (파일 단위)

### (A) 신규 `scripts/base_frame.py` — 순수 변환 라이브러리
pyzed 의존 없이(가능하면 numpy 만) 아래 함수를 제공. 전부 `RIGHT_HANDED_Z_UP_X_FWD`/METER 기준.

- `R_ZUP_IMG` 상수: `np.array([[0,0,1],[-1,0,0],[0,-1,0]], float)`. 4×4 버전 `T_ZUP_IMG` 도.
- `load_base_t_tag(path) -> dict`: `base_t_tag.json`(또는 example) 을 읽어
  `{tag_id: (4×4 np.array base_T_tag), ...}`, `tag_size_m`, `dictionary` 를 돌려준다.
  입력 포맷은 태그별 `translation_m`(x,y,z) + `rpy_deg`(roll,pitch,yaw) 또는 `matrix`(16 float).
  rpy→행렬은 `zed_make_fusion_config.py` 와 **같은 순서/규약(intrinsic ZYX, degrees)** 을 쓴다.
- `cam_t_tag_from_pnp(corners_px, tag_size_m, K) -> list[(4×4, reproj_err)]`:
  `cv2.solvePnPGeneric(objp, corners, K, None, flags=cv2.SOLVEPNP_IPPE_SQUARE)` 로 **두 해**와
  각 재투영오차를 얻어 재투영오차 오름차순 리스트로 반환. `objp` 는 태그 중심 원점, 한 변
  `tag_size_m` 의 4 코너(OpenCV aruco 코너 순서와 일치). distortion=None(=0).
  결과는 **IMAGE/OpenCV 프레임**의 `cam_T_tag`.
- `imgframe_to_zup(T_img) -> T_zup`: 카메라 optical(IMAGE) 프레임에서 표현된 `cam_T_tag` 를
  ZED Z_UP 카메라 프레임 기준으로 변환. `T_zup = T_ZUP_IMG @ T_img` (카메라 프레임 기저변환).
- `world_t_tag(world_t_cam, cam_t_tag_zup) -> 4×4`: `world_T_cam @ cam_T_tag`.
- `base_t_world(base_t_tag, world_t_tag) -> 4×4`: `base_T_tag @ inv(world_T_tag)`.
- `apply_T(T, xyz) -> [x,y,z]`: 동차변환. **비유한값(NaN/inf)은 그대로 통과**(변환하지 않음).
- `rebase_record(record, T, new_frame="robot_base") -> dict`: record 사본을 만들어
  `frame` 교체, `kp`(리스트) 각 점 · `joints[*].xyz` · 존재 시 `position` 에 `apply_T` 적용.
  `kp_conf`/`joints[*].conf`/기타 필드는 불변.
- `average_poses(list_of_4x4) -> 4×4`: 병진은 중앙값, 회전은 **쿼터니언 평균(Markley: M=Σqqᵀ 의
  최대고유벡터)**. (회전 평균 유틸은 자체 구현 또는 scipy 있으면 사용 — 없으면 numpy eig.)

### (B) 신규 `scripts/ar_base_anchor.py` — 라이브 앵커 산출
- CLI:
  - `--config PATH`(기본 `logs/fusion_zed360.json`) — fusion config(= world_T_cam 원천).
  - `--base-tag PATH`(기본 `logs/base_t_tag.json`) — `base_T_tag` 상수 + tag_size + dictionary.
  - `--out PATH`(기본 `logs/base_anchor.json`) — 산출 앵커.
  - `--frames N`(기본 60) — 평균낼 프레임 수. `--max-reproj PX`(기본 1.0) — 재투영오차 게이트.
  - `--ambiguity-ratio R`(기본 0.3) — IPPE 2해의 재투영오차 비(err0/err1)가 R 초과면(=두 해가
    비슷 = 모호) 그 프레임 **폐기**.
  - `--preview`(디스플레이 필요) — 검출 태그·좌표축을 창에 그려 확인.
    `--save-debug PATH`(헤드리스) — 주석 이미지 1장 저장. **앵커 숫자를 믿기 전 검출·축 확인용.**
- 흐름:
  1. `read_fusion_configuration_file(config, RIGHT_HANDED_Z_UP_X_FWD, METER)` 로 각 serial 의
     `world_T_cam` 획득. `load_base_t_tag(base-tag)` 로 상수 획득.
  2. 카메라를 **한 대씩 순차 open**(USB 컨트롤러 1개라 동시 스트리밍은 상한 — 정적 태그니
     한 대 열어 N프레임 잡고 닫고 다음 대. `zed_check.py` 패턴). **`depth_mode = NONE`**
     (ArUco PnP 는 태그 크기+intrinsic 만 쓰는 monocular라 ZED depth 불필요 — GPU·대역 절약).
     `camera_disable_self_calib=True` 로 intrinsic 고정. **연 해상도(HD720) 기준**
     `calibration_parameters.left_cam` 에서 K 구성(`_raw` 아님, distortion=0).
     이미지는 **`retrieve_image(LEFT)`**(rectified) → `get_data()`(BGRA) → **GRAY 변환** 후 검출.
  3. `--frames` 동안: 각 카메라 프레임에서 ArUco 검출(`cv2.aruco.ArucoDetector`, dictionary 는
     `base_t_tag.json` 의 `dictionary` 사용). **ID 화이트리스트**: `base_t_tag.json` 의 `tags[].id`
     에 없는 검출은 **폐기**(false-positive 방어의 핵심). 통과 태그마다
     `cam_t_tag_from_pnp` → 게이트(재투영오차·모호성) 통과분만 채택 →
     `imgframe_to_zup` → `world_t_tag = world_T_cam · cam_T_tag` → `base_t_world = base_T_tag ·
     inv(world_T_tag)`. serial·tag_id 별로 base_T_world 후보 수집.
  4. **교차검증**: 서로 다른 (serial,tag) 조합이 낸 base_T_world 들의 병진 편차(mm)·회전 편차(deg)를
     리포트. `average_poses` 로 최종 base_T_world 산출.
  5. `--out` 에 저장: `base_T_world`(4×4 row-major), `coordinate_system`, `unit`,
     사용한 tag_id·serial 목록, 프레임 수, 채택/폐기 수, 교차검증 편차, `t_ns`(system 아님 —
     `sl` 타임스탬프 사용), note. **`logs/**` 의 기존 파일은 수정하지 않고 새 파일만 생성.**
- 카메라를 1대만 열어도 동작해야 한다(단일 카메라가 태그를 보면 그 카메라 기준으로 산출). 2대면
  교차검증까지.

### (C) 신규 `scripts/rebase_pose_log.py` — 오프라인 재표현 (하드웨어 불필요)
- CLI: `--in PATH`(fusion JSONL), `--anchor PATH`(기본 `logs/base_anchor.json`),
  `--out PATH`, `--keep-world`(플래그; 주면 world 레코드도 함께 기록, 기본은 base 만).
- 흐름: 앵커에서 `base_T_world` 로드. `--in` 을 줄 단위로 읽어 `frame=="fusion_world"` 레코드마다
  `rebase_record(rec, base_T_world, "robot_base")` 를 `--out` 에 기록(`--keep-world` 면 원본도).
  `source=="camera"`(raw) 레코드는 fusion world 가 아니므로 **변환하지 않고** 통과(또는 스킵) —
  기본 스킵, 명확히 로그.
- meta: 입력 meta json 이 있으면 참고만. 출력은 새 JSONL + 간단한 `_meta` 옆파일(앵커 경로,
  `frame:"robot_base"`, coord/unit, 변환/스킵 카운트).

### (D) 신규 `logs/base_t_tag.example.json` — 입력 템플릿
```json
{
  "coordinate_system": "RIGHT_HANDED_Z_UP_X_FWD",
  "unit": "METER",
  "dictionary": "DICT_5X5_100",
  "tag_size_m": 0.10,
  "tags": [
    { "id": 0, "translation_m": [0.0, 0.0, 0.0], "rpy_deg": [0.0, 0.0, 0.0],
      "note": "CAD 설계값으로 교체할 것 — 로봇 base 원점 기준 태그 중심 pose" }
  ]
}
```
사용자가 `logs/base_t_tag.json` 로 복사해 CAD 값을 채운다(코드는 실제 파일을 입력으로 받음).

## 참고해야 할 것 (왜 보는지 함께)

- `scripts/zed_fusion_bodytrack.py` L96–115 `_body_record` — **JSONL 레코드 스키마**
  (`frame/kp/kp_conf/joints/position`) 확인. rebase 가 정확히 이 필드를 변환해야 한다.
- `scripts/zed_make_fusion_config.py` — `read/write_configuration_file` 사용법, rpy→Transform
  규약(`set_euler_angles(roll,pitch,yaw,True)`), COORD/UNIT 상수. `base_frame.py` 의 rpy 규약을
  여기와 일치시킨다.
- `logs/fusion_zed360.json` — world_T_cam 원천(읽기만, 수정 금지). serial 키·pose 형식 확인.
- ZED aruco 공식 샘플(`stereolabs/zed-aruco`, C++) — intrinsic·rectified 이미지로 PnP 하는 흐름의
  근거(포팅이 아니라 개념 참고).

## 신경써야 할 것 (가드레일)

- **검증된 런타임 변경 금지**: `zed_fusion_viz.py`/`zed_fusion_bodytrack.py`/
  `zed_make_fusion_config.py`/`run_fusion.py` 수정 없음. **새 파일만.**
- **카메라 소유권 = 순서 강제**: ZED 카메라는 **한 프로세스만** 열 수 있다. 앵커 도구와 Fusion 이
  동시에 카메라를 잡을 수 없으므로, 실행 순서는 **ZED360 → `ar_base_anchor`(열고 검출·저장·닫기)
  → Fusion**. 앵커 도구는 반드시 카메라를 **닫고 종료**해야 Fusion 이 열 수 있다. 이 사이에
  카메라가 안 움직이므로 `base_T_world` 는 그 세션 내내 유효. (자동 연결은 다음 plan.)
- **`logs/**` 기존 파일 수정 금지**: 앵커/재표현 출력은 **새 파일**로만 쓴다(`base_anchor.json`,
  재표현 JSONL). `fusion_zed360.json` 등은 읽기 전용.
- **좌표계 일관성**: 전 구간 `RIGHT_HANDED_Z_UP_X_FWD`/METER. solvePnP(IMAGE)→ZUP 변환을
  `imgframe_to_zup` 한 곳에서만 처리하고, 그 외 어디서도 프레임을 섞지 않는다.
- **distortion=0**: rectified `retrieve_image(LEFT)` + `calibration_parameters`(raw 아님).
- **`base_T_world` 는 좌곱 상수**: human 은 fusion world 로 나오므로 `p_base = base_T_world · p_world`.
  절대 `world_T_base` 와 혼동하지 말 것(앵커 파일에 방향을 명시적으로 기록).
- **비유한 keypoint 보존**: 누락 관절(NaN/inf)을 변환해 가짜 좌표로 만들지 말 것.
- **시간·난수 주의**: 파일명 타임스탬프가 필요하면 `sl` 카메라 타임스탬프를 쓴다.
- **BODY_34 인덱스 불변**: rebase 는 좌표만 바꾸고 관절 인덱스/순서/이름을 건드리지 않는다.
- **샌드박스에 카메라·GPU·로봇 없음**: codex 는 (B) 를 라이브 실행 불가. (A)(C)(D) 는
  합성 입력으로 정적 검증. (B) 는 `py_compile`+`--help`+분기 로직까지. **라이브는 사용자 `zed` env.**
- **flip 안전장치는 필수**: 단일 태그 6-DOF 라 정면·원거리에서 자세가 뒤집힐 수 있다. IPPE 두 해
  재투영오차 게이팅(`--ambiguity-ratio`)을 반드시 넣는다(공짜 방어).
- **마커·크기 확정**: 부스 2.5×2.5 m → 태그-카메라 최대 거리 **≤1.3m**. **100mm 태그**를 쓴다.
  100mm 는 1.3m 에서 대략 **38~54px**(f≈500~700px, 실제는 `left_cam.fx` 로 확인) — 검출 임계
  (32~40px) 위라 원단에서도 안정적. dictionary 는 **`DICT_5X5_100`**(cv2.aruco 네이티브).
  ID 화이트리스트로 false-positive 를 막으므로 AprilTag 는 불필요. 크기/딕셔너리 변경 시
  `base_t_tag.json` 과 테스트 스크립트 상수만 수정.

## 이번에는 하지 않는 것 (non-scope)

- **라이브 뷰어/로거에 base 프레임 출력 배선**(검증된 런타임이라 별도 plan). 이번엔 오프라인 재표현까지.
- **PiPER SDK 연동 / TCP 터치 프로빙으로 `base_T_tag` 교차검증**(다음 단계 검증). 이번엔
  `base_T_tag` 를 CAD 상수로 신뢰.
- **hand-eye 다자세, 위치-only 다태그 Kabsch, tag bundle 맵**(정확도 부족 판명 시 다음 plan).
- **ε(t) 모델링, CBF, ROS2 노드화.**
- `base_T_tag` 자체의 정확도 평가(로봇 실측 필요).

## 근거

- 대화로 확정: 카메라는 캘브 후 고정 → `base_T_cam`(정확히는 `base_T_world`)은 1회 상수 →
  이후 human 은 행렬곱 한 번. hand-eye 불필요(`base_T_tag` 를 CAD 로 알기 때문).
- `docs/robot_base_registration.md`(설계) / `..._research.md`(원자료)에 프레임·SDK·정확도 근거.
  핵심 사실은 위 "맥락"에 재서술함(codex 는 이 plan 전문만 받으므로).

## 검증

**정적 (codex, 샌드박스에서 가능):**
- `python3 -m py_compile scripts/base_frame.py scripts/ar_base_anchor.py scripts/rebase_pose_log.py` 통과.
- `--help` 3종 노출 확인.
- **`base_frame.py` 자체 라운드트립 테스트**(스크립트 하단 `if __name__=="__main__"` 또는 별도
  `--selftest`): 임의 `base_T_tag`·`world_T_cam` 를 정하고, 그로부터 태그 4코너를 카메라에 투영해
  합성 `corners_px` 생성 → `cam_t_tag_from_pnp`→`imgframe_to_zup`→`world_t_tag`→`base_t_world` 가
  **입력 `base_T_world` 를 mm/deg 오차 내로 복원**하는지 assert. (프레임 로직의 정적 증명.)
- `rebase_pose_log.py` 를 **합성 fusion JSONL 픽스처**(몇 줄, fusion_world 레코드)와 항등
  앵커(base_T_world=I)로 돌려 출력이 입력 좌표와 동일한지, 그리고 알려진 평행이동 앵커로
  좌표가 정확히 그만큼 이동하는지 확인.
- 잘못된 입력(앵커 없음/태그 config 누락) 시 명확한 에러.

**라이브 (사용자, `zed` env, 하드웨어):**
- 로봇 base 의 알려진 자리에 태그 부착 → `logs/base_t_tag.json` 에 CAD 값 기입 →
  `run_fusion.py` 로 ZED360 캘브 후 `ar_base_anchor.py` 실행 → `base_anchor.json` 생성,
  교차검증 편차(2대) 확인.
- 기록된 fusion JSONL 을 `rebase_pose_log.py` 로 재표현 → base 프레임에서 human 이 **로봇 대비
  물리적으로 맞는 위치**에 오는지 확인. **좌표계 변환(§맥락 5)이 맞는지 여기서 판정.**
- (권장) 태그 앞에 사람이 서서 손목이 로봇 base 기준 기대 좌표 근처인지 눈으로 대조.

## 다음 단계

- 좌표·정확도 확인되면: **`run_fusion.py` 에 앵커 단계 삽입**(ZED360 → 앵커 → Fusion 자동화) +
  **라이브 뷰어/로거에 base 프레임 출력 배선**(별도 plan) → JSONL 에 `robot_base` 프레임을 실시간 병기.
- **PiPER FK / TCP 터치로 `base_T_world` 교차검증** → 반복도 표준편차를 ε(t) 상수항으로.
- 정확도 부족 시: 위치-only 다태그 Kabsch 로 업그레이드(설계문서 §6).
