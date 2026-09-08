---
date: 2026-08-03
task: Fusion BODY_34 스켈레톤을 fusion_world 프레임 그대로 ROS2 토픽으로 실시간 발행하는 새 브리지 스크립트. base 좌표 변환은 코드로 짜지 않고 cbf_base_tf 의 static TF + tf2 에 위임한다
planner: Claude
executor: codex
status: done
---

# PLAN09 — Fusion 스켈레톤 ROS2 실시간 브리지 (base 변환은 tf2 위임)

> 파일: `docs/plans/2026_08/03_PLAN09_fusion_ros2_bridge.md` (식별자 = PLAN09).

## 한 줄 결론

새 스크립트 `scripts/fusion_ros2_bridge.py` 를 추가한다. 기존 `scripts/zed_fusion_bodytrack.py`
**의 함수를 import 재사용**해 sender·Fusion 을 띄우고, 융합된 BODY_34 스켈레톤을 매 프레임
**`frame_id: "fusion_world"` 그대로** `MarkerArray`(시각화) + `PoseArray`(데이터)로 퍼블리시한다.
**base 좌표로 옮기는 행렬 곱은 짜지 않는다** — `cbf_base_tf` 가 발행하는 `base→fusion_world`
static TF 를 tf2 가 적용한다. ZED 쪽 기존 스크립트는 한 줄도 수정하지 않는다.

## 왜 이 plan 이 필요한가

지금 파이프라인은 **좌표가 이어지지 않은 채 끊겨 있다.**

- `scripts/zed_fusion_bodytrack.py` 는 융합 스켈레톤을 `"frame": "fusion_world"` 로 JSONL 에 쓴다.
- `logs/base_cam_extrinsics.yaml` 에는 `base→fusion_world` 변환이 이미 들어 있다.
- **그런데 이 둘을 실제로 잇는 코드가 없다.** 재료는 다 있는데 조립이 안 됐다.

그리고 최종 소비자인 CBF 안전층은 **실시간 데이터**를 먹는다. 파일 후처리 변환기를 만들어도
결국 버려야 하므로, 처음부터 실시간 경로를 만든다.

이 plan 이 끝나면 RViz2 에서 Fixed Frame 을 `base` 로 두는 것만으로 사람 스켈레톤이 로봇 기준
좌표에 서 있는 것을 볼 수 있고, 다운스트림 노드는 `tf2_ros.Buffer.transform(msg, "base")`
한 줄로 base 좌표를 얻는다.

## 지금까지 이어진 맥락 (이 plan 만 읽어도 되게 재서술)

프레임 표기: `T_A_B` = B 좌표의 점을 A 좌표로 보냄 (`p_A = T_A_B · p_B`).

### 1. 하드웨어 / 환경

- ZED-M **2대** (S/N `13870389`=zed1, `19321109`=zed2), ZED SDK **5.4**, Ubuntu 22.04.
- USB 컨트롤러가 하나(Intel xHCI)라 **2×HD720@30 고정**. `--fps 30` 이외는 코드가 거부한다.
- pyzed 는 conda `zed` env (Python **3.10.20**, conda-forge/GCC 14.3), numpy **2.2.6**.
- ROS2 **Humble** 은 시스템 설치 (Python **3.10.12**, GCC 11.4).
  rclpy 실경로: `/opt/ros/humble/local/lib/python3.10/dist-packages/`.

### 2. ★ conda pyzed 와 시스템 rclpy 는 한 프로세스에서 공존한다 (이번에 실측 확인)

이 plan 전체가 이 사실 위에 서 있다. **2026-08-03 에 직접 실행해 확인했다:**

```
conda run -n zed  +  source /opt/ros/humble/setup.bash  +  PYTHONPATH 에 ROS2 dist-packages 추가
  → import rclpy / tf2_ros / geometry_msgs / visualization_msgs   OK
  → import pyzed.sl                                                OK
  → rclpy.init() → Node 생성 → create_publisher → tf2_ros.Buffer/TransformListener
    → publish → spin_once                                          OK
  → RMW = rmw_fastrtps_cpp, numpy = 2.2.6 (conda 것이 그대로 유지됨)
```

되는 이유: 양쪽 다 Python **3.10** 이라 C 확장 ABI 가 호환되고, conda 쪽 libstdc++ 가 시스템보다
**최신**(GCC 14 > 11)이라 시스템 `.so` 를 얹는 방향이 문제없다. pyzed 휠 이름도 `cp310` 이다.

**따라서 "conda 프로세스와 ROS2 프로세스를 소켓/파일 IPC 로 분리한다" 같은 우회는 필요 없다.**
브리지 한 프로세스가 pyzed 로 Fusion 을 돌리면서 동시에 rclpy 로 퍼블리시한다.

### 3. 좌표계 / 포맷 규약 (전 구간 통일, 바꾸지 말 것)

- `RIGHT_HANDED_Z_UP_X_FWD` / `METER` (X=전방, Y=좌, Z=상).
- sender 검출 포맷 = **BODY_18**, Fusion 융합 결과 = **BODY_34**. 인덱스를 섞지 않는다.
- 융합 결과 keypoint 는 **fusion world frame** 기준이다.

### 4. base 프레임과 static TF (PLAN06~08 에서 확정, 이미 동작)

- `base` 원점 = ArUco 큐브의 **마커 1 중심**, +X=큐브 정면, +Z=위, +Y=왼쪽.
- `scripts/measure_base_cam.py` 가 측정해 `logs/base_cam_extrinsics.yaml` 을 만든다. 내용은
  `base→zed1_link`, `base→zed2_link`, `base→fusion_world` **3개의 translation+rotation_quat 뿐**이다
  (이미지·intrinsic·ArUco 중간값은 들어가지 않는다).
- ROS2 패키지 `ros2_ws/src/cbf_base_tf` 의 `static_tf_node.py` 가 그 YAML 을 읽어 `/tf_static` 으로
  3개를 **한 번에** 발행한다. 이 노드는 rclpy/tf2_ros/geometry_msgs/yaml 만 쓰고 OpenCV·pyzed 를
  전혀 import 하지 않는다.
- **⚠ 이 패키지는 아직 한 번도 colcon build 된 적이 없다** (`ros2_ws/build`, `ros2_ws/install` 없음).
- **⚠ 함정**: launch 의 `extrinsics` 기본값은 패키지 share 안의
  `config/base_cam_extrinsics.yaml` 인데 이건 **translation 전부 0, rotation 단위 quaternion 인
  placeholder** 다. 실측 경로를 안 넘기면 `fusion_world` 가 `base` 와 정확히 겹쳐서 **틀렸는데도
  맞아 보이는** 상태가 된다.

### 5. 측정 정확도의 현재 한계 (알고 있어야 할 것, 이번 범위 아님)

ArUco 측정은 이 리그(10cm 태그 @ 1.9m)에서 **데시미터급**이다. 같은 배치 3회 실행에서
`base_T_world` 교차검증이 552 / 704 / 1022 mm, 14~21° 로 요동했다. 원인은 코드 버그가 아니라
측정 기하(작은 태그 + 먼 거리 + 정사각 마커 IPPE flip 모호성)이며,
`aruco_cube_datum.py --selftest` 가 합성 데이터로 1mm/0.1° 이내 라운드트립을 통과해 **수학은
옳다**는 것이 증명돼 있다. 정밀화(ChArUco 보드)는 CBF 연동 시점 과제로 보류 중이다.

**중요**: 이 오차는 **스켈레톤 융합 품질과 무관**하다. 융합은 ZED360 이 만든
`logs/fusion_zed360.json` 의 extrinsic 을 쓰며, 2026-07-24 에 사람 1명 40초 촬영에서 내내
`fused=1`, 단일 스켈레톤(id 0)으로 확인됐다. 이번 plan 은 그 좌표를 **옮기는** 일이지
정확도를 올리는 일이 아니다.

### 6. 재사용 대상 자산 — `scripts/zed_fusion_bodytrack.py` (수정 금지, import 만)

이 파일은 **모듈 레벨 함수/상수 + `if __name__ == "__main__"` 가드** 구조라 import 해도
아무것도 실행되지 않는다. 선례도 있다 — `base_tf_live.py` 가 `aruco_cube_datum`,
`measure_base_cam` 을 같은 방식으로 끌어 쓰고 원본은 무수정이다.

가져다 쓸 심볼:

| 심볼 | 역할 |
|---|---|
| `COORD`, `UNIT` | `RIGHT_HANDED_Z_UP_X_FWD` / `METER` |
| `BODY_FORMAT` | sender 검출 포맷 `sl.BODY_FORMAT.BODY_18` |
| `FUSED_BODY_FORMAT_NAME` | `"BODY_34"` |
| `BONES_34` | BODY_34 뼈대 연결쌍 33개 — **LINE_LIST 마커에 그대로 쓴다** |
| `_read_config(path)` | Fusion config JSON → `sl.FusionConfiguration` 리스트 (2대 미만이면 RuntimeError) |
| `_open_sender(conf, res, fps, depth, conf_threshold, retry_count, retry_wait)` | 카메라 open + positional tracking(static) + body tracking + `start_publishing` 까지. 리턴 `{"serial", "camera", "runtime", "bodies"}` |
| `_init_fusion(configs, verbose)` | `sl.Fusion` init + subscribe + `enable_body_tracking`. 리턴 `(fusion, identifiers)` |
| `_joint_indices(name)` | HEAD/LEFT_WRIST/RIGHT_WRIST 인덱스 (로그용, 이번엔 선택) |
| `_ok_keypoint(point)` | keypoint 유효성 판정 — **NaN/무효 관절 걸러내는 기준을 새로 만들지 말고 이걸 쓴다** |
| `_tolist(value)` | numpy/SDK 배열 → 파이썬 리스트 |
| `_status_failed`, `_camera_identifier` | 필요 시 |

`main()` 의 루프 골격(참고용, 그대로 옮기지 말고 필요한 부분만):

```
for sender in senders: sender["camera"].grab() → retrieve_bodies(...)
fusion.process()
fusion.retrieve_bodies(fused, runtime, sl.CameraIdentifier(), sl.FUSION_REFERENCE_FRAME.WORLD)
for body in fused.body_list: ...
```

`runtime` 은 `sl.BodyTrackingFusionRuntimeParameters()` 에
`skeleton_minimum_allowed_keypoints`, `skeleton_minimum_allowed_camera`, `skeleton_smoothing`
세 필드를 채운 것이다. 시작 직후 **warmup grab 1회**를 senders 에 먼저 돌려야
shared-memory sender 가 Fusion subscribe 전에 준비된다(원본 주석에 명시돼 있음).

## 지금 기준 판단 (사용자와 확정)

1. **좌표 변환은 짜지 않는다.** 스켈레톤을 `fusion_world` 로 내보내고 base 변환은 tf2 에 맡긴다.
   브리지 안에서 직접 곱하면 좌표계가 두 군데서 관리돼, 카메라를 옮겨 YAML 만 갱신했을 때
   한쪽만 낡는 사고가 난다. 단일 source of truth 는 `/tf_static` 이다.
2. **오프라인 JSONL→base 변환기는 만들지 않는다.** 종점이 실시간이라 우회로다. 폐기.
3. **ZED 쪽 코드는 무수정.** 새 파일만 추가하고 기존 것은 import 재사용한다.
4. **numpy 를 건드리지 않는다.** conda `zed` 의 numpy 2.2.6 을 그대로 둔다. 대신 브리지는
   numpy 1.x 를 요구하는 ROS2 자산(`cv_bridge`, `sensor_msgs/Image`, PointCloud 헬퍼)을
   **절대 import 하지 않는다.** 스켈레톤 좌표만 보내면 쓸 일이 없다.
4-1. **환경 결합은 브리지 서브셸 안으로만 가둔다 (사용자 추가 요구).** 한 프로세스 구조는
   유지하되, ROS2 환경변수가 밖으로 새지 않도록 격리한다. 상세는 §환경 격리 규약.
   실측상 런타임 충돌은 없으므로 프로세스를 쪼개는 구조(IPC)는 **이번 범위에서 검토하지
   않는다** — 지연이 한 단계 늘고 되돌리기도 어렵다. 다만 메시지 빌더는 pyzed 타입에
   의존하지 않는 순수 함수로 두어, 나중에 어떤 구조 변경이 오더라도 그대로 재사용되게 한다
   (이번엔 단위 검증을 가능하게 하는 것이 1차 목적이다).
5. **메시지는 2종.** RViz 로 보는 용(`MarkerArray`)과 다운스트림이 먹는 용(`PoseArray`)을 나눈다.
   커스텀 msg 패키지는 만들지 않는다 — 빌드 부담만 늘고 지금 필요 없다.
6. **PoseArray 는 한 명분.** `PoseArray` 는 body id 를 실을 자리가 없다. 다인 데이터 토픽은
   커스텀 msg 가 필요하므로 다음 plan 으로 미룬다. 시각화(`MarkerArray`)는 전원 표시한다.
7. **타임스탬프는 노드 시계 고정.** static TF 는 시각 무관하게 latch 되므로 lookup 에 영향이 없다.
   ZED 취득 시각 기반 지연 분석은 이번 범위 밖.

## 이번에 할 것

신규 파일 **3개**와 **colcon build 1회**. 기존 파일 수정은 `.gitignore` 한 줄 외에 없다.

| 대상 | 환경 | 성격 |
|---|---|---|
| `scripts/fusion_ros2_bridge.py` | conda `zed` + ROS2 PYTHONPATH | 본체 |
| `scripts/run_bridge.sh` | bash | 환경 결합 런처 |
| `scripts/check_tf_to_base.py` | 시스템 ROS2 (pyzed 불필요) | 검증 도구 |
| `ros2_ws` colcon build | 시스템 ROS2 | 선행 조건 |

## 환경 격리 규약 (사용자 추가 요구 — 반드시 지킬 것)

conda `zed` 와 시스템 ROS2 는 **한 프로세스에서 공존하되, 결합은 브리지 서브셸 안에서만**
일어나야 한다. 아래 6개는 타협 대상이 아니다.

1. **부모 셸을 오염시키지 않는다.** 사용자가 `run_bridge.sh` 를 실행하기 위해
   `conda activate zed` 나 `source /opt/ros/humble/setup.bash` 를 **미리 해둘 필요가 없어야**
   한다. 런처가 서브셸 안에서 자급자족한다. 런처는 부모 셸의 `PYTHONPATH` 를 덮어쓰지 않고
   **뒤에 이어붙이기만** 한다(`:${PYTHONPATH:-}`).
2. **역방향 오염 금지.** ROS2 환경이 잡힌 셸에서 기존 ZED 스크립트
   (`measure_base_cam.py`, `base_tf_live.py`, `zed_fusion_bodytrack.py`, `run_fusion.py`)를
   실행하는 경로를 만들지 않는다. 그 스크립트들은 **순수 conda `zed`** 에서만 돌아야 한다.
   런처는 브리지 하나만 띄운다.
3. **어떤 패키지도 설치·변경하지 않는다.** `pip install`, `conda install`, `apt install`,
   `rosdep install` 전부 금지. conda 의 numpy 2.2.6, pyzed 5.4, 시스템 ROS2 Humble 을
   **있는 그대로** 쓴다. 이게 실측으로 검증된 유일한 조합이다.
4. **얹는 것은 최소한만.** 브리지 서브셸에서 source 하는 것은 `/opt/ros/humble/setup.bash`
   **하나뿐**이다. `ros2_ws/install/setup.bash` 는 source 하지 않는다 — `cbf_base_tf` 는
   완전히 다른 프로세스에서 뜨고, 브리지는 그 패키지의 파이썬 코드를 쓰지 않는다.
5. **★ 하드 게이트**: 브리지는 시작 직후 아래를 검사하고 **하나라도 어긋나면 즉시 exit 3**
   한다. 경고만 찍고 진행하지 않는다.
   - `numpy.__file__` 이 conda `zed` env 아래인가 (ROS2 쪽 numpy 가 앞으로 끼어들지 않았는가)
   - `pyzed` 가 import 되는가
   - `rclpy.__file__` 이 `/opt/ros/humble/` 아래인가
   - 실패 시 세 경로를 그대로 출력하고 "run_bridge.sh 로 실행하라"고 안내한다.
   이 게이트가 있으면 환경이 틀어진 채 반쯤 도는 상태 — 제일 디버깅하기 나쁜 상태 — 가
   원천 차단된다.
6. **`conda activate` 를 스크립트에서 쓰지 않는다.** 비대화형 셸에서 불안정하다.
   `conda run -n zed` 만 쓴다.

## 구현해야 할 것 (파일 단위)

### 0. 선행 — `cbf_base_tf` 빌드

```bash
cd ros2_ws && colcon build --packages-select cbf_base_tf
```

- 빌드 산출물이 저장소를 더럽히지 않도록 `.gitignore` 에
  `ros2_ws/build/`, `ros2_ws/install/`, `ros2_ws/log/` 를 추가한다. (기존 항목은 건드리지 않는다.)
- `source ros2_ws/install/setup.bash` 후 `ros2 pkg list | grep cbf_base_tf` 로 확인.

### 1. 신규 `scripts/fusion_ros2_bridge.py`

conda `zed` env 에서 실행하되 `PYTHONPATH` 로 ROS2 를 얹은 상태를 전제한다.

**import 재사용 (새로 짜지 말 것):**

```
from zed_fusion_bodytrack import (COORD, UNIT, BODY_FORMAT, FUSED_BODY_FORMAT_NAME, BONES_34,
                                  _read_config, _open_sender, _init_fusion,
                                  _ok_keypoint, _tolist)
```

`scripts/` 는 패키지가 아니므로 `python3 scripts/fusion_ros2_bridge.py` 실행 시 `sys.path[0]` 이
`scripts/` 가 되어 형제 import 가 성립한다 (`base_tf_live.py` 와 동일한 방식).

**CLI (argparse)** — bodytrack 과 같은 이름·기본값을 쓴다:

- `--config PATH` (필수) — Fusion config JSON. 실사용은 `logs/fusion_zed360.json`.
- `--res HD720`, `--fps 30`, `--depth NEURAL`, `--conf 40`
- `--min-keypoints 7`, `--min-cameras 1`, `--smoothing 0.1`
- `--retry-count 3`, `--retry-wait 1.0`, `--verbose-fusion`
- `--duration 0` (0 = Ctrl-C 까지)
- `--frame-id fusion_world` — 퍼블리시 헤더 프레임
- `--topic-prefix /human` — 토픽 접두사
- `--marker-lifetime 0.2` (초) — 프레임 끊겼을 때 잔상 제거
- `--node-name fusion_skeleton_bridge`

`--fps` 가 30 이 아니면 bodytrack 과 동일하게 **에러 종료(exit 2)** 한다. 이 리그는 @60 에서
붕괴한다.

**퍼블리시 토픽 3개** (QoS 는 기본값 = RELIABLE/VOLATILE/depth 10. RViz 기본 구독과 맞춘다):

| 토픽 | 타입 | 내용 |
|---|---|---|
| `{prefix}/skeleton_markers` | `visualization_msgs/MarkerArray` | 전원 시각화 |
| `{prefix}/skeleton_poses` | `geometry_msgs/PoseArray` | 대표 1명의 34관절 |
| `{prefix}/body_count` | `std_msgs/Int32` | 현재 융합된 사람 수 (RViz 없이 확인용) |

**MarkerArray 구성 (프레임마다 새로 만든다):**

- 맨 앞에 `action = Marker.DELETEALL` 마커 1개 → 사라진 사람의 잔상 제거.
- body 마다 `ns = "body_%d" % body.id`, 두 개의 마커:
  - `id=0`: `SPHERE_LIST`, `scale = 0.05` — `_ok_keypoint` 통과한 관절만 점으로.
  - `id=1`: `LINE_LIST`, `scale.x = 0.02` — `BONES_34` 를 순회하되 **양 끝 관절이 모두
    `_ok_keypoint` 를 통과할 때만** 두 점을 넣는다. 한쪽이라도 무효면 그 뼈는 생략.
- 색은 `body.id` 로 결정되는 고정 팔레트(5~6색 순환)를 쓴다. 사람이 여럿일 때 구분되게.
- 모든 마커: `header.frame_id = args.frame_id`, `header.stamp = node.get_clock().now()`,
  `lifetime = args.marker_lifetime`, `pose.orientation.w = 1.0`.

**PoseArray 구성:**

- `fused.body_list` 가 비어 있으면 **빈 PoseArray 를 발행한다**(발행 자체를 거르지 않는다 —
  소비자가 "사람 없음"을 알 수 있어야 한다).
- 사람이 있으면 `body_list[0]` 하나를 골라 **인덱스 0~33 순서를 그대로 유지한 34개**를 채운다.
  `orientation` 은 단위 quaternion 고정(BODY_34 는 관절 방향을 주지 않는다).
- **무효 관절은 SDK 가 준 값(보통 NaN)을 그대로 둔다.** 0으로 치환하거나 건너뛰면 인덱스가
  밀리거나 원점에 가짜 관절이 생긴다. 소비자가 `isfinite` 로 판단하는 계약이다.
  이 계약을 파일 상단 주석에 한 줄로 남긴다.
- 사람이 2명 이상 잡히면 **최초 1회만** 경고를 출력한다(매 프레임 로그 도배 금지).

**메인 흐름:**

1. `rclpy.init()` → `Node(args.node_name)` → 퍼블리셔 3개 생성.
2. **환경 하드 게이트** (§환경 격리 규약 5번). `numpy`·`pyzed`·`rclpy` 의 실제 로드 경로를
   검사해 하나라도 어긋나면 세 경로를 출력하고 **exit 3**. 통과하면 한 줄 요약
   (`rclpy=/opt/ros/humble/... numpy=2.2.6 (conda)`)을 남기고 진행한다. `rclpy.init()` 보다
   먼저 하는 게 좋다 — 잘못된 환경에서 DDS 를 띄우지 않게.
3. `_read_config(args.config)` → 각 config 마다 `_open_sender(...)`.
4. **warmup grab 1회**를 모든 sender 에 돌린다 (shared-memory sender 준비).
5. `_init_fusion(configs, args.verbose_fusion)` → `runtime` 파라미터 3필드 설정.
6. 루프:
   - 각 sender `grab()` → `retrieve_bodies(...)`
   - `fusion.process()` 실패 시 `continue`
   - `fusion.retrieve_bodies(fused, runtime, sl.CameraIdentifier(), sl.FUSION_REFERENCE_FRAME.WORLD)`
     실패 시 `continue`
   - 메시지 3개 빌드 후 퍼블리시
   - `rclpy.spin_once(node, timeout_sec=0.0)` — 퍼블리시만 하면 필수는 아니지만 파라미터·
     서비스 응답을 위해 매 루프 한 번 돌린다.
   - `--duration` 경과 또는 SIGINT 면 종료.
   - 1초마다 fps / 융합 인원수를 한 줄 출력 (bodytrack 과 같은 톤).
7. 종료: `fusion.close()` → sender 들 `disable_body_tracking()` + `close()` →
   `node.destroy_node()` → `rclpy.shutdown()`. SIGINT 는 플래그로 받아 루프를 빠져나온다
   (bodytrack 의 signal 처리 방식과 동일한 결).

**메시지 빌더는 순수 함수로 분리한다.** pyzed 객체가 아니라 **keypoint 리스트 + id** 를 받아
메시지를 만드는 형태로 두면 카메라 없이 단위 검증이 가능하다(§검증에서 쓴다). 예:
`build_marker_array(bodies_kp, frame_id, stamp, lifetime)`,
`build_pose_array(kp, frame_id, stamp)` — `bodies_kp` 는 `[(body_id, [[x,y,z], ...34]), ...]`.

### 2. 신규 `scripts/run_bridge.sh`

conda 와 ROS2 를 결합하는 얇은 런처. **아래 형태는 2026-08-03 에 실제로 동작을 확인한 조합**
이므로 그대로 따른다 (임의로 순서를 바꾸지 말 것):

```bash
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec conda run --no-capture-output -n zed bash -lc '
  source /opt/ros/humble/setup.bash
  export PYTHONPATH="/opt/ros/humble/local/lib/python3.10/dist-packages:/opt/ros/humble/lib/python3.10/site-packages:${PYTHONPATH:-}"
  exec python3 "$0" "$@"
' "$HERE/fusion_ros2_bridge.py" "$@"
```

- `--no-capture-output` 이 없으면 conda run 이 stdout 을 버퍼링해 라이브 로그가 안 보인다.
- 인자는 전부 브리지로 그대로 넘어가야 한다.
- `ROS_DOMAIN_ID` 등 이미 설정된 환경변수는 conda run 이 상속하므로 따로 손대지 않는다.
- **격리 확인용 체크리스트** (§환경 격리 규약과 1:1 대응):
  - `source` 와 `export` 는 전부 `conda run` **안쪽 서브셸**에 있다. 스크립트 바깥(부모 셸에서
    실행되는 줄)에는 환경 변경이 하나도 없다.
  - `PYTHONPATH` 는 `:${PYTHONPATH:-}` 로 **이어붙이기**만 한다. 통째로 덮어쓰지 않는다.
  - `source` 하는 것은 `/opt/ros/humble/setup.bash` 하나뿐이다.
    `ros2_ws/install/setup.bash` 는 넣지 않는다.
  - `conda activate` 를 쓰지 않는다. `exec` 로 넘겨 프로세스를 남기지 않는다.
  - 이 런처는 브리지 **하나만** 띄운다. static TF 노드나 RViz 를 같이 띄우지 않는다
    (환경이 다르므로 사용자가 별도 터미널에서 실행한다).

### 3. 신규 `scripts/check_tf_to_base.py`

**시스템 ROS2 python 으로 실행**한다(pyzed·CUDA·카메라 불필요). 하드웨어 없이 좌표 변환의
정확성 자체를 증명하는 것이 목적이다.

- rclpy 노드를 띄우고 `tf2_ros.Buffer` + `TransformListener` 로 `base` ← `fusion_world` 를 조회
  (`--timeout` 기본 5초, 못 찾으면 명확한 안내와 함께 exit 1).
- `--extrinsics PATH` (기본 `logs/base_cam_extrinsics.yaml`) 를 직접 파싱해 같은 변환을
  **손으로 계산**한다.
- 고정된 테스트 점 몇 개(예: 원점, 각 축 1m, 임의 점 하나)를 `tf2_geometry_msgs.do_transform_point`
  로 변환한 결과와 손계산 결과를 비교해 **1e-6 이내면 통과**, 아니면 차이를 출력하고 exit 1.
- **placeholder 감지**: 조회된 `base→fusion_world` 가 translation 전부 0 + 단위 quaternion 이면
  "placeholder YAML 이 발행되고 있다. launch 에 실측 경로를 넘겼는지 확인하라"고 **경고**한다.
  이 함정이 이 파이프라인에서 제일 위험하다.
- 종료 코드로 성공/실패를 알린다(0/1). 출력은 짧게.

## 참고해야 할 것 (왜 보는지 함께)

- `scripts/zed_fusion_bodytrack.py` — 재사용할 함수의 **정확한 시그니처와 호출 순서**.
  특히 `_open_sender` 인자 순서, warmup grab 이 `_init_fusion` **앞**에 와야 하는 이유(주석에
  명시됨), `retrieve_bodies` 에 `sl.FUSION_REFERENCE_FRAME.WORLD` 를 넘긴다는 점, `BONES_34`
  연결쌍, `_ok_keypoint` 의 유효성 기준.
- `ros2_ws/src/cbf_base_tf/cbf_base_tf/static_tf_node.py` — `/tf_static` 에 무엇이 어떤 이름으로
  실리는지(`base`→`zed1_link`/`zed2_link`/`fusion_world`), YAML 검증 규칙(coordinate_system,
  unit, quaternion norm). `check_tf_to_base.py` 의 손계산이 이 규칙과 어긋나면 안 된다.
- `ros2_ws/src/cbf_base_tf/launch/base_tf.launch.py` — `extrinsics` 인자 이름과 **기본값이
  placeholder** 라는 사실. 문서/검증 절차에 실측 경로를 명시해야 한다.
- `logs/base_cam_extrinsics.yaml` — 실측 산출물. `transforms` 리스트의
  parent/child/translation/rotation_quat 포맷 (읽기 전용).
- `scripts/base_tf_live.py` — 형제 스크립트를 import 재사용하면서 원본을 안 건드리는 **선례**.
  CLI 구성·헤드리스 가드·출력 톤을 참고한다.
- `logs/fusion_zed360.json` — `--config` 로 넘길 실사용 Fusion config (읽기 전용).

## 신경써야 할 것 (가드레일)

- **기존 검증 스크립트 수정 절대 금지**: `zed_fusion_bodytrack.py`, `zed_fusion_viz.py`,
  `zed_make_fusion_config.py`, `run_fusion.py`, `measure_base_cam.py`, `aruco_cube_datum.py`,
  `base_tf_live.py`, 그리고 `ros2_ws/src/cbf_base_tf/**` 전부. **import 와 build 만** 한다.
  수정이 필요해 보이면 구현을 멈추고 plan 을 `needs_revision` 으로 되돌린다.
- **브리지 안에서 base 변환을 하지 말 것.** `base_cam_extrinsics.yaml` 을 읽어 스켈레톤 좌표에
  곱하고 싶어지겠지만 하지 않는다. 그건 tf2 의 일이고, 이 plan 의 핵심 설계 결정이다.
  브리지는 `logs/base_cam_extrinsics.yaml` 을 **아예 열지 않는다**.
- **numpy 1.x 를 요구하는 ROS2 자산 import 금지**: `cv_bridge`, `sensor_msgs.msg.Image`,
  `sensor_msgs_py.point_cloud2`, `ros2_numpy` 류. conda 의 numpy 2.2.6 과 충돌한다.
  브리지가 다루는 것은 스켈레톤 좌표뿐이므로 필요 없다. **이미지·포인트클라우드는 퍼블리시하지
  않는다.**
- **numpy·pyzed·ROS2 를 재설치하거나 버전을 바꾸지 말 것.** 지금 조합이 검증된 조합이다.
  `pip install` / `conda install` / `apt install` / `rosdep install` 을 실행하지 않는다.
- **환경 격리 6개 규약을 어기지 말 것** (§환경 격리 규약). 특히 ROS2 환경이 잡힌 셸에서
  기존 ZED 스크립트를 실행하는 예시·문서·헬퍼를 만들지 않는다(역방향 오염). 그리고 환경
  검사는 **경고가 아니라 exit 3 하드 게이트**다 — "일단 돌려보고 안 되면 알겠지"로 두면
  가장 진단하기 어려운 반쯤 도는 상태가 생긴다.
- **`logs/**` 는 읽기 전용.** 브리지는 어떤 파일도 쓰지 않는다(JSONL 로깅은 bodytrack 담당,
  이번 범위 밖).
- **fps 30 고정**: `--fps` 가 30 이 아니면 exit 2. 2×HD720@60 은 이 리그에서 붕괴한다.
- **BODY_34 인덱스를 재정렬하지 말 것.** sender 는 BODY_18, 융합 결과는 BODY_34 다. PoseArray
  는 0~33 순서 그대로, 무효 관절도 자리를 비우지 않는다.
- **DELETEALL 마커를 빠뜨리지 말 것.** 없으면 사람이 프레임 밖으로 나가도 RViz 에 스켈레톤이
  영원히 남아 "잘 되는 것처럼" 보인다.
- **placeholder YAML 함정**: 실행·문서·검증 어디서든 `extrinsics:=` 에 **절대경로 실측 YAML**
  을 넘기는 것을 명시한다. 안 넘기면 조용히 항등변환이 발행된다.
- **샌드박스 한계**: codex 에는 카메라·GPU·디스플레이가 없다. 브리지의 **라이브 실행은 불가**
  하다. 대신 rclpy 는 돌아가므로 §검증의 정적/합성 항목은 **실제로 실행해서** 통과시켜야 한다
  (`--help` 만 찍고 넘어가지 말 것).

## 코드 스타일 (사용자 요청 — "AI 티 안 나게")

`measure_base_cam.py`·`base_tf_live.py` 와 **같은 결**로 쓴다. 표면(주석·레이아웃·네이밍)에만
적용하고 정확성 가드레일은 타협하지 않는다.

- 주석은 **한국어로 "왜"** 를 설명한다. 줄마다 기계적으로 되풀이하지 않는다. 프레임 규약,
  warmup grab 순서, NaN 유지 계약처럼 **헷갈리는 지점에만** 개념 메모를 단다.
- 논리 국면이 바뀌면 빈 줄로 끊는다. 과한 docstring(`Args:/Returns:/Raises:`) 금지 — 짧은 한 줄
  주석으로 대체. 타입힌트는 도움되는 곳만 가볍게.
- 과설계 금지: 불필요한 클래스 계층, 모든 줄을 감싸는 방어적 try/except 지양. 절차를 위에서
  아래로 곧게. 이모지·장식 구분선·과장 로그 금지. 네이밍은 짧고 실용적으로
  (`kp`, `msg`, `pub`, `bgr`).
- 파일 상단은 `#!/usr/bin/env python3` + `# -*- coding: utf-8 -*-`. shell 은 `#!/usr/bin/env bash`
  + `set -euo pipefail`.

## 이번에는 하지 않는 것 (non-scope)

- **오프라인 JSONL → base 좌표 변환기.** 실시간 경로로 대체됐다. 만들지 않는다.
- **프로세스 분리(IPC) 구조.** 소켓·UDP·공유메모리·파일 중계 등 conda 와 ROS2 를 별도
  프로세스로 갈라 잇는 방식은 **이번에 검토하지 않는다.** 관련 코드·옵션·주석·문서를 남기지
  않는다. 브리지는 한 프로세스다.
- **브리지 내부에서의 좌표 변환.** tf2 위임이 설계 결정이다.
- **커스텀 msg 패키지 / 다인(多人) 데이터 토픽.** `PoseArray` 는 대표 1명. 여러 명의 id-tagged
  데이터가 필요해지면 별도 plan.
- **이미지·깊이맵·포인트클라우드 퍼블리시.** numpy 2 충돌 위험 + 대역폭. 스켈레톤 좌표만.
- **JSONL 로깅·SVO 녹화·MP4 저장.** bodytrack/viz 담당. 브리지는 파일을 쓰지 않는다.
- **ZED 취득 타임스탬프 기반 stamp / 지연 측정.** 노드 시계 고정.
- **브리지를 ROS2 launch 파일로 묶기.** 실행 환경이 conda 라 launch 로 감싸면 환경이 꼬인다.
  런처 셸 스크립트로 충분하다.
- **base 정밀화(ChArUco 보드), 재측정, ZED360 재캘리브.** 좌표를 옮기는 일만 한다.
- **CBF 제어층, ε(t) 모델링, hand-eye(`T_base_cam`) 정밀화, 로봇 URDF 연동.** 스코프 밖.
- **numpy/pyzed/ROS2 버전 변경, 패키지 설치.**

## 근거

- 사용자와 확정 (2026-08-03): "결국 실시간 변환이 필요하다", "ZED 쪽 코드는 안 건드리는 게 좋다",
  "conda 에 numpy 다른 버전 안 까는 게 맞다".
- conda pyzed + 시스템 rclpy 공존은 **추정이 아니라 실행으로 확인**했다(§맥락 2). 이 사실이
  IPC 우회를 불필요하게 만들어 이 plan 을 파일 3개 규모로 줄였다.
- `base→fusion_world` static TF 와 BODY_34 융합 스켈레톤이 **양쪽 다 이미 동작**하므로,
  남은 일은 스켈레톤을 ROS2 토픽으로 올리는 것뿐이다. 변환은 tf2 가 공짜로 해준다.
- `zed_fusion_bodytrack.py` 가 모듈 레벨 함수 + `__main__` 가드 구조라 import 재사용이 성립한다.
  `base_tf_live.py` 가 같은 패턴으로 이미 성공했다.

## 검증

### 정적 / 합성 (codex, 샌드박스에서 **실제로 실행**해 통과시킬 것)

1. `python3 -m py_compile scripts/fusion_ros2_bridge.py scripts/check_tf_to_base.py`
2. `bash -n scripts/run_bridge.sh`
3. **빌드**: `cd ros2_ws && colcon build --packages-select cbf_base_tf` 성공 →
   `source install/setup.bash && ros2 pkg list | grep cbf_base_tf`
4. **static TF 발행 확인**: 실측 YAML 절대경로로 launch 한 뒤
   `ros2 run tf2_ros tf2_echo base fusion_world` 값이 `logs/base_cam_extrinsics.yaml` 의
   `fusion_world` 행(translation `[1.665, -1.167, -0.870]`, quat `[-0.0236, -0.0242, 0.9610, 0.2743]`)
   과 일치.
5. **★ TF 라운드트립**: `scripts/check_tf_to_base.py` 가 exit 0. 테스트 점의 tf2 변환 결과와
   손계산이 1e-6 이내로 일치해야 한다. **이 항목이 이 plan 의 좌표 정확성 증명이다.**
6. **placeholder 경고 동작 확인**: launch 를 인자 없이(기본 placeholder) 띄우고
   `check_tf_to_base.py` 를 돌리면 placeholder 경고가 나오는지.
7. `--help` 가 모든 옵션 노출. `--fps 60` 이 exit 2 로 거부되는지.
8. **환경 결합 확인**: `scripts/run_bridge.sh --help` 가 conda+ROS2 결합 상태에서 정상 출력.
   또한 그 환경에서 `python3 -c "import rclpy, pyzed.sl, numpy; print(rclpy.__file__, numpy.__version__)"`
   가 `/opt/ros/humble/...` 와 `2.2.6` 을 출력.
8-1. **★ 환경 격리 확인** (§환경 격리 규약):
   - `run_bridge.sh` 실행 **전후로 부모 셸의 `PYTHONPATH`·`LD_LIBRARY_PATH`·`AMENT_PREFIX_PATH`
     가 동일**한지 (`env | sort` diff 가 비어야 한다). 새어나가면 실패.
   - `conda activate` 없이, ROS2 를 source 하지 않은 **맨 셸**에서 `./scripts/run_bridge.sh --help`
     가 그대로 동작하는지.
   - **하드 게이트 동작**: ROS2 PYTHONPATH 없이 `conda run -n zed python3
     scripts/fusion_ros2_bridge.py --help` 를 직접 실행하면 **exit 3** 과 안내 문구가 나오는지.
   - 순수 conda 셸에서 기존 스크립트가 여전히 멀쩡한지:
     `conda run -n zed python3 scripts/aruco_cube_datum.py --selftest` 통과
     (역방향 오염이 없다는 확인. 카메라 불필요).
9. **재사용 심볼 import 확인**: 같은 환경에서 `from zed_fusion_bodytrack import (...)` 가 성공
   (카메라 없이 import 만으로 성공해야 한다 — 아니면 `__main__` 가드가 깨진 것).
10. **메시지 빌더 단위 검증**: 순수 함수에 가짜 34관절 배열을 넣어
    - 정상 관절만 → SPHERE_LIST 점 개수 34, LINE_LIST 점 개수 = 유효 뼈 × 2
    - 일부를 NaN 으로 → 해당 점과 그 점을 쓰는 뼈만 빠지고 나머지는 유지
    - PoseArray 는 항상 길이 34, NaN 자리는 NaN 유지
    - body 0명 → MarkerArray 는 DELETEALL 만, PoseArray 는 빈 배열, body_count = 0

### 라이브 (사용자, conda `zed` env + 하드웨어)

터미널 3개:

```bash
# A) static TF — 반드시 실측 YAML 절대경로를 넘긴다
source ros2_ws/install/setup.bash
ros2 launch cbf_base_tf base_tf.launch.py \
     extrinsics:=/home/pc/cbf_ws/logs/base_cam_extrinsics.yaml

# B) 브리지
./scripts/run_bridge.sh --config logs/fusion_zed360.json

# C) 확인
ros2 topic hz /human/skeleton_markers      # ≈30Hz
ros2 topic echo /human/body_count          # 사람 들어오면 1
rviz2                                      # Fixed Frame = base, MarkerArray 추가
```

판정 기준:

- Fixed Frame 을 `base` 로 두었을 때 스켈레톤이 **실제 사람이 서 있는 자리**에 그려지는가.
- 발이 바닥 높이에 오는가 (base 가 큐브 마커1 중심이므로 발은 대략 큐브 높이만큼 아래).
- 사람이 걸어가면 스켈레톤이 따라가고, 프레임 밖으로 나가면 **잔상 없이 사라지는가**(DELETEALL).
- Fixed Frame 을 `fusion_world` ↔ `base` 로 토글했을 때 스켈레톤이 **다른 자리로 점프하는가**
  (같은 자리면 placeholder YAML 을 발행 중이라는 뜻 — 함정에 걸린 것).
- 오차가 데시미터급으로 보이는 것은 **정상**이다(§맥락 5). 이번 plan 의 판정 대상이 아니다.
  방향이 뒤집히거나 축이 90° 틀어지는 것만 실패로 본다.

## 다음 단계

- **다인 데이터 토픽**: id 를 실을 수 있는 커스텀 msg 패키지(`cbf_msgs/HumanSkeletonArray`)를
  만들어 `PoseArray` 1명 제약을 푼다.
- **로봇 URDF / `T_base_robot` 연결**: base 는 지금 ArUco 큐브 기준이다. 실제 로봇 베이스와
  이어야 CBF 가 의미를 갖는다. 이 시점에 ArUco 데시미터 오차가 병목이 되므로 ChArUco 보드
  정밀화를 함께 검토한다.
- **ε(t) / CBF 안전층**: base 좌표 스켈레톤이 안정적으로 들어오면 그 위에 안전 제약을 얹는다.
- (선택) bodytrack 에 브리지를 붙여 **로깅과 실시간 발행을 동시에** 하는 통합 실행 경로.
  단, 기존 스크립트 수정이 필요하므로 별도 plan 으로 논의한다.
