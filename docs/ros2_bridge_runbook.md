# ros2_bridge_runbook.md — Fusion 스켈레톤 ROS2 브리지 실행·확인 절차

PLAN09 산출물(`scripts/fusion_ros2_bridge.py`)을 실제로 띄우고 RViz2 로 확인하는 절차.
**한 줄 요약**: 터미널 3개(static TF / 브리지 / RViz2)를 띄우고, RViz2 의 Fixed Frame 을
`base` 로 두면 사람 스켈레톤이 로봇 기준 좌표에 그려진다.

관련 문서: 설계 근거는 `docs/plans/2026_08/03_PLAN09_fusion_ros2_bridge.md`,
현재 상태는 `docs/memory.md`, 그날 작업 기록은 `docs/worklog/2026-08-03.md`.

---

## 0. 준비 확인 (처음 한 번만)

### 0-1. ROS2 패키지 빌드

`cbf_base_tf` 가 빌드돼 있어야 한다. 이미 돼 있으면 건너뛴다.

```bash
cd /home/pc/cbf_ws/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select cbf_base_tf
source install/setup.bash
ros2 pkg list | grep cbf_base_tf        # cbf_base_tf 가 나와야 한다
```

빌드 산출물(`build/`, `install/`, `log/`)은 `.gitignore` 에 들어 있다.

### 0-2. 실측 extrinsics YAML 존재 확인

```bash
cat /home/pc/cbf_ws/logs/base_cam_extrinsics.yaml
```

`base→zed1_link`, `base→zed2_link`, `base→fusion_world` 세 항목이 **0 이 아닌 값**으로
들어 있어야 한다. 없거나 전부 0이면 `scripts/measure_base_cam.py` 로 다시 측정해야 한다.

### 0-3. ⚠ 가장 흔한 실수 — placeholder YAML

`ros2_ws/src/cbf_base_tf/config/base_cam_extrinsics.yaml` 은 **형식 예시용 placeholder** 로
translation 이 전부 0, rotation 이 단위 quaternion 이다. launch 의 **기본값이 이것**이라,
`extrinsics:=` 를 안 넘기면 `fusion_world` 가 `base` 와 정확히 겹친다.

**변환이 아예 안 일어나는데 화면상으로는 잘 되는 것처럼 보인다.** 이 문서의 모든 명령에서
**실측 YAML 절대경로를 반드시 넘긴다.**

---

## 1. 환경 구조 (왜 터미널을 나누나)

이 시스템에는 파이썬 환경이 **두 개**이고, 프로세스마다 필요한 게 다르다.

| 프로세스 | 필요한 것 | 환경 |
|---|---|---|
| static TF 노드 | rclpy, tf2, yaml | **시스템 ROS2 Humble** (pyzed 불필요) |
| 브리지 | pyzed + rclpy 둘 다 | **conda `zed` + ROS2 경로** (런처가 결합) |
| RViz2 | rclpy | **시스템 ROS2 Humble** |

conda `zed`(Python 3.10.20)와 시스템 ROS2(Python 3.10.12)는 **한 프로세스에서 공존한다**
(2026-08-03 실측 확인). 다만 그 결합은 `scripts/run_bridge.sh` **서브셸 안에서만** 일어나고
부모 셸로 새지 않는다.

**따라서 브리지 터미널에서는 `conda activate` 도 `source setup.bash` 도 하지 않는다.**
런처가 알아서 한다. 오히려 미리 해두면 환경이 섞인다.

---

## 2. 실행 — 터미널 3개

### 터미널 A — static TF 발행

```bash
cd /home/pc/cbf_ws
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash

ros2 launch cbf_base_tf base_tf.launch.py \
     extrinsics:=/home/pc/cbf_ws/logs/base_cam_extrinsics.yaml
```

정상이면 `static TF 3개 발행: /home/pc/cbf_ws/logs/base_cam_extrinsics.yaml` 로그가 뜬다.
`/tf_static` 은 latch 되므로 **한 번만 발행하고 그대로 떠 있으면 된다.**

> `ros2 launch` 대신 `ros2 run cbf_base_tf static_tf_node --ros-args -p extrinsics:=<절대경로>`
> 도 동일하게 동작한다.

### 터미널 B — 브리지 (카메라 2대 필요)

```bash
cd /home/pc/cbf_ws
./scripts/run_bridge.sh --config logs/fusion_zed360.json
```

**맨 셸에서 그대로 실행한다.** `conda activate zed` 하지 않는다.

시작하면 먼저 환경 검사 한 줄이 나온다:

```
환경 확인: rclpy=/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/__init__.py numpy=2.2.6 (conda zed) pyzed=...
config cameras: [13870389, 19321109]
bridge: sender=BODY_18 fused=BODY_34 frame=fusion_world
  sender S/N 13870389 publishing (HD720 @ 30fps)
  sender S/N 19321109 publishing (HD720 @ 30fps)
  subscribed S/N ...
frames=312 ~29.8fps live=1 cameras=2
```

`live=` 가 현재 융합된 사람 수다. 사람이 들어오면 1 이 된다.

주요 옵션 (기본값이 이 리그에 맞춰져 있어 보통 손댈 일 없다):

| 옵션 | 기본 | 설명 |
|---|---|---|
| `--config` | (필수) | ZED360 Fusion config. 실사용 `logs/fusion_zed360.json` |
| `--fps` | 30 | **30 고정.** 다른 값이면 exit 2 (2×HD720@60 은 이 리그에서 붕괴) |
| `--res` | HD720 | 해상도 |
| `--depth` | NEURAL | `NEURAL_LIGHT`, `PERFORMANCE` 로 낮출 수 있음 |
| `--conf` | 40 | sender 검출 신뢰도 임계값 |
| `--min-keypoints` | 7 | 융합 최소 관절 수 |
| `--min-cameras` | 1 | 융합 최소 카메라 수 |
| `--smoothing` | 0.1 | 스켈레톤 스무딩 |
| `--duration` | 0 | 초. 0 = Ctrl-C 까지 |
| `--frame-id` | fusion_world | 발행 헤더 프레임. **바꾸지 말 것** |
| `--topic-prefix` | /human | 토픽 접두사 |
| `--marker-lifetime` | 0.2 | 초. 마커 잔상 제거 주기 |

### 터미널 C — RViz2

```bash
source /opt/ros/humble/setup.bash
source /home/pc/cbf_ws/ros2_ws/install/setup.bash
rviz2
```

---

## 3. RViz2 설정 (처음 한 번, 이후 저장해서 재사용)

### 3-1. Fixed Frame

왼쪽 **Displays** 패널 맨 위 → **Global Options** → **Fixed Frame** 을 **`base`** 로 바꾼다.

여기가 이 시스템의 핵심이다. `base` 로 두면 tf2 가 `base ← fusion_world` 변환을 자동으로
적용해서, **브리지는 카메라 좌표로 보냈는데 화면에는 로봇 좌표로 그려진다.**

### 3-2. Display 추가

좌하단 **Add** 버튼 → **By topic** 탭에서 고르는 게 제일 쉽다.

| Display | 토픽 | 용도 |
|---|---|---|
| **MarkerArray** | `/human/skeleton_markers` | **사람 뼈대 (이게 메인)** |
| **TF** | — (By display type 에서 추가) | 좌표축 3개 확인 |
| PoseArray | `/human/skeleton_poses` | (선택) 관절 34개 화살표 |

**TF** display 를 켜면 `base`, `zed1_link`, `zed2_link`, `fusion_world` 네 좌표축이 보인다.
`base` 가 큐브 자리에, `zed1/zed2` 가 카메라 자리에 있으면 배치가 맞는 것이다.

> **PoseArray 는 켜도 안 켜도 된다.** 무효 관절이 NaN 으로 들어 있어서 RViz 가 경고를 낼 수
> 있다. 이건 의도된 설계다(소비자가 `isfinite` 로 거르는 계약). 보기용은 MarkerArray 다.

### 3-3. 보기 편하게

- **Views** 패널 → Type 을 `Orbit` 으로, Target Frame 을 `base` 로.
- **Grid** display 를 추가하면 바닥 기준이 생겨서 발 높이를 가늠하기 쉽다.
- 설정이 끝나면 **File → Save Config As** 로 저장해두면 다음에 그대로 뜬다.
  (저장 경로는 저장소 밖 또는 `~/.rviz2/` 를 권장 — `logs/` 는 건드리지 않는다.)

---

## 4. 판정 — 무엇을 보면 성공인가

### 4-1. 터미널로 먼저 확인 (RViz 없이)

```bash
source /opt/ros/humble/setup.bash
ros2 topic hz /human/skeleton_markers    # ≈30 Hz
ros2 topic echo /human/body_count        # 사람 들어오면 data: 1
ros2 run tf2_ros tf2_echo base fusion_world
```

`tf2_echo` 가 아래와 **같은 값**이면 실측 TF 가 제대로 발행 중이다:

```
- Translation: [1.665, -1.167, -0.870]
- Rotation: in Quaternion (xyzw) [-0.024, -0.024, 0.961, 0.274]
- Rotation: in RPY (degree) [-3.409, 1.834, 148.084]
```

전부 0 / 단위 quaternion 이 나오면 **placeholder 함정에 걸린 것**이다 (§0-3).

### 4-2. 자동 채점기

카메라 없이도 돌아간다. 터미널 A 가 떠 있는 상태에서:

```bash
source /opt/ros/humble/setup.bash
cd /home/pc/cbf_ws
python3 scripts/check_tf_to_base.py --extrinsics logs/base_cam_extrinsics.yaml
```

기대 출력:

```
OK: base ← fusion_world, 5 points max_error=4.44e-16
```

허용 기준은 `1e-6` 이다. 이 도구는 tf2 가 계산한 결과와 YAML 을 직접 손계산한 결과를
테스트 점 5개로 대조한다. 서로 베낄 수 없는 두 경로라 **일치하면 변환이 실제로 맞는 것**이다.

실패 케이스와 의미:

| 출력 | 의미 |
|---|---|
| `warning: placeholder YAML이 발행되고 있습니다` | launch 에 실측 경로를 안 넘김 (§0-3) |
| `error: TF/YAML 변환 불일치: ... max_error=3.0155` | 발행 중인 TF 와 YAML 이 다름 (보통 placeholder 발행 중) |
| `error: base ← fusion_world TF를 5초 안에 찾지 못했습니다` | 터미널 A 가 안 떠 있음 |

### 4-3. RViz2 육안 판정

- [ ] Fixed Frame `base` 에서 스켈레톤이 **실제 사람이 서 있는 자리**에 그려진다.
- [ ] 발이 바닥 근처에 온다 (base 가 큐브 마커1 중심이므로 발은 큐브 높이만큼 아래).
- [ ] 사람이 걸으면 스켈레톤이 따라간다.
- [ ] 사람이 화면 밖으로 나가면 **잔상 없이 사라진다** (DELETEALL 마커 동작).
- [ ] **★ 토글 테스트**: Fixed Frame 을 `fusion_world` ↔ `base` 로 바꿔본다.
      → **스켈레톤이 휙 점프하면 정상.** 변환이 실제로 일어나고 있다는 뜻.
      → **제자리에 그대로면 placeholder 함정**이다.

### 4-4. 정상인데 이상해 보이는 것

- **위치가 10~20 cm 어긋나 보임** — 정상이다. ArUco 기반 base 측정이 이 리그(10 cm 태그 @
  1.9 m)에서 **데시미터급**인 게 알려진 한계다. 코드 버그가 아니라 측정 기하의 문제이며,
  ChArUco 보드 정밀화는 CBF 연동 시점 과제로 보류 중이다.
- **관절 몇 개가 빠져 보임** — 정상이다. 가려진 관절은 무효 처리해서 안 그린다.
  그 관절을 쓰는 뼈도 함께 빠진다.
- **판정 기준은 "방향이 맞는가"** 다. 축이 90° 틀어지거나 좌우가 뒤집히면 실패,
  수 cm~수십 cm 오차는 이번 단계의 판정 대상이 아니다.

---

## 5. 종료 / 정리

각 터미널에서 `Ctrl-C`. 브리지는 SIGINT 를 받아 Fusion → 카메라 → 노드 순으로 정리한다.

프로세스가 남았는지 확인:

```bash
pgrep -af "static_tf_node|fusion_ros2_bridge|rviz2"
```

> **주의**: static TF 노드가 살아 있으면 `/tf_static` 이 계속 발행돼서, 다음에 다른 YAML 로
> 띄웠을 때 **두 값이 섞인다.** 검사 결과가 이상하면 먼저 잔존 프로세스부터 확인한다.
> (실제로 검증 중에 이것 때문에 결과가 뒤집혀 나온 적이 있다.)

---

## 6. 트러블슈팅

| 증상 | 원인 / 조치 |
|---|---|
| `error: 브리지 실행 환경 검사를 통과하지 못했습니다` + **exit 3** | 브리지를 직접 실행했다. **`./scripts/run_bridge.sh` 로 실행**한다. 출력된 numpy/pyzed/rclpy 경로를 보면 뭐가 빠졌는지 알 수 있다. |
| `--fps 60` 이 **exit 2** | 의도된 동작. 이 리그는 2×HD720@60 에서 붕괴한다. 30 으로 실행한다. |
| RViz 에 아무것도 안 보임 | ① Fixed Frame 이 `base`/`fusion_world` 가 아닌 다른 값인지 ② 터미널 A(static TF)가 떠 있는지 ③ `ros2 topic hz` 로 브리지가 실제 발행 중인지 |
| 스켈레톤이 원점에 딱 붙어 있음 | placeholder 함정 (§0-3). 터미널 A 를 실측 절대경로로 다시 띄운다. |
| 사람이 나갔는데 스켈레톤이 남음 | `--marker-lifetime` 을 줄여본다. DELETEALL 이 매 프레임 나가므로 보통은 안 생긴다. |
| `sender S/N ... open failed` | 다른 프로그램(ZED Studio 등)이 카메라를 잡고 있다. 닫고 재실행. USB 연장선을 쓰고 있으면 **PC 에 직결**한다. |
| fps 가 30 에 한참 못 미침 | USB 컨트롤러가 하나뿐이라 다른 USB 장치와 대역폭을 나눠 쓰면 떨어진다. `--depth NEURAL_LIGHT` 로 낮춰본다. |
| `ros2` 명령이 없다 | 해당 터미널에서 `source /opt/ros/humble/setup.bash` 를 안 했다. (단 **브리지 터미널은 하면 안 된다**) |

---

## 7. 발행되는 토픽 계약

| 토픽 | 타입 | 내용 |
|---|---|---|
| `/human/skeleton_markers` | `visualization_msgs/MarkerArray` | 전원. `ns="body_<id>"`, id 0=관절 SPHERE_LIST, id 1=뼈 LINE_LIST. 맨 앞에 DELETEALL |
| `/human/skeleton_poses` | `geometry_msgs/PoseArray` | **대표 1명**의 BODY_34 관절 34개. 인덱스 고정 |
| `/human/body_count` | `std_msgs/Int32` | 현재 융합된 사람 수 |

전부 `frame_id = "fusion_world"`, 좌표 규약은 `RIGHT_HANDED_Z_UP_X_FWD` / METER
(X=전방, Y=좌, Z=상).

**소비자 계약 2가지 (다운스트림 노드를 짤 때 반드시 지킬 것):**

1. **무효 관절은 NaN 이다.** 0 으로 치환하지 않았다 — 그러면 원점에 가짜 관절이 생기고,
   건너뛰면 BODY_34 인덱스가 밀린다. **`math.isfinite` 로 거르고 쓴다.**
2. **PoseArray 는 한 명분이다.** `PoseArray` 에 body id 를 실을 자리가 없어서 `body_list[0]`
   하나만 넣는다. 사람이 2명 이상이면 브리지가 최초 1회 경고를 낸다. 여러 명이 필요하면
   `MarkerArray` 를 쓰거나, 커스텀 msg 패키지를 만드는 다음 plan 을 기다린다.

base 좌표가 필요한 노드는 **직접 변환하지 말고** tf2 를 쓴다:

```python
from tf2_ros import Buffer, TransformListener
# ...
p_base = buffer.transform(msg, "base")
```

좌표계 single source of truth 는 `/tf_static` 하나다. 노드마다 YAML 을 읽어 곱하면
카메라를 옮겼을 때 한쪽만 낡는다.

---

## 8. 알려진 제약 (이번 단계 범위 밖)

- **base 정확도 데시미터급** — ArUco 측정 한계. 정밀화는 ChArUco 보드(A3~A2) 필요.
  로봇 좌표 연동 시점 과제.
- **다인 데이터 토픽 없음** — PoseArray 1명 제약. 커스텀 msg 필요.
- **이미지·포인트클라우드 발행 안 함** — conda 의 numpy 2.2.6 과 ROS2 의 numpy 1.x 자산
  (`cv_bridge` 등)이 충돌할 수 있어 의도적으로 제외했다. 스켈레톤 좌표만 보낸다.
- **타임스탬프는 노드 시계** — ZED 취득 시각 기반 지연 분석은 미구현.
- **JSONL 로깅 없음** — 브리지는 파일을 쓰지 않는다. 로깅이 필요하면
  `scripts/zed_fusion_bodytrack.py` 를 쓴다(단 카메라를 동시에 못 잡으므로 따로 실행).
