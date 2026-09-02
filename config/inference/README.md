# 추론 설정

## 어떤 YAML을 사용해야 하는가

기존 `vla_pipeline`을 그대로 사용할 때는
[`pi0_piper_vla_pipeline.yaml`](./pi0_piper_vla_pipeline.yaml)을 사용한다.

[`pi0_piper_inference.yaml`](./pi0_piper_inference.yaml)은 기존 `vla_pipeline`을 거치지
않고 새로운 WebSocket adapter를 직접 작성할 때 사용하는 별도 설정이다. 두 설정은 같은
π0 checkpoint를 읽지만, 로봇 쪽 client와 통신하는 방식이 다르다.

| 구분 | `pi0_piper_inference.yaml` | `pi0_piper_vla_pipeline.yaml` |
|---|---|---|
| 주 용도 | 새로 만드는 범용 adapter | 기존 `vla_pipeline` 연동 |
| 통신 방식 | OpenPI WebSocket | LeRobot 0.6 AsyncInference gRPC |
| 실행 파일 | `scripts/inference/serve_policy.py` | server: `scripts/inference/serve_vla_pipeline.py`<br>client: `scripts/inference/run_vla_pipeline_client.py` |
| 기본 포트 | `8000` | `8080` |
| 입력 방식 | RGB 영상 2개, 7D state, prompt를 직접 전송 | LeRobot feature handshake와 observation queue 사용 |
| 출력 방식 | `(50, 7)` absolute action 배열 | timestamp가 포함된 `TimedAction` chunk |
| 실행 모드 | adapter 구현에 따름 | YAML에서 `async` 또는 `sync` 선택 |
| chunk 설정 | 없음 | 실행 시간, chunk 크기, FPS 및 비동기 queue 설정 가능 |
| YAML schema | `1` | `4` |

두 YAML의 다음 항목은 의미가 같다.

- `checkpoint`: 불러올 학습 run, step, normalization asset
- `policy`: task prompt와 π0 sampling 횟수
- `server`: bind 주소와 포트
- `runtime`: JAX GPU memory allocator 상한

두 서버를 동시에 실행할 필요는 없다. 같은 π0 모델을 각각 GPU에 복원하므로 동시에
실행하면 VRAM을 중복 사용한다.

## 실행 명령

### 기존 `vla_pipeline`을 사용할 때

```bash
./scripts/inference/serve_vla_pipeline.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml
```

다른 terminal에서 같은 YAML을 반영한 Piper client를 실행한다.

```bash
./scripts/inference/run_vla_pipeline_client.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml
```

서버와 client는 YAML의 `checkpoint.step`을 사용한다. `--step`을 주면 그 실행에 한해 YAML
값을 덮어쓴다. 선택한 step의 완료 checkpoint가 없거나 손상됐으면 다른 step으로 대체하지
않고 해당 process가 즉시 종료한다. client launcher가 `lerobot-060`, `PYTHONPATH`,
`PIPER_EPISODE_TIME_S`를 자동 설정하므로 긴 `python -m piper_bridge.async_client ...`
명령을 별도로 실행하지 않는다.

## 동기·비동기 모드 변경

[`pi0_piper_vla_pipeline.yaml`](./pi0_piper_vla_pipeline.yaml)의 한 줄만 바꾼다.

```yaml
client:
  mode: async  # 또는 sync
```

서버와 client를 모두 종료한 다음 같은 YAML로 다시 실행해야 한다. 실행 명령은 두 모드가
동일하다.

### `mode: async`

```text
관측 전송 ─→ 서버 추론
                 │
로봇은 queue의 기존 action을 20Hz로 계속 실행
                 │
새 chunk 수신 ─→ 기존 queue와 합성
```

추론과 로봇 실행이 겹친다. 지연 중에도 queue에 action이 있으면 로봇이 계속 움직이며,
`client.async_options`의 세 설정을 모두 사용한다.

```yaml
client:
  mode: async
  episode_time_seconds: 35
  actions_per_chunk: 50
  fps: 20
  observation_queue_timeout_seconds: 1.0
  async_options:
    chunk_size_threshold: 0.5
    aggregate_fn_name: weighted_average
    debug_visualize_queue_size: false
```

### `mode: sync`

```text
관측 1회 → π0 추론 완료까지 정지 → action chunk를 20Hz로 전부 실행 → 다음 관측
```

추론 중에는 새 action을 실행하지 않는다. 한 번 받은 chunk를 모두 소비한 뒤 다음 관측을
보내므로 queue 중첩과 aggregation이 없다. `client.async_options`는 YAML 형식과 모드 전환
편의를 위해 남아 있지만 동기 client 명령에도 전달되지 않고 동작에서도 전부 무시된다.
`/piper/inference/output` action 발행은 유지되지만 async 전용 queue 그래프,
`async_trace.jsonl`, 원본/aggregation chunk 계측은 생성하지 않는다.

```yaml
client:
  mode: sync
  episode_time_seconds: 35
  actions_per_chunk: 50
  fps: 20
  observation_queue_timeout_seconds: 1.0
  async_options:  # sync에서는 아래 값 전부 비활성
    chunk_size_threshold: 0.5
    aggregate_fn_name: weighted_average
    debug_visualize_queue_size: false
```

### 모드별 옵션 적용표

| 옵션 | `async` | `sync` | 의미 |
|---|---:|---:|---|
| `episode_time_seconds` | 적용 | 적용 | control loop 최대 실행 시간. `null`은 무제한 |
| `actions_per_chunk` | 적용 | 적용 | 서버가 한 관측에서 반환할 action 개수 |
| `fps` | 적용 | 적용 | 반환된 action을 실행하는 주기 |
| `observation_queue_timeout_seconds` | 서버 적용 | 서버 적용 | 서버가 observation을 기다리는 최대 시간 |
| `async_options.chunk_size_threshold` | 적용 | 무시 | queue가 얼마나 남았을 때 다음 관측을 보낼지 결정 |
| `async_options.aggregate_fn_name` | 적용 | 무시 | 겹치는 기존·신규 action을 합성하는 방법 |
| `async_options.debug_visualize_queue_size` | 적용 | 무시 | 종료 후 async queue 크기 그래프 표시 |

`sync`에서 `actions_per_chunk: 50`, `fps: 20`이면 한 번 추론한 뒤 최대 2.5초분
action을 실행한다. 추론 시간에는 로봇 action 발행이 멈추므로 실기기 연속 제어는 보통
`async`가 더 적합하다. `actions_per_chunk: 1`은 매 action마다 다시 추론하는 완전한 step
동기에 가깝지만 π0 추론이 50ms보다 길면 20Hz를 유지할 수 없어 권장하지 않는다.

### 새 WebSocket adapter를 사용할 때

```bash
./scripts/inference/serve_policy.py \
  --config config/inference/pi0_piper_inference.yaml \
  --step 30000
```

## 추가 문서

- 동기·비동기 chunk 파라미터 상세 설명:
  [VLA_PIPELINE_PARAMETERS.md](./VLA_PIPELINE_PARAMETERS.md)
- 서버 실행·입출력·ROS 계약:
  [추론 문서](../../docs/inference/README.md)
