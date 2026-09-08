# overview.md — cbf_ws

아키텍처·개념 문서. "지금 어디" 는 `docs/memory.md`, "어떻게 갈지" 는 `docs/plans/`,
이 파일은 **"이 시스템이 무엇인가"** 를 담는다.

## 목적

사람 주변에서 동작하는 로봇의 **안전층(CBF)** 에 넣을 **신뢰할 수 있는 사람 상태(포즈)** 를 만든다.
단일 카메라는 앉거나 몸이 겹치는 상황에서 **반대쪽 관절이 통째로 소실**된다(실측에서 오른손목
신뢰도 median 0). 안전 신호가 소비하는 건 **머리 + 양 손목**이라 한 관절만 비어도 문제가 된다.
그래서 **ZED-M 2대를 사람의 좌/우에 놓고 SDK Fusion 으로 융합**해, 한쪽이 가린 관절을 반대쪽이
메우는 **가림-강건 단일 스켈레톤 + 관절별 신뢰도**를 얻는 것이 이 워크스페이스의 현재 범위다.

## 전체 흐름

```text
ZED-M #1 (S/N 13870389)            ZED-M #2 (S/N 19321109)
  grab → body tracking(BODY_18)      grab → body tracking(BODY_18)
  start_publishing (shared memory)   start_publishing (shared memory)
        \                                   /
         └──────── sl.Fusion.subscribe(serial, comm, pose) ────────┘
                            ▲
                            │ extrinsic(카메라 간 상대 pose)
                            │   ← ZED360 캘리브 결과 (logs/fusion_zed360.json)
                            │     (logs/fusion_manual.json 은 placeholder)
                            ▼
                  fusion.process() → retrieve_bodies()
                            │
                  융합 스켈레톤 BODY_34 @ fusion world frame
                            │
        ┌───────────────────┼────────────────────┐
        ▼                   ▼                    ▼
  JSONL 로그          라이브 뷰어(창 2개)        (향후)
  logs/fusion_*.jsonl  ├ cameras (raw 2D)        hand-eye → robot base
  kp + per-joint conf  └ world view              → ε(t) → CBF 안전층
  + timestamp            top/front/side/orbit
```

별도의 1회성 base 정합 경로는 라이브 Fusion 프로세스와 분리되어 있다.

```text
ArUco 큐브 데이텀 ─┐
                    ├─ measure_base_cam.py (conda zed, 순차 카메라 open)
ZED360 fusion config┘       │
                            ▼
                  base_cam_extrinsics.yaml
                            │ 파일만 전달
                            ▼
             cbf_base_tf (system ROS2 Humble)
                            │
                /tf_static: base → zed1_link
                            base → zed2_link
                            base → fusion_world
```

실행 진입점은 **`scripts/run_fusion.py`** 다. Fusion 을 켜기 전에 **ZED360 캘리브를 강제**하고
(신선도·serial 검증), 통과해야 뷰어/파이프라인을 띄운다.

위 그림의 **"(향후) hand-eye → robot base"** 구간(융합 world → 로봇 베이스 정합)은 문서 2개가 담당한다.
아직 **plan 이 아니다** (승인 대상 아님).

| 문서 | 성격 | 언제 읽나 |
|---|---|---|
| [robot_base_registration.md](robot_base_registration.md) | **설계 결정** — 압축·주관적 | "그래서 뭘 할 건데" |
| [robot_base_registration_research.md](robot_base_registration_research.md) | **원자료** — 망라적·중립적 | "근거가 정확히 뭔데", 버린 선택지 재검토, 미확인 항목 |

**ZED360 월드 프레임의 실측 해부**(원점 = 카메라 1번 아래 바닥, **yaw 만 캘리브**, roll/pitch 는
IMU)와 SDK 사실 정리는 research 문서 §1–2 가 단일 출처다.

## 구성 요소

| 모듈/파일 | 역할 |
|---|---|
| `scripts/run_fusion.py` | **진입점.** ZED360 캘리브 게이트(강제) → config 검증 → 아래 대상 실행 |
| `scripts/zed_fusion_viz.py` | 라이브 뷰어. 카메라 raw 2D(BODY_18) 오버레이 + world 뷰(BODY_34, top/front/side/orbit) |
| `scripts/zed_fusion_bodytrack.py` | 융합 파이프라인 + JSONL 로깅 + top-down MP4. sender/fusion 헬퍼의 원본 |
| `scripts/zed_make_fusion_config.py` | 수동/측정 pose → ZED360 호환 fusion config JSON (부트스트랩용) |
| `scripts/zed_check.py` | 카메라 인식·단독 스트리밍 점검 (순차 open) |
| `scripts/aruco_cube_datum.py` | 큐브 데이텀 로드, optical→body 변환, pose 평균 등 순수 수학 |
| `scripts/measure_base_cam.py` | 큐브 마커로 base 기준 ZED pose 측정 → static TF YAML 저장 |
| `scripts/zed_bodytrack_min.py` / `zed_bodytrack_viz.py` | 단일 카메라 로그 / 2D 오버레이 (레퍼런스) |
| `scripts/viz_pose_log.py` | 저장된 포즈 로그 → 스켈레톤 영상 |
| `scripts/codex_*.sh` | 하네스: 승인 게이트·스냅샷·codex headless 실행·웹 브리지 |
| `ros2_ws/src/cbf_base_tf/` | 측정 YAML을 읽어 base 기준 세 static TF를 발행하는 ament_python 패키지 |
| `logs/` | 실측 로그(.jsonl), .svo2, .mp4, 캘리브 config. **수정 금지** |

## 핵심 설계 결정

- **SDK Fusion 모듈 사용**: 직접 삼각측량하지 않는다. 각 카메라가 로컬 검출(BODY_18)을 publish 하고
  Fusion 이 world 좌표에서 연관·융합해 **BODY_34** 를 낸다. 재추적/피팅을 SDK 에 맡긴다.
- **캘리브레이션이 전제**: 상대 extrinsic 이 틀리면 같은 사람이 두 world 위치로 찍혀 Fusion 이
  **다른 사람 2명(id0/id1)** 으로 본다. 그래서 ZED360 캘리브를 **실행 전 강제**한다(PLAN04).
  카메라가 고정이 아니고 충격을 받으므로 매 세션 재캘리브가 기본이다.
- **2×HD720@30 고정**: USB 컨트롤러가 하나라 @60 은 붕괴(5.7/21.7fps). 코드가 60 을 거부한다.
- **좌표계 통일**: `RIGHT_HANDED_Z_UP_X_FWD` / METER (X=전방, Y=좌, Z=상). 융합 결과는
  **fusion world frame** — 단일캠 로그와 프레임이 달라 로그에 `frame: "fusion_world"` 를 태그한다.
- **측정과 ROS2 발행 분리**: pyzed/CUDA가 필요한 base pose 측정은 conda `zed`에서 끝내고,
  시스템 ROS2는 quaternion 좌표 YAML만 읽어 `/tf_static`을 발행한다.
- **뷰는 투영 교체로 얻는다**: 융합 결과가 world 3D 라 top(X-Y)/front(Y-Z)/side(X-Z) 는 축만 바꾸면 된다.
  orbit 도 OpenGL 없이 회전 정사영으로 처리한다.
- **새 기능은 새 파일**: 검증된 스크립트의 런타임을 개조하지 않고, 헬퍼는 import 재사용한다.

## 제약

- ZED-M **2대**, SDK **5.4**, pyzed 는 conda `zed` env, **GPU(CUDA) 필요**.
- USB 컨트롤러 **1개**(Intel xHCI `00:14.0`) 공유 → 2×HD720@30 이 상한.
- **USB3 패시브 연장선 금지** — SuperSpeed 신호 저하로 불완전 프레임(찢김) 발생. **PC 직결**.
- **ZED360 은 GUI 전용**(CLI 없음) → 캘리브는 사람이 직접 수행해야 한다.
- 카메라·GPU·디스플레이는 **사용자 환경에만** 있다. 에이전트 샌드박스는 정적 검증까지만 가능.

## 용어

- **sender** — 각 카메라가 로컬에서 검출해 Fusion 으로 publish 하는 쪽(`start_publishing`).
- **fusion world frame** — 캘리브레이션이 정의하는 공통 world 좌표계. 융합 keypoint 의 기준.
- **extrinsic** — 카메라 간 상대 위치·자세. ZED360 이 계산하며, 틀리면 융합이 분리된다.
- **base frame** — ArUco 큐브 마커 1 중심에 둔 로봇 셀 기준. +X=마커1 법선, +Y=왼쪽, +Z=위.
- **BODY_18 / BODY_34** — sender 검출 포맷 / Fusion 이 피팅해 내는 융합 포맷. 인덱스가 다르다.
- **가림 상보성(occlusion-robustness)** — 한 카메라가 놓친 관절을 반대쪽이 메우는 성질. 이 구조의 목적.
