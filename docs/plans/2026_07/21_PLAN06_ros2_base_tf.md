---
date: 2026-07-21
task: ArUco 정육면체 데이텀(마커 0/1/2)으로 base(=마커1) 기준 ZED 2대 6-DOF pose를 1회 측정해, ROS2 static TF(base→zed_link×2 + base→fusion_world)로 발행
planner: Claude
executor: codex
status: done
---

# PLAN06 — ArUco 큐브 데이텀 → base 프레임 static TF (ROS2)

> 파일: `docs/plans/2026_07/21_PLAN06_ros2_base_tf.md` (식별자 = PLAN06).

## 한 줄 결론

로봇 셀에 세워진 **ArUco 정육면체(마커 0/1/2, 세 면 90°)**를 각 ZED가 검출해, **base(=마커1)
기준 카메라 2대의 6-DOF pose**를 1회 측정한다. 결과를 **좌표 상수 파일(yaml)**로 저장하고, 그
파일을 읽어 **ROS2 `static_transform_publisher`**가 `base→zed1_link`, `base→zed2_link`,
`base→fusion_world`를 발행한다. 측정(pyzed+CUDA)과 발행(ROS2, CUDA無)은 **프로세스가 완전히
분리**되어 파일로만 이어진다 → conda/ROS2/CUDA 충돌 지점이 없다. **기존 검증된 스크립트는
안 건드리고 새 파일만 추가한다.**

## 왜 이 plan 이 필요한가

ROS2 TF 트리의 뿌리를 놓는 작업이다. base 프레임(로봇 셀에 고정된 ArUco 큐브) 기준으로 두 ZED가
어디에 어떻게 놓였는지를 TF 엣지로 박아두면, 이후 다운스트림 좌표 변환은 tf2가 자동 합성한다.
카메라와 큐브가 고정이라 이 변환은 **static** — 1회 측정 후 상수로 발행하면 된다.

**분리 아키텍처(사용자와 확정)**: ZED SDK는 카메라 open 만으로도 CUDA를 강제하고(depth 꺼도
동일), conda(pyzed)와 apt-ROS2를 한 셸에 섞으면 PATH/PYTHONPATH·numpy 버전이 충돌한다(ROS2 공식
문서·Stereolabs 지원팀이 "별도 프로세스로 하라"고 명시). 그래서 **측정 도구는 conda `zed` env 에서
pyzed 로 돌고 ROS2 를 전혀 import 하지 않으며**, **ROS2 launch 는 시스템 apt Humble 에서 상수만
발행**한다. 둘의 유일한 접점은 측정 결과 **yaml 파일 하나**다.

## 지금까지 이어진 맥락 (이 plan 만 읽어도 되게 재서술)

프레임 표기: `T_A_B` = B 좌표의 점을 A 좌표로 보냄 (`p_A = T_A_B · p_B`).

1. **하드웨어/환경**: ZED-M 2대 (S/N `13870389`=zed1, `19321109`=zed2), SDK 5.4, pyzed 는 conda
   `zed` env(Python 3.10), Ubuntu 22.04, ROS2 Humble(시스템 apt). USB 컨트롤러 1개 → 카메라는
   **동시에 한 대씩만** 여는 게 안전(`scripts/zed_check.py` 패턴).
2. **좌표계 통일**: 전 구간 `RIGHT_HANDED_Z_UP_X_FWD` / METER (X=전방, Y=좌, Z=상).
   이건 **ROS REP-103 과 동일**하므로 측정 숫자가 ROS2 TF 로 **변환 없이 그대로** 들어간다.
3. **base 프레임 정의(사용자·CAD 확정)**: 원점 = 마커 **1** 중심, **+X = 마커1 정면(법선)**,
   **+Z = 위(프로파일 수직)**, **+Y = 왼쪽**. 마커는 각 면 **정중앙**에 **정립(태그 위쪽 변 = +Z)**
   부착. 정육면체 겉면 한 변 **101mm → 반 변 0.0505m**. 세 면 배치:
   | 마커 | 면(법선, base축) | 중심 위치(base, m) | 태그 위쪽 |
   |---|---|---|---|
   | 1 | +X (정면) | `[0, 0, 0]` | +Z |
   | 2 | +Y (왼쪽) | `[-0.0505, +0.0505, 0]` | +Z |
   | 0 | −Y (오른쪽) | `[-0.0505, -0.0505, 0]` | +Z |
   딕셔너리 `DICT_5X5_100`, 태그 한 변(검은 사각형) **0.10m**.
4. **검출 원천 코드(재활용)**: `scripts/aruco_zed_test.py` 가 이미
   `retrieve_image(LEFT)`(rectified) → `cv2.aruco` 검출 → `cv2.solvePnP(..., SOLVEPNP_IPPE_SQUARE)`
   로 `optical_T_marker` 를 뽑는다. intrinsic 은 `calibration_parameters.left_cam`(rectified,
   **distortion=0**). 이 흐름을 그대로 쓴다.
5. **fusion world 원천**: `logs/fusion_zed360.json` 을
   `sl.read_fusion_configuration_file(path, RIGHT_HANDED_Z_UP_X_FWD, METER)` 로 읽으면 각 serial 의
   `world_T_cam`(Z-up 카메라 프레임)을 얻는다. 손 파싱 금지(SDK 5.4 실파일 포맷이 문서와 다름).
6. **프레임 변환 상수**: solvePnP 는 **optical 프레임**(X우·Y하·Z전), 프로젝트/ROS 는 **body 프레임**
   (X전·Y좌·Z상). 둘은 **원점 공유, 고정 회전**만 다르다:
   `R_body_optical = [[0,0,1],[-1,0,0],[0,-1,0]]` (det=+1). optical→body 변환
   `T_body_optical = [[R_body_optical, 0],[0, 1]]`.

## 지금 기준 판단

- **측정(pyzed) ↔ 발행(ROS2) 프로세스 완전 분리**, 접점은 yaml 파일뿐. ROS2 쪽엔 pyzed/CUDA/conda
  없음.
- 세 마커 **중심 3점만으로 회전을 풀지 않는다**(큐브라 중심들이 몰려 있어 yaw 지렛대가 짧음).
  대신 **각 마커의 solvePnP 자세를 직접** 쓰고, 카메라가 여러 면을 보면 **여러 후보를 평균**한다.
- 카메라 프레임은 전 계산을 **body(Z-up) 프레임**으로 통일한다(solvePnP optical 결과를 즉시
  `T_body_optical` 로 변환). 그래야 ZED360 의 `world_T_cam`(Z-up)과 프레임이 일치해
  `base_T_world` 가 깔끔히 합성된다.
- 순수 수학은 별도 모듈로 분리해 **하드웨어 없이 정적 검증**(합성 입력)한다.
- static TF 는 latch(transient_local)가 원칙이나 DDS 타이밍 버그 이력이 있어, launch 에서
  **publisher 노드를 계속 띄워둔다**(상수만 쏘는 거라 비용 0).

## 이번에 할 것

1. `scripts/aruco_cube_datum.py` (신규) — 순수 변환 라이브러리(정적 검증 대상).
2. `scripts/measure_base_cam.py` (신규) — 라이브 측정 도구(pyzed, 사용자 검증). yaml 산출.
3. `logs/base_cube_datum.example.json` (신규) — base_T_marker 데이텀 입력 템플릿(위 §3 값 기입).
4. `ros2_ws/src/cbf_base_tf/` (신규 ROS2 ament_python 패키지) — yaml 을 읽어 static TF 발행.

## 구현해야 할 것 (파일 단위)

### (A) 신규 `scripts/aruco_cube_datum.py` — 순수 변환 라이브러리
pyzed 의존 없이(numpy + cv2 만) 아래를 제공. 전부 `RIGHT_HANDED_Z_UP_X_FWD`/METER.

- 상수 `R_BODY_OPTICAL = np.array([[0,0,1],[-1,0,0],[0,-1,0]], float)`, 4×4 `T_BODY_OPTICAL`.
- `load_datum(path) -> {marker_id: T_base_marker(4×4), ...}, tag_size_m, dictionary`:
  입력은 마커별 `center_m`([x,y,z]) + `normal`(태그 법선, base축 단위벡터) + `up`(태그 위쪽,
  base축 단위벡터). 이로부터 마커의 **PnP object-point 프레임(X=right, Y=up, Z=normal)** →
  base 회전을 구성: `Z_m = normal`, `Y_m = up`, `X_m = cross(up, normal)`,
  `R_base_marker = [X_m | Y_m | Z_m]`(열벡터). `T_base_marker = [[R, center],[0,1]]`.
  `normal`·`up` 은 정규직교여야 하며 아니면 명확한 에러.
- `object_points(tag_size_m) -> 4×3`: `aruco_zed_test.make_object_points` 와 **동일 코너 순서**
  (top-left, top-right, bottom-right, bottom-left). 값은 재구현(그 파일 import 하지 말 것 — pyzed
  끌려옴). 검은 사각형 한 변 기준.
- `pnp_cam_optical_T_marker(corners_px, tag_size_m, K) -> list[(4×4, reproj_err)]`:
  `cv2.solvePnPGeneric(objp, corners, K, None, flags=cv2.SOLVEPNP_IPPE_SQUARE)` 로 **두 해**와
  각 재투영오차를 재투영오차 오름차순으로 반환. 결과는 **optical 프레임** `optical_T_marker`.
  distortion=None(rectified).
- `base_T_cam_from_marker(T_base_marker, optical_T_marker) -> 4×4`:
  `cam_body_T_marker = T_BODY_OPTICAL @ optical_T_marker`;
  `return T_base_marker @ inv(cam_body_T_marker)`. → **base_T_cam(body 프레임)**.
- `base_T_world(base_T_cam_body, world_T_cam_body) -> 4×4`:
  `base_T_cam_body @ inv(world_T_cam_body)`.
- `average_poses(list_of_4x4) -> 4×4`: 병진 = 중앙값, 회전 = **쿼터니언 평균**(Markley:
  `M = Σ qqᵀ` 의 최대고유벡터, numpy `eigh`). scipy 있으면 써도 됨.
- `mat_to_xyzquat(T) -> (xyz, xyzw)`: TF 발행용. 회전은 **quaternion (x,y,z,w)**.
- `--selftest`(스크립트 하단): 임의 `T_base_marker`·`base_T_cam` 를 정하고, 태그 4코너를 카메라에
  투영해 합성 `corners_px` 생성 → `pnp_cam_optical_T_marker`→`base_T_cam_from_marker` 가 입력
  `base_T_cam` 를 **mm/deg 오차 내로 복원**하는지 assert. (프레임 로직의 정적 증명.)

### (B) 신규 `scripts/measure_base_cam.py` — 라이브 측정 도구 (pyzed, conda zed env)
- **ROS2 를 import 하지 않는다.** 산출물은 yaml 파일뿐.
- CLI:
  - `--datum PATH`(기본 `logs/base_cube_datum.json`) — base_T_marker 데이텀 + tag_size + dictionary.
  - `--fusion-config PATH`(기본 `logs/fusion_zed360.json`) — world_T_cam 원천(base_T_world 계산용).
  - `--out PATH`(기본 `logs/base_cam_extrinsics.yaml`) — 발행용 좌표 상수(§출력 포맷).
  - `--frames N`(기본 60), `--max-reproj PX`(기본 1.0) — 재투영오차 게이트.
  - `--ambiguity-ratio R`(기본 0.3) — IPPE 두 해 재투영오차 비(err0/err1) > R 이면(모호) 그 검출 폐기.
  - `--serial-map "13870389=zed1,19321109=zed2"`(기본 이 매핑) — serial→child frame 이름.
  - `--preview`(디스플레이) / `--save-debug PATH`(헤드리스) — 검출·좌표축 확인용 주석 이미지.
- 흐름:
  1. `load_datum`, `read_fusion_configuration_file(...)` 로 상수·`world_T_cam` 획득.
  2. 카메라를 **한 대씩 순차 open**(`set_from_serial_number`, `RESOLUTION.HD720`, `camera_fps=30`,
     **`depth_mode = NONE`**, `coordinate_units = METER`, **`camera_disable_self_calib=True`**).
     K = `calibration_parameters.left_cam`(raw 아님). 이미지 = `retrieve_image(LEFT)` → BGRA →
     GRAY → `cv2.aruco.ArucoDetector`(dictionary = datum 의 것).
  3. `--frames` 동안 각 프레임: 검출된 마커 중 **datum 에 있는 ID만**(화이트리스트) 채택.
     각 마커 → `pnp_cam_optical_T_marker` → 게이트(재투영오차·모호성) 통과분 →
     `base_T_cam_from_marker(T_base_marker[id], optical_T_marker)` = base_T_cam 후보.
     **한 프레임에 여러 면이 보이면 각 면이 후보 하나** → 전부 수집.
  4. serial 별로 후보들을 `average_poses` → **base_T_cam(body)** 확정. 그리고
     `base_T_world = base_T_world(base_T_cam, world_T_cam[serial])` 도 serial 별로 산출.
  5. **교차검증**: 두 카메라가 각각 낸 base_T_world 의 병진(mm)·회전(deg) 편차를 리포트(둘이
     달라진 만큼이 ZED360 extrinsic + 측정 품질 지표). 최종 base_T_world 는 두 추정의
     `average_poses`.
  6. `--out` yaml 저장(§출력 포맷). 카메라 1대만 보여도 그 대 기준으로 동작(교차검증은 생략).
- **stdout 요약**: 카메라별 채택/폐기 프레임 수, base_T_cam xyz, base_T_world 교차검증 편차.

### (C) 신규 `logs/base_cube_datum.example.json` — 데이텀 템플릿
```json
{
  "coordinate_system": "RIGHT_HANDED_Z_UP_X_FWD",
  "unit": "METER",
  "dictionary": "DICT_5X5_100",
  "tag_size_m": 0.10,
  "note": "정육면체 겉면 101mm, 반 변 0.0505m. 마커 중앙·정립(위=+Z) 부착. 값은 CAD 확정치.",
  "markers": [
    { "id": 1, "center_m": [0.0,    0.0,    0.0], "normal": [1,0,0],  "up": [0,0,1], "face": "정면 +X" },
    { "id": 2, "center_m": [-0.0505, 0.0505, 0.0], "normal": [0,1,0],  "up": [0,0,1], "face": "왼쪽 +Y" },
    { "id": 0, "center_m": [-0.0505,-0.0505, 0.0], "normal": [0,-1,0], "up": [0,0,1], "face": "오른쪽 -Y" }
  ]
}
```
사용자가 `logs/base_cube_datum.json` 로 복사해 최종 CAD 값으로 확정(코드는 실제 파일을 입력받음).

### (D) 신규 `ros2_ws/src/cbf_base_tf/` — ROS2 static TF 패키지 (시스템 Humble)
ament_python 패키지. **pyzed/CUDA/conda 의존 전무.** yaml(=(B) 산출물)만 읽어 static TF 를 발행하는
**커스텀 브로드캐스터 노드** 하나로 구성(사용자 참조 스타일). launch+CLI `static_transform_publisher`
대신 노드로 가는 이유: 읽기 쉽고, 나중 토픽 브리지를 같은 노드에서 확장하기 쉽다.
- `package.xml` — build_type `ament_python`. `<depend>rclpy</depend>`, `<depend>tf2_ros</depend>`,
  `<depend>geometry_msgs</depend>`, `<exec_depend>ros2launch</exec_depend>`.
- `setup.py` / `setup.cfg` / `resource/cbf_base_tf` / `cbf_base_tf/__init__.py` — 표준 스캐폴딩.
  `entry_points.console_scripts` 에 `static_tf_node`. `data_files` 에 `launch/`·`config/` 설치.
- `config/base_cam_extrinsics.yaml` — (B) 출력의 **샘플/플레이스홀더** 사본(사용자가 실측값으로 교체).
- `cbf_base_tf/static_tf_node.py` — rclpy 노드(사용자 샘플 구조 그대로). yaml 의 `transforms`
  (parent/child/translation/rotation_quat) 를 읽어 `StaticTransformBroadcaster.sendTransform([...])`
  로 **리스트째 한 번에** 발행. `StaticTransformBroadcaster` 가 `/tf_static` 을 transient_local 로
  쏘므로 구독자가 늦게 붙어도 받는다 → 노드는 그냥 `spin` 유지. 발행 전 각 quaternion 정규화 확인.
  yaml 경로는 ROS 파라미터 `extrinsics`(기본 패키지 내 config) 로 받는다.
- `launch/base_tf.launch.py` — 위 노드 하나 실행, `extrinsics` 파라미터로 yaml 경로 주입
  (`extrinsics:=<path>` 로 오버라이드).
- `README.md`(패키지 내) — 빌드/실행 3줄: `colcon build --packages-select cbf_base_tf` →
  `source install/setup.bash` → `ros2 launch cbf_base_tf base_tf.launch.py extrinsics:=<yaml>`.

## 참고해야 할 것 (왜 보는지 함께)

- `scripts/aruco_zed_test.py` — 검출/solvePnP/intrinsic 흐름의 원본. `make_object_points` 코너 순서,
  `get_K`(left_cam), `SOLVEPNP_IPPE_SQUARE`, BGRA→GRAY 를 (A)/(B) 가 동일하게 따른다. **단 import
  하지 말고 필요한 로직만 재구현**(그 파일은 pyzed 를 끌어옴 → (A) 정적 검증 오염).
- `scripts/zed_check.py` — 카메라 **한 대씩 순차 open/close** 패턴(USB 1컨트롤러 제약).
- `scripts/zed_make_fusion_config.py` — `read_fusion_configuration_file` 사용법·COORD/UNIT 상수 확인.
- `logs/fusion_zed360.json` — `world_T_cam` 원천(읽기 전용). serial 키·pose 포맷.
- 대화·CAD 확정 데이텀(§3 표) — (C) 의 값이 이것과 일치해야 한다.

## 신경써야 할 것 (가드레일)

- **검증된 런타임 변경 금지**: `zed_fusion_viz.py`/`zed_fusion_bodytrack.py`/
  `zed_make_fusion_config.py`/`run_fusion.py`/`aruco_zed_test.py` **수정 없음. 새 파일만.**
- **측정 도구는 ROS2 를 import 하지 않는다**(분리 원칙의 핵심). ROS2 패키지는 pyzed 를 import
  하지 않는다. 접점은 yaml 파일뿐.
- **`logs/**` 기존 파일 수정 금지**: `fusion_zed360.json` 등은 읽기 전용. 새 파일
  (`base_cube_datum.example.json`, `base_cam_extrinsics.yaml`)만 생성.
- **프레임 일관성**: solvePnP=optical → 즉시 `T_BODY_OPTICAL` 로 body 전환. 이후 전 계산·발행은
  body(Z-up). base_T_world 는 body끼리 합성. 프레임을 한 곳(`aruco_cube_datum.py`) 밖에서 섞지 말 것.
- **중심-3점 Kabsch 쓰지 말 것**: 큐브라 중심이 몰려 yaw 지렛대가 짧다. 각 마커 자세를 직접 쓴다.
- **태그 크기 = 검은 사각형만**(흰 여백 제외). 흰 여백 포함 시 거리·pose 가 통째로 틀어짐.
- **ID 화이트리스트**: datum 에 없는 검출 ID 는 폐기(false-positive 방어).
- **flip 안전장치**: `SOLVEPNP_IPPE_SQUARE` 두 해 + 재투영오차/모호성 게이팅(`--ambiguity-ratio`).
- **distortion=0**: rectified `retrieve_image(LEFT)` + `calibration_parameters`(raw 아님).
- **`camera_disable_self_calib=True`**: 세션마다 intrinsic 이 미세하게 바뀌는 것 방지.
- **카메라 한 대씩**: 동시 2대 open 은 USB 컨트롤러 1개라 위험 → 순차 open/close.
- **비유한값 게이트**: NaN/inf pose 는 후보에서 제외(가짜 좌표 방지).
- **회전은 quaternion 으로만 발행**: yaml·노드 모두 (x,y,z,w) 쿼터니언을 쓴다. euler(yaw/pitch/roll)
  순서 혼동을 애초에 피한다. 발행 전 `w²+x²+y²+z²≈1` 정규화 확인.
- **샌드박스에 카메라·GPU·ROS2 없음**: codex 는 (B) 라이브 실행·(D) colcon build 불가. (A)(C) 는
  합성 입력으로 정적 검증, (B) 는 `py_compile`+`--help`+분기, (D) 는 `py_compile`(launch)+yaml/xml
  스키마 확인까지. **라이브·빌드는 사용자.**

## 코드 스타일 (사용자 요청 — "AI 티 안 나게")

사용자가 제시한 참조 샘플(rclpy `StaticTransformBroadcaster` 노드) 수준의 **손으로 쓴 듯한 가독성**을
목표로 한다. 표면(주석·레이아웃·네이밍·군더더기)에만 적용하고, **정확성 가드레일(프레임 변환,
게이팅, ID 화이트리스트, distortion=0 등)은 절대 타협하지 않는다.**

- **주석은 한국어로, "왜"를 설명**한다(코드를 기계적으로 한 줄씩 되풀이하지 말 것). 개념 메모·근거를
  블록 위나 옆에 자연스럽게 단다. 참조 샘플의 tf2 설명 주석 톤을 따른다.
- **넉넉한 빈 줄**로 논리 단계를 분리한다(함수 안에서도 국면이 바뀌면 빈 줄 1~2개).
- **과한 docstring 금지**: 함수마다 `Args:/Returns:/Raises:` 블록을 붙이지 말 것. 필요하면 짧은
  한국어 한 줄 주석으로 대체. 모듈 상단 설명은 참조 샘플처럼 간결하게.
- **타입힌트는 가볍게**: 읽기에 도움되는 곳만. 모든 인자/반환에 기계적으로 달지 말 것.
- **과설계 금지**: 불필요한 클래스·팩토리·추상화 레이어, 모든 줄을 감싸는 방어적 try/except 지양.
  참조 샘플처럼 절차를 위에서 아래로 곧게 쓴다.
- **이모지·장식 구분선·과장된 로그 문구 금지.** 네이밍은 짧고 실용적으로(`t`, `q`, `ps_camera` 수준).
- 공격적 자동 포매터로 "기계처럼 완벽하게" 밀지 말 것 — 참조 샘플 정도의 자연스러움 유지.
- 파일 상단은 `#!/usr/bin/env python3` + `# -*- coding: utf-8 -*-`(참조 샘플과 동일).

## 이번에는 하지 않는 것 (non-scope)

- **라이브 스켈레톤을 ROS2 토픽으로 흘리기**(소켓/zeromq 브리지 노드). 이번엔 static TF 만.
- **PLAN05(fusion world → robot base, 협업자 것) 연동** 및 **robot_base ↔ ArUco큐브 오프셋**.
  나중에 TF 엣지 하나(`robot_base → base`)로 이어붙인다.
- **RoboStack(conda 안 ROS2)** 경로. 지금은 시스템 apt Humble 분리로 충분.
- **zed_ros2_wrapper 도입**, ZED 라이브 데이터의 ROS2 직결.
- **데이텀 정확도의 로봇 실측 교차검증**(TCP 터치 등).
- ArUco 검출 파라미터 튜닝, 태그 크기/딕셔너리 변경.

## 근거

- 대화·CAD 로 확정: base=마커1, 큐브 3면 배치·치수(§3), 태그 정립 부착, 카메라·큐브 고정 →
  static 1회 측정.
- 리서치(2026-07-21, 출처는 아래): ZED SDK 는 CUDA 강제(depth 꺼도), conda+apt-ROS2 동일 셸 혼용은
  공식 안티패턴, Stereolabs 가 "별도 프로세스+IPC" 권장, ZED-M UVC 경로 존재하나 이번엔 SDK
  rectified 경로 사용, `static_transform_publisher` 가 고정 extrinsic 발행의 표준(단 latch 버그
  이력 → 노드 상시 실행). Ubuntu 24.04 는 시스템 Python 3.12 라 pyzed cp310 과 불일치 → 22.04/Humble
  유지가 정답.
  - https://support.stereolabs.com/hc/en-us/articles/1500009126942 (CUDA 필수)
  - https://community.stereolabs.com/t/numpy-version-problem-for-ros2-based-zed-sdk-api-usage/10188 (별도 프로세스 권장)
  - https://docs.ros.org/en/humble/How-To-Guides/Installation-Troubleshooting.html (conda/apt 혼용 경고)

## 검증

**정적 (codex, 샌드박스에서 가능):**
- `python3 -m py_compile scripts/aruco_cube_datum.py scripts/measure_base_cam.py` 통과.
- `scripts/measure_base_cam.py --help` 노출.
- `python3 scripts/aruco_cube_datum.py --selftest` 통과(합성 코너 라운드트립이 base_T_cam 을
  mm/deg 내 복원).
- (C) json 을 `load_datum` 으로 읽어 마커 3개의 `T_base_marker` 가 §3 표와 일치(회전 직교성,
  중심 좌표) 하는지 확인하는 미니 체크(셀프테스트에 포함).
- (D): `python3 -m py_compile ros2_ws/src/cbf_base_tf/cbf_base_tf/static_tf_node.py
  ros2_ws/src/cbf_base_tf/launch/base_tf.launch.py`, `package.xml`/`setup.py` 존재·형식 확인,
  샘플 yaml 파싱.

**라이브 (사용자, 하드웨어·ROS2):**
- 터미널 A(conda zed): `python3 scripts/measure_base_cam.py --preview` → 검출·좌표축 육안 확인 →
  `logs/base_cam_extrinsics.yaml` 생성. 두 카메라 base_T_world 교차검증 편차 확인(작을수록 좋음).
- 터미널 B(시스템 Humble): `colcon build --packages-select cbf_base_tf` →
  `ros2 launch cbf_base_tf base_tf.launch.py extrinsics:=<yaml>` → `ros2 run tf2_tools view_frames`
  또는 RViz2 TF 로 base→zed1/zed2/fusion_world 가 **물리적으로 맞는 위치/방향**인지 확인.
- (판정) 카메라를 큐브에서 실제 떨어진 거리·방향과 base→zed_link 병진/회전이 상식적으로 일치하는가.
  좌표계(optical→body, +X/+Z 방향) 오류가 여기서 드러난다.

## 다음 단계

- 좌표·정확도 확인되면: **라이브 스켈레톤(fusion_world BODY_34)을 ROS2 토픽으로 흘리는 브리지**
  (conda 측 소켓 발행 → apt-ROS2 브리지 노드가 `/tf`·PointCloud/Marker 로 재발행). base→fusion_world
  가 이미 TF 에 있으므로 스켈레톤이 base 프레임에 바로 배치된다.
- **PLAN05 연동**: `robot_base → base(ArUco큐브)` 엣지 하나를 추가하면 tf2 가
  `robot_base → fusion_world` 를 자동 합성 → CBF 소비 프레임 완성.
- 반복도(앵커 10회) 표준편차를 ε(t) 상수항으로.
