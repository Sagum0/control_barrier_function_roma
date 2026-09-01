# Piper π0 추론 서버

현재는 완료된 학습 checkpoint를 읽는 서버 표면을 두 가지 제공한다.

- 새 adapter용 OpenPI WebSocket 정책 서버
- 기존 `vla_pipeline` LeRobot 0.6 client용 AsyncInference gRPC 서버

두 서버 모두 같은 OpenPI policy와 checkpoint 내 norm stats를 사용한다. 실제 ROS action
발행, chunk 집계, rosbridge 연결은 기존 `vla_pipeline` client가 그대로 담당한다.

## 기준으로 삼은 로봇 코드

로봇 계약은 아래 저장소의 정확한 브랜치와 commit만 확인했다.

- 저장소: `https://github.com/Sagum0/RoMaLab`
- 브랜치: `dev_e2e_piper`
- 확인 commit: `74c35ccb551e395e0201ac889d21dd4a4bd7ee14`
- 로컬 확인 경로: `/home/pc/RoMaLab_dev_e2e_piper`

ROS 토픽·단위·chunk 계약은 위 RoMaLab branch만 기준으로 삼았다. LeRobot gRPC wire
계약은 공식 LeRobot `v0.6.0`과 기존 `/home/pc/vla_pipeline-main` client를 대조했다.
`/home/pc/piper_ws`는 사용하지 않았다.

## 전체 구조

```text
추론 PC
├── vla_ws conda Python 3.11
│   └── OpenPI JAX WebSocket policy server
│       ├── Orbax <step>/params 복원
│       ├── <step>/assets/<asset_id>/norm_stats.json 사용
│       └── canonical observation -> absolute actions (50, 7)
│
└── ROS2 Humble Python 3.10                 다음 구현 단계
    └── RoMaLab policy adapter
        ├── 두 JPEG 카메라 + slave_state 구독
        ├── WebSocket server에 observation 요청
        ├── 향후 adapter: 원본 chunk 발행
        └── chunk action을 20Hz로 executor에 발행

로봇 PC: RoMaLab dev_e2e_piper
├── 카메라 발행
├── local ready gate 발행
├── 안전 executor
└── rollout bag recorder
```

JAX 환경과 ROS2 Humble 환경의 Python 버전이 다르므로 모델 서버와 ROS2 어댑터를
한 process에 섞지 않는다. 같은 추론 PC 안에서는 WebSocket을 `127.0.0.1`에만 bind한다.
두 PC 사이 통신은 rosbridge가 아니라 ROS2 DDS를 사용하고 `ROS_DOMAIN_ID=17`을 맞춘다.

## 현재 생성된 파일

```text
config/inference/pi0_piper_inference.yaml
config/inference/pi0_piper_vla_pipeline.yaml
scripts/inference/serve_policy.py
scripts/inference/serve_vla_pipeline.py
src/piper_vla/inference/
├── settings.py           # strict YAML과 workspace 경로 검증
├── checkpoint.py         # 완료 Orbax step과 내장 norm stats 검증
├── observation.py        # RGB/state 입력과 (50, 7) 출력 계약
├── romalab_contract.py   # dev_e2e_piper ROS2 토픽·단위 계약
├── policy_server.py      # OpenPI policy restore와 WebSocket server
└── lerobot_grpc.py       # LeRobot 0.6 AsyncInference gRPC 호환 표면
```

기존 `vla_pipeline`을 유지하는 실행법과 검증 범위는
[`VLA_PIPELINE_SERVER.md`](./VLA_PIPELINE_SERVER.md)에 분리해 두었다.

## 1. 학습 중에 할 수 있는 검사

아래 명령은 JAX/OpenPI policy를 import하지 않고 GPU도 초기화하지 않는다. 숫자 step,
Orbax commit timestamp, params marker, checkpoint 내 norm stats만 읽는다.

```bash
cd /home/pc/vla_ws

./scripts/inference/serve_policy.py \
  --config config/inference/pi0_piper_inference.yaml \
  --latest \
  --check-only
```

`--latest`는 이름이 숫자인 커밋 완료 step만 고른다.
`*.orbax-checkpoint-tmp-*`와 commit이 끝나지 않은 checkpoint는 무시한다.

## 2. 30,000 step 완료 뒤 서버 실행

학습 process가 종료되고 `30000/_CHECKPOINT_METADATA`가 commit된 뒤 실행한다.
학습과 동시에 실행하면 두 JAX process가 GPU 메모리를 경쟁하므로 금지한다.

```bash
cd /home/pc/vla_ws

./scripts/inference/serve_policy.py \
  --config config/inference/pi0_piper_inference.yaml \
  --step 30000
```

다른 터미널에서 health endpoint를 확인한다.

```bash
curl http://127.0.0.1:8000/healthz
```

정상 응답은 `OK`다. 첫 실제 추론 요청은 JIT compile 때문에 오래 걸릴 수 있으므로,
로봇 연결 전에 고정 관측으로 warm-up과 지연 시간을 먼저 측정한다.

## 입력과 출력

WebSocket client가 보낼 입력은 다음 네 key다.

```python
{
    "observation/image": third_person_rgb_uint8,       # (480, 640, 3)
    "observation/wrist_image": wrist_rgb_uint8,       # (480, 640, 3)
    "observation/state": absolute_state_float32_7d,   # joint 6 rad + gripper m
    "prompt": "pick up the green blocks one at a time and place them in the white box",
}
```

JPEG를 OpenCV로 decode하면 BGR이므로 RGB로 바꾼 뒤 보내야 한다. 224×224 resize,
z-score normalization, 관절 6축 delta 변환을 client에서 하지 않는다. OpenPI policy가
학습과 같은 순서로 처리한다.

출력 `actions`는 아래 계약을 만족해야 한다.

- shape: `(50, 7)`
- 축 순서: `joint1`~`joint6`, `gripper`
- 관절 단위: absolute radian
- gripper 단위: absolute meter
- 모든 값: finite

OpenPI output transform이 unnormalize, delta→absolute 복원, 내부 32차원에서 실제
7차원 slice를 수행한다. client가 다시 역변환하면 action이 망가진다.

## RoMaLab ROS2 계약

| 역할 | 토픽 | 메시지 | 주기·단위 |
|---|---|---|---|
| 3인칭 영상 | `/piper/third_person/image` | `CompressedImage` | JPEG 640×480, 30Hz |
| 손목 영상 | `/piper/wrist/image` | `CompressedImage` | JPEG 640×480, 30Hz |
| 로봇 state | `/piper/inference/slave_state` | `JointState` | 6축 rad + gripper m, 최대 100Hz |
| step action | `/piper/inference/output` | `JointState` | absolute 7D, 20Hz 권장 |
| 향후 adapter 원본 chunk | `/piper/inference/chunk` | `JointTrajectory` | 추론 1회당 `(50, 7)` 1건 |
| local gate | `/piper/inference/ready` | `Bool` | 로봇 PC가 발행 |

executor는 action이 0.5초 동안 없으면 HOLD로 전환한다. action은 정확한 7개 이름,
finite 값, 현재 자세와의 안전 거리, URDF 범위 검사를 통과해야 한다. 최종 안전 판단은
RoMaLab executor가 담당하지만, ROS2 어댑터도 발행 전에 shape와 finite를 먼저 검사한다.

## 설정 파일 의미

실행 설정은 `/home/pc/vla_ws/config/inference/pi0_piper_inference.yaml`에 있다.

- `checkpoint.run_name`: 학습 결과 run 이름
- `checkpoint.step`: 기본으로 복원할 exact step
- `checkpoint.asset_id`: checkpoint 안의 norm stats 폴더 이름
- `policy.prompt`: 학습 데이터에 저장된 정확한 task 문장
- `policy.num_inference_steps`: π0 Euler sampling 횟수, 현재 10
- `server.host`: 같은 PC adapter만 연결할 때 `127.0.0.1`
- `runtime.jax_memory_fraction`: JAX allocator 상한 비율, 실제 GPU 사용량과는 다름

`latest`는 점검에는 편하지만 실험 재현을 위해 실제 rollout은 `--step 30000`처럼
정확한 숫자를 고정한다.

## 다음 구현 단계

서버의 실제 checkpoint load와 고정 관측 추론 시간을 검증한 뒤 ROS2 adapter를 만든다.
adapter는 별도 ROS2 package로 두고 다음 일만 맡긴다.

1. 두 카메라와 state를 timestamp 기준으로 묶는다.
2. WebSocket server에 canonical observation을 요청한다.
3. 향후 ROS2 adapter는 원본 `(50, 7)` chunk를 `/piper/inference/chunk`에 한 번 발행한다.
4. 선택한 action을 `/piper/inference/output`에 20Hz로 지속 발행한다.
5. 지연·stale observation·server 오류가 나면 새 action 발행을 멈춰 executor HOLD를 유도한다.
