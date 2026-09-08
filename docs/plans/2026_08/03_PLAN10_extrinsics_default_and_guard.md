---
date: 2026-08-03
task: cbf_base_tf 의 extrinsics 기본값을 실측 YAML 절대경로로 바꾸고, 세 transform 이 전부 항등이면 발행을 거부하는 가드를 추가한다. placeholder 파일은 .example.yaml 로 이름을 바꿔 오인을 없앤다
planner: Claude
executor: codex
status: draft
---

# PLAN10 — extrinsics 기본값 하드코딩 + 항등변환 거부 가드

> 파일: `docs/plans/2026_08/03_PLAN10_extrinsics_default_and_guard.md` (식별자 = PLAN10).

## 한 줄 결론

`cbf_base_tf` 의 `extrinsics` 기본값을 **실측 YAML 절대경로**
(`/home/pc/cbf_ws/logs/base_cam_extrinsics.yaml`)로 바꾸고, `static_tf_node` 가 **세 transform 이
전부 항등이면 에러로 종료**하도록 가드를 넣는다. 패키지 안의 placeholder 는
`base_cam_extrinsics.example.yaml` 로 이름을 바꾼다. **"경로를 안 넘겨서 조용히 항등변환이
발행되는" 함정을 구조적으로 없애는 것**이 목적이다.

## 왜 이 plan 이 필요한가

지금은 `ros2 launch cbf_base_tf base_tf.launch.py` 를 **인자 없이** 실행하면 패키지 share 안의
placeholder YAML(translation 전부 0, rotation 단위 quaternion)이 그대로 `/tf_static` 에 발행된다.

그 결과가 위험하다. `base` 와 `fusion_world` 가 **정확히 겹친다.** 좌표 변환이 아무것도
일어나지 않는데, RViz2 화면에는 스켈레톤이 멀쩡히 그려진다. **틀렸는데 맞아 보이는 상태**이고,
이 파이프라인에서 가장 진단하기 어려운 실패 모드다.

이건 가정이 아니라 **실제로 재현된 문제**다. 2026-08-03 PLAN09 검증 중:

- placeholder 발행 + 실측 YAML 대조 → `max_error=3.0155 m` (3미터 어긋남)
- 사용자도 실행 절차에서 `extrinsics:=` 를 매번 손으로 붙여야 하는 것을 불편해했다.

`measure_base_cam.py` 의 `--out` 기본값이 `logs/base_cam_extrinsics.yaml` 로 고정이라,
**재측정해도 경로가 바뀌지 않는다.** 즉 이 경로를 기본값으로 박아두면 편해지는 동시에
재측정 결과가 자동으로 반영된다 — 편의와 안전이 같은 방향이다.

다만 기본값만 바꾸면 부족하다. 누군가 다른 경로를 넘기거나 옛 빌드가 남아 있으면 여전히
항등변환이 나갈 수 있다. **경로와 무관하게 항등변환 자체를 거부**해야 함정이 사라진다.

## 지금까지 이어진 맥락 (이 plan 만 읽어도 되게 재서술)

프레임 표기: `T_A_B` = B 좌표의 점을 A 좌표로 보냄 (`p_A = T_A_B · p_B`).

### 1. 이 워크스페이스가 하는 일

ZED-M 2대(S/N `13870389`=zed1, `19321109`=zed2)를 ZED SDK Fusion 으로 묶어 가림에 강한 단일
휴먼 스켈레톤을 만든다. 좌표 규약은 전 구간 `RIGHT_HANDED_Z_UP_X_FWD` / METER
(X=전방, Y=좌, Z=상). 최종 소비자는 로봇 안전층(CBF)이다.

### 2. base 프레임과 static TF

- `base` 원점 = ArUco 큐브의 **마커 1 중심**, +X=큐브 정면, +Z=위, +Y=왼쪽.
- `scripts/measure_base_cam.py` 가 카메라를 보고 측정해 `logs/base_cam_extrinsics.yaml` 을 쓴다
  (`--out` 기본값이 이 경로다). 내용은 `base→zed1_link`, `base→zed2_link`,
  `base→fusion_world` 세 개의 `translation` + `rotation_quat` 뿐이다.
- 현재 실측값(2026-07-24 측정):

```yaml
coordinate_system: RIGHT_HANDED_Z_UP_X_FWD
unit: METER
transforms:
  - parent: base
    child: zed1_link
    translation: [1.24797179107, -1.46640275104, -0.185631819713]
    rotation_quat: [-0.011077844576, 0.0055644439553, 0.933732744523, 0.35775617413]
  - parent: base
    child: zed2_link
    translation: [1.45994621108, 1.19621488124, -0.168819352241]
    rotation_quat: [-0.0165157706714, -0.0227381852565, 0.902881644955, -0.428969625327]
  - parent: base
    child: fusion_world
    translation: [1.66469607918, -1.16719364747, -0.87003379229]
    rotation_quat: [-0.0235543031683, -0.0241980578936, 0.961045695186, 0.274318830123]
```

- ROS2 패키지 `ros2_ws/src/cbf_base_tf` 의 `static_tf_node.py` 가 이 YAML 을 읽어 `/tf_static`
  으로 세 개를 **리스트로 한 번에** 발행한다(따로 보내면 TF 트리가 잠깐 끊긴다). 이 노드는
  rclpy / tf2_ros / geometry_msgs / yaml 만 쓰고 OpenCV·pyzed 를 import 하지 않는다.
- 2026-08-03 에 처음 `colcon build --packages-select cbf_base_tf` 성공. `ros2_ws/{build,install,log}`
  는 `.gitignore` 에 있다.

### 3. 이 TF 를 쓰는 쪽 (PLAN09, 2026-08-03 완료)

`scripts/fusion_ros2_bridge.py` 가 융합 BODY_34 스켈레톤을 `frame_id: "fusion_world"` 로
`/human/skeleton_markers`(MarkerArray), `/human/skeleton_poses`(PoseArray),
`/human/body_count`(Int32) 에 30Hz 로 발행한다. **브리지는 base 변환을 직접 하지 않고
`base_cam_extrinsics.yaml` 을 열지도 않는다** — 변환은 전적으로 `/tf_static` + tf2 가 한다.
그래서 이 static TF 가 틀리면 **다운스트림 전체가 조용히 틀린다.**

### 4. 검증 도구 (재사용 대상)

`scripts/check_tf_to_base.py` (PLAN09 산출물, 시스템 ROS2 python 으로 실행, pyzed 불필요):

- tf2 로 `base ← fusion_world` 를 조회하고, `--extrinsics` YAML 을 직접 파싱해 손계산한 값과
  고정 테스트 점 5개로 대조한다. 최대 오차 `1e-6` 초과면 exit 1.
- 현재 `is_placeholder()` 함수가 있어 조회된 transform 이 항등이면 **경고만** 출력한다.
- 실측 발행 상태에서 `OK: base ← fusion_world, 5 points max_error=4.44e-16` 이 나온다.

### 5. 현재 파일 상태 (변경 대상)

**`ros2_ws/src/cbf_base_tf/launch/base_tf.launch.py`** — 기본값이 패키지 share 의 placeholder:

```python
default_yaml = get_package_share_directory("cbf_base_tf") + \
    "/config/base_cam_extrinsics.yaml"
```

**`ros2_ws/src/cbf_base_tf/cbf_base_tf/static_tf_node.py`** — `StaticTfNode.__init__` 안에서
같은 방식으로 기본 경로를 만들고, `declare_parameter("extrinsics", default_path)` 후
`load_transforms(path)` 로 읽어 바로 발행한다. `load_transforms` 는 coordinate_system / unit /
quaternion norm / child 중복을 검증하지만 **값이 항등인지는 보지 않는다.**

**`ros2_ws/src/cbf_base_tf/config/base_cam_extrinsics.yaml`** — placeholder. 세 transform 전부
`translation: [0.0, 0.0, 0.0]`, `rotation_quat: [0.0, 0.0, 0.0, 1.0]`. 파일 첫 줄 주석에
"실측 전 형식 확인용 placeholder다" 라고 적혀 있다.

**`ros2_ws/src/cbf_base_tf/setup.py`** — `data_files` 에 `("share/cbf_base_tf/config",
glob("config/*.yaml"))`. **glob 이라 파일명을 바꿔도 설치는 그대로 된다** (setup.py 수정 불필요).

### 6. 이식성은 고려하지 않는다 (사용자 확정)

절대경로 `/home/pc/cbf_ws/...` 를 추적 파일에 넣는다. 사용자가 **"다른 PC 에서 할 게 아니라
여기서만 한다"** 고 명시했다. 이 워크스페이스는 카메라 S/N 까지 코드에 박혀 있는 단일 리그다.
환경변수 폴백 같은 갈래를 만들지 않는다.

## 지금 기준 판단 (사용자와 확정)

1. **기본값을 실측 YAML 절대경로로 하드코딩한다.** `measure_base_cam.py` 의 출력 경로가
   고정이라, 재측정해도 자동으로 새 값이 반영된다. 편의와 안전이 같은 방향이다.
2. **항등변환 거부 가드가 진짜 해결책이다.** 기본값만 바꾸면 다른 경로를 넘겼을 때 함정이
   남는다. **경로와 무관하게** 세 transform 이 전부 항등이면 발행을 거부한다.
   명시적 탈출구(`allow_placeholder`)를 줄 때만 통과시킨다.
3. **placeholder 를 패키지에서 지우지는 않는다.** 형식 참조용으로 가치가 있다. 대신
   `base_cam_extrinsics.example.yaml` 로 **이름을 바꿔** 실측 파일로 오인할 수 없게 한다
   (`logs/base_cube_datum.example.json` 선례와 같은 규칙).
4. **실측 YAML 을 패키지 config/ 로 복사하지 않는다.** 실측 데이터가 두 벌 생기면 재측정 시
   복사·재빌드를 까먹는 **새로운 종류의 조용한 낡음**이 생긴다. 원본은 `logs/` 하나다.
5. **환경변수 폴백(`CBF_EXTRINSICS`)은 만들지 않는다.** 경로 결정 갈래가 늘어나면 "지금 어떤
   파일이 발행 중인가"를 추론하기 어려워진다. 갈래는 기본값 + 명시적 인자 둘로 충분하다.

## 이번에 할 것

`ros2_ws/src/cbf_base_tf` 안의 파일 **3개** 변경 + 문서 갱신. 새 파일은 만들지 않는다.

| 대상 | 변경 |
|---|---|
| `launch/base_tf.launch.py` | 기본값을 실측 YAML 절대경로로 |
| `cbf_base_tf/static_tf_node.py` | 기본 경로 동일하게 + **항등변환 거부 가드** + `allow_placeholder` 파라미터 |
| `config/base_cam_extrinsics.yaml` | → `config/base_cam_extrinsics.example.yaml` 로 rename |
| `README.md`, `docs/ros2_bridge_runbook.md` | 바뀐 사용법 반영 |

## 구현해야 할 것 (파일 단위)

### 1. `ros2_ws/src/cbf_base_tf/launch/base_tf.launch.py`

- 모듈 상수로 실측 경로를 둔다:
  `DEFAULT_EXTRINSICS = "/home/pc/cbf_ws/logs/base_cam_extrinsics.yaml"`
- `DeclareLaunchArgument("extrinsics", default_value=DEFAULT_EXTRINSICS, ...)` 로 바꾼다.
- `get_package_share_directory` 가 더 이상 필요 없으면 **import 를 지운다** (미사용 import 금지).
- `description` 문구를 갱신한다: "기본값은 measure_base_cam.py 실측 산출물. 다른 파일을 쓸
  때만 지정한다" 정도.
- 노드 이름(`cbf_base_static_tf`), `output="screen"`, 파라미터 전달 방식은 **그대로 둔다.**

### 2. `ros2_ws/src/cbf_base_tf/cbf_base_tf/static_tf_node.py`

**(a) 기본 경로**

- 모듈 상수 `DEFAULT_EXTRINSICS = "/home/pc/cbf_ws/logs/base_cam_extrinsics.yaml"` 을 두고
  `declare_parameter("extrinsics", DEFAULT_EXTRINSICS)` 로 바꾼다.
- `get_package_share_directory` 를 더 안 쓰면 import 를 지운다.
  (`package.xml` 의 `ament_index_python` 의존은 **그대로 둔다** — 제거 판단은 이번 범위 밖.)

**(b) 항등변환 거부 가드 (핵심)**

- `declare_parameter("allow_placeholder", False)` 를 추가한다.
- `load_transforms(path)` 결과를 받은 뒤, **모든** transform 이 항등인지 검사하는 순수 함수를
  하나 추가한다. 판정 기준:
  - translation 세 값 모두 `abs(v) <= 1e-12`
  - quaternion 의 x, y, z 모두 `abs(v) <= 1e-12` **그리고** `abs(abs(w) - 1.0) <= 1e-12`
    (`w = -1` 도 같은 회전이므로 절댓값으로 본다)
- **`all()` 이다. `any()` 가 아니다.** transform 하나가 우연히 항등인 것은 정상일 수 있다
  (예: 좌표계가 실제로 일치). **전부 항등일 때만** placeholder 로 판정한다.
- 전부 항등이고 `allow_placeholder` 가 False 면 **발행하지 않고 종료**한다. 메시지에
  ① 무슨 일이 일어났는지 ② 읽은 파일 경로 ③ 어떻게 고치는지 를 담는다. 예:

```
placeholder(전부 항등)로 보이는 YAML이라 발행을 거부합니다: <읽은 경로>
base와 fusion_world가 겹쳐서, 좌표 변환이 없는데도 정상처럼 보이게 됩니다.
실측 파일로 실행하세요:
  ros2 launch cbf_base_tf base_tf.launch.py extrinsics:=/home/pc/cbf_ws/logs/base_cam_extrinsics.yaml
형식 확인 목적이면 -p allow_placeholder:=true 를 붙이세요.
```

- `allow_placeholder` 가 True 면 **경고 로그를 남기고 발행한다**(조용히 통과시키지 않는다).

**(c) 종료 방식**

- 지금 `main()` 은 `StaticTfNode()` 생성 실패 시 예외가 그대로 올라가 **raw traceback** 이
  찍힌다. placeholder 거부와 파일 오류는 **사용자 실수**라 traceback 이 아니라 짧은 메시지 +
  **exit 2** 로 끝나야 한다.
- `main()` 에서 `ValueError` / `OSError` / `yaml.YAMLError` 와 placeholder 거부를 잡아
  `stderr` 로 메시지를 출력하고 `sys.exit(2)` 한다. 그 외 예기치 못한 예외는 그대로 둔다
  (숨기지 않는다).
- `rclpy.shutdown()` / `destroy_node()` 정리 순서는 지금 구조를 유지한다
  (`finally` 에서 이중 shutdown 이 나지 않게 주의).

**(d) 건드리지 말 것**

- `load_transforms` 의 기존 검증(coordinate_system, unit, quaternion norm, child 중복,
  parent==child 금지)과 에러 메시지 — 그대로 둔다.
- 세 transform 을 **리스트로 한 번에** `sendTransform` 하는 것 — 그대로 둔다
  (주석에 이유가 적혀 있다).
- 발행하는 frame 이름(`base`, `zed1_link`, `zed2_link`, `fusion_world`) — 그대로 둔다.

### 3. `config/base_cam_extrinsics.yaml` → `config/base_cam_extrinsics.example.yaml`

- **`git mv` 가 아니라 일반 `mv`** 로 옮긴다(이 환경에서 codex 는 git 을 쓰지 않는다).
- 파일 내용은 그대로 두되, 첫 줄 주석을 갱신한다: 형식 참조용이며 **이 파일로는 노드가
  발행을 거부한다**는 사실을 한 줄로 적는다.
- `setup.py` 는 `glob("config/*.yaml")` 이라 **수정 불필요**하다. 확인만 하고 넘어간다.
- 옛 이름이 빌드 산출물(`ros2_ws/install/`, `ros2_ws/build/`)에 남아 있을 수 있으므로
  **재빌드해서 새 이름만 설치되는지 확인**한다.

### 4. 문서 갱신

- `ros2_ws/src/cbf_base_tf/README.md` — 기본값이 실측 경로로 바뀐 것, placeholder 이름 변경,
  항등 거부 가드와 `allow_placeholder` 탈출구를 반영한다. 기존 3줄 구조를 유지하고 짧게.
- `docs/ros2_bridge_runbook.md` — 다음을 갱신한다:
  - §0-3 "가장 흔한 실수 — placeholder YAML": 이제 **노드가 거부하므로 조용히 틀리지 않는다**로
    성격이 바뀌었다. 경고문을 "이랬는데 이제 이렇게 막힌다" 로 고쳐 쓴다.
  - §2 터미널 A: `extrinsics:=` 없이 `ros2 launch cbf_base_tf base_tf.launch.py` 만으로
    동작하도록 예시를 바꾼다(명시 지정은 "다른 파일을 쓸 때"로 남긴다).
  - §6 트러블슈팅: placeholder 거부 메시지와 exit 2 를 항목으로 추가한다.
  - 나머지(RViz2 설정, 판정 기준, 토픽 계약)는 그대로 둔다.

## 참고해야 할 것 (왜 보는지 함께)

- `ros2_ws/src/cbf_base_tf/cbf_base_tf/static_tf_node.py` — 기존 `load_transforms` 검증 규칙과
  에러 메시지 톤. 새 가드를 **같은 결**로 쓴다(한국어, `%` 포매팅, 짧은 문장).
- `scripts/check_tf_to_base.py` 의 `is_placeholder()` — 항등 판정 기준이 이미 여기 있다
  (translation `<=1e-12`, quat x/y/z `<=1e-12`, `abs(abs(w)-1) <= 1e-12`). **같은 임계값을 쓴다.**
  두 곳의 기준이 다르면 한쪽만 잡는 상황이 생긴다.
- `ros2_ws/src/cbf_base_tf/setup.py` — `glob("config/*.yaml")` 이라 rename 후에도 설치되는지
  확인용. 수정 대상은 아니다.
- `logs/base_cam_extrinsics.yaml` — 새 기본값이 가리킬 실제 파일(읽기 전용). 존재·형식 확인용.
- `docs/ros2_bridge_runbook.md` — 갱신 대상이자, 사용자가 실제로 따라 하는 절차. 문서와 코드
  동작이 어긋나면 안 된다.

## 신경써야 할 것 (가드레일)

- **`any()` 가 아니라 `all()`.** transform 하나가 항등인 것은 정상일 수 있다. **셋 전부**
  항등일 때만 거부한다. 이걸 틀리면 정상 설정에서도 노드가 안 뜬다.
- **판정 임계값을 `check_tf_to_base.py` 와 일치시킨다.** 새 상수를 발명하지 말 것.
- **traceback 대신 짧은 메시지 + exit 2.** 사용자 실수 경로에서 파이썬 스택을 토하지 않는다.
  단, 예기치 못한 예외까지 잡아 삼키지는 말 것.
- **`logs/**` 는 읽기 전용.** 이번 작업에서 `logs/` 아래 어떤 파일도 만들거나 고치지 않는다.
- **ZED 쪽 스크립트 전부 무수정**: `scripts/` 아래 `zed_*.py`, `run_fusion.py`,
  `measure_base_cam.py`, `aruco_cube_datum.py`, `base_tf_live.py`,
  `fusion_ros2_bridge.py`, `run_bridge.sh`, `check_tf_to_base.py`. 이번 범위는
  `ros2_ws/src/cbf_base_tf` 와 문서뿐이다.
- **PLAN09 산출물의 동작을 바꾸지 말 것.** 특히 `check_tf_to_base.py` 는 이번에 수정하지
  않는다(§검증에서 **그대로** 재사용해 회귀를 확인해야 하므로).
- **frame 이름·발행 방식 유지.** `base`/`zed1_link`/`zed2_link`/`fusion_world`, 리스트 일괄
  `sendTransform`, `/tf_static` latch 동작을 바꾸지 않는다. 다운스트림이 여기에 의존한다.
- **잔존 프로세스 주의(검증 시).** `static_tf_node` 가 살아 있으면 `/tf_static` 이 계속
  발행돼 새 실행 결과와 섞인다. 검증 각 단계 전에 `pgrep -f static_tf_node` 로 확인하고
  정리한다. (2026-08-03 검증에서 실제로 이것 때문에 결과가 뒤집혀 나온 적이 있다.)
- **재빌드 필수.** 이 패키지는 ament_python 이라 소스만 고치면 `install/` 의 옛 사본이 돈다.
  검증 전에 반드시 `colcon build --packages-select cbf_base_tf` 를 다시 한다.

## 코드 스타일 (사용자 요청 — "AI 티 안 나게")

기존 `static_tf_node.py` 와 **같은 결**로 쓴다.

- 주석은 **한국어로 "왜"** 를 설명한다. 줄마다 되풀이하지 않는다. 항등 판정처럼 의도가
  안 드러나는 곳에만 한 줄 단다(특히 `all()` 인 이유).
- 문자열 포매팅은 기존 파일과 같이 `%` 를 쓴다. f-string 으로 갈아엎지 않는다.
- 과한 docstring(`Args:/Returns:/Raises:`) 금지. 짧은 한 줄 주석으로.
- 불필요한 클래스·추상화 금지. 항등 판정은 **모듈 레벨 순수 함수 하나**로 충분하다.
- 이모지·장식 구분선·과장 로그 금지. 네이밍은 짧고 실용적으로.

## 이번에는 하지 않는 것 (non-scope)

- **환경변수 폴백(`CBF_EXTRINSICS`) 등 경로 결정 갈래 추가.** 기본값 + 명시 인자 둘뿐이다.
- **실측 YAML 을 패키지 `config/` 로 복사.** 실측 원본은 `logs/` 하나다.
- **placeholder 파일 삭제.** 이름만 바꾼다.
- **`check_tf_to_base.py` 수정.** 회귀 확인용으로 그대로 둔다. (환경 미설정 시
  `ModuleNotFoundError` 가 raw 로 뜨는 문제는 인지하고 있으나 **별도 plan**으로 다룬다.)
- **`fusion_ros2_bridge.py` / `run_bridge.sh` 수정.** 이번과 무관하다.
- **브리지에 ZED360 캘리브 게이트 추가.** `run_fusion.py` 에 있는 게이트가 브리지에는 없다는
  것을 인지하고 있으나 **별도 plan**으로 다룬다.
- **`package.xml` 의존성 정리, 커스텀 msg, 다인 토픽, 로봇 URDF 연결.**
- **base 정밀화(ChArUco).** 측정 정확도는 이번 주제가 아니다.

## 근거

- 사용자와 확정(2026-08-03): "extrinsic 도 하드코딩하는 게 편하지 않나", "다른 PC 에 할 거
  아님. 여기서 할 거니까 그건 상관없고".
- 함정이 실증됨: PLAN09 검증에서 placeholder 발행 상태로 실측 YAML 과 대조하니
  `max_error=3.0155 m`. 화면상으로는 정상으로 보이는 상태였다.
- `measure_base_cam.py --out` 기본값이 `logs/base_cam_extrinsics.yaml` 고정 → 경로 하드코딩이
  재측정을 방해하지 않고 오히려 자동 반영시킨다.
- 항등 판정 로직은 `check_tf_to_base.py:is_placeholder()` 에 이미 검증된 형태로 존재한다 →
  같은 기준을 노드 쪽에도 심어 "탐지"에서 "차단"으로 올린다.

## 검증

### 정적 / 실행 (codex, 하드웨어 없이 **실제로 실행**해 통과시킬 것)

각 단계 전에 `pgrep -f static_tf_node` 로 잔존 프로세스가 없는지 확인한다.

1. `python3 -m py_compile ros2_ws/src/cbf_base_tf/cbf_base_tf/static_tf_node.py
   ros2_ws/src/cbf_base_tf/launch/base_tf.launch.py`
2. **재빌드**: `cd ros2_ws && colcon build --packages-select cbf_base_tf` 성공.
   `ls install/cbf_base_tf/share/cbf_base_tf/config/` 에 **`base_cam_extrinsics.example.yaml`
   만 있고 옛 이름은 없어야** 한다.
3. **★ 인자 없이 실행 → 실측값이 발행돼야 한다**:
   `ros2 launch cbf_base_tf base_tf.launch.py` (인자 없음)
   → `ros2 run tf2_ros tf2_echo base fusion_world` 가
   translation `[1.665, -1.167, -0.870]`, quat `[-0.024, -0.024, 0.961, 0.274]` 를 출력.
   **이게 이번 plan 의 핵심 성공 조건이다.**
4. **회귀**: 같은 상태에서 `python3 scripts/check_tf_to_base.py` 가
   `OK: ... max_error=` 와 `1e-6` 이하를 출력하고 exit 0.
   (`check_tf_to_base.py` 는 수정 대상이 아니므로 **그대로** 통과해야 한다.)
5. **★ 항등 거부**: placeholder 를 명시 지정해 실행
   `ros2 launch cbf_base_tf base_tf.launch.py extrinsics:=<설치된 .example.yaml 절대경로>`
   → 노드가 **발행하지 않고 exit 2**, 위에서 정한 안내 메시지 출력.
   → 이때 `ros2 topic echo /tf_static --once` 가 **아무것도 못 받는지** 확인
     (거부인데 발행됐다면 가드가 무의미하다).
6. **탈출구**: `-p allow_placeholder:=true` (또는 launch 를 통한 동등한 방법)로 같은 파일을
   실행하면 **경고 로그와 함께 발행**되는지.
7. **오탐 없음(`all()` 확인)**: 임시 YAML 을 하나 만들어 **세 transform 중 하나만** 항등,
   나머지 둘은 실측값으로 채운 뒤 실행 → **정상 발행**돼야 한다(거부되면 `any()` 로 짠 것).
   임시 파일은 `/tmp` 에 만들고 **`logs/` 에는 만들지 않는다.**
8. **파일 오류 경로**: 없는 경로를 넘기면 traceback 이 아니라 짧은 메시지 + exit 2.
9. 문서 갱신 확인: `README.md` 와 `docs/ros2_bridge_runbook.md` 의 명령 예시가 실제 동작과
   일치하는지 눈으로 대조(특히 runbook §0-3, §2 터미널 A, §6).

### 라이브 (사용자, 하드웨어)

- `docs/ros2_bridge_runbook.md` 절차대로 터미널 A 를 **인자 없이** 띄우고, 브리지 + RViz2 로
  스켈레톤이 `base` 기준 제자리에 오는지 확인.
- Fixed Frame `fusion_world` ↔ `base` 토글 시 스켈레톤이 점프하는지(정상).

## 다음 단계

- **브리지 ZED360 캘리브 게이트**: `run_fusion.py` 에는 "Fusion 실행 전 ZED360 재캘리브 강제"
  게이트가 있는데 `run_bridge.sh` 에는 없다. 카메라가 움직였는데 낡은 config 로 조용히 도는
  경로가 남아 있다. 별도 plan 으로 논의.
- **`check_tf_to_base.py` 환경 가드**: 브리지처럼 rclpy import 실패 시 친절한 안내 + 명확한
  종료 코드를 주도록. 지금은 raw `ModuleNotFoundError` 가 뜬다.
- 다인 id 데이터 토픽(커스텀 msg), 로봇 URDF·`T_base_robot` 연결.
