# π0 비동기 추론 설정 가이드

설정 파일은 [`pi0_piper_vla_pipeline.yaml`](./pi0_piper_vla_pipeline.yaml)이다.
이 파일 하나가 **π0 모델 서버 설정**과 **기존 LeRobot async client 실행 계약**을
함께 보관한다.

쉽게 말하면 다음 세 가지를 정한다.

1. 어떤 학습 결과를 불러올지 정한다.
2. π0가 action 50개를 어떻게 계산하고 몇 개를 보낼지 정한다.
3. 기존 action과 새 action이 겹칠 때 client가 어떻게 합칠지 정한다.

## 1분 요약

처음 실험할 때는 아래 값을 유지하는 것을 권장한다.

```yaml
policy:
  num_inference_steps: 10

async_client:
  actions_per_chunk: 50
  chunk_size_threshold: 0.50
  aggregate_fn_name: weighted_average
  fps: 20
  observation_queue_timeout_seconds: 1.0
  debug_visualize_queue_size: true
```

이 설정은 다음처럼 동작한다.

```text
π0가 미래 action 50개 생성
          ↓
client에 action 50개 전송
          ↓
20 Hz로 실행하다가 queue가 약 50% 남으면 새 관측 요청
          ↓
겹치는 action = 기존 예측 30% + 새로운 예측 70%
```

## 설정이 실제 적용되는 위치

모든 값이 서버에서 직접 계산되는 것은 아니다.

| 구분 | 설정 | 실제 적용 위치 |
|---|---|---|
| 모델 | `num_inference_steps` | π0 GPU 추론 |
| 서버 | `actions_per_chunk` | server가 client 요청값과 일치하는지 강제 |
| 서버 | `fps` | action timestamp 간격 계산 |
| 서버 | `observation_queue_timeout_seconds` | observation 대기 시간 |
| client | `chunk_size_threshold` | Piper PC action queue |
| client | `aggregate_fn_name` | Piper PC에서 이전·신규 chunk 합성 |
| client | `debug_visualize_queue_size` | Piper PC 진단 화면 |

현재 LeRobot 0.6 handshake는 `actions_per_chunk`만 서버에 전달한다.
따라서 threshold와 합성 방식은 서버가 원격으로 강제할 수 없다. 대신 서버 launcher가
같은 YAML 값으로 client 실행 명령을 만들어 준다.

```bash
./scripts/inference/serve_vla_pipeline.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml \
  --step 30000 \
  --print-client-command
```

출력된 명령을 Piper PC에서 실행해야 같은 설정이 적용된다.

## `checkpoint`: 어떤 모델을 불러오는가

### `runs_root`

학습 결과들이 들어 있는 상위 경로다.

```yaml
runs_root: data/runs
```

상대 경로는 `/home/pc/vla_ws` 기준으로 해석한다. workspace 밖으로 나가는 경로와
symlink 탈출은 거부한다.

### `config_name`

학습 때 사용한 OpenPI namespace다. 현재 Piper π0는 다음 값만 지원한다.

```yaml
config_name: pi0_piper_lora
```

다른 이름은 단순 폴더명이 아니라 모델·데이터 변환 계약이 달라질 수 있으므로 거부한다.

### `run_name`

사용할 학습 run 폴더 이름이다.

```yaml
run_name: two_block_pnp_b32_vt_s30000_r002
```

`vt`는 Vision encoder까지 학습한 run, `vf`는 Vision encoder를 동결한 run 이름에
사용한 표기다. 추론 코드는 둘 다 같은 방식으로 복원하지만 결과 성능은 다를 수 있다.

### `asset_id`

checkpoint 내부 normalization 통계 폴더 이름이다.

```yaml
asset_id: two_block_pnp
```

서버는 반드시 선택한 checkpoint 안의 다음 파일을 사용한다.

```text
<step>/assets/two_block_pnp/norm_stats.json
```

학습 workspace의 다른 통계를 임의로 섞지 않는다.

### `step`

기본으로 복원할 완료 checkpoint 번호다.

```yaml
step: 30000
```

실험 기록을 재현하려면 `latest`보다 숫자를 고정하는 것이 안전하다. Orbax 임시 저장
폴더나 commit이 끝나지 않은 step은 선택되지 않는다.

## `policy`: π0가 action을 계산하는 방법

### `prompt`

모델에 전달할 작업 문장이다. 현재 단일-task 서버는 client가 보낸 문장과 이 문장이
글자 단위로 같아야 한다.

```yaml
prompt: "pick up the green blocks one at a time and place them in the white box"
```

비슷한 뜻의 한국어 문장으로 바꾸는 것도 학습 때 보지 않은 조건이 될 수 있다.

### `num_inference_steps`

π0 Flow Matching이 노이즈에서 action을 만드는 Euler 적분 횟수다.

- 작게 하면 추론이 빨라질 수 있지만 action 품질이 달라질 수 있다.
- 크게 하면 계산 시간이 늘어난다.
- chunk 길이 50을 바꾸는 값은 아니다.

현재 시작값은 `10`이다. 비교 실험 후보는 `5`, `10`, `20`이지만, `10` 이외 값은
실제 로봇 성공률과 추론 시간을 함께 측정해야 한다. 숫자가 크다고 항상 좋은 것은 아니다.

## `server`: 네트워크 주소

### `host`

서버가 연결을 받을 주소다.

```yaml
host: 127.0.0.1
```

- client가 같은 PC에 있으면 `127.0.0.1`
- Piper client가 다른 PC에 있으면 `0.0.0.0` 또는 GPU PC의 신뢰된 LAN 주소

이 gRPC 연결에는 인증과 TLS가 없고 pickle 호환 payload를 사용한다. 공용 인터넷에
노출하지 말고 방화벽으로 신뢰된 Piper PC만 허용해야 한다.

### `port`

기존 LeRobot async client가 접속할 TCP port다. 기본값은 `8080`이다.

## `runtime`: GPU 메모리

### `jax_memory_fraction`

JAX allocator가 사용할 수 있는 GPU 메모리 pool 상한 비율이다.

```yaml
jax_memory_fraction: 0.70
```

이 값은 모델 크기나 추론 품질을 바꾸지 않는다. `nvidia-smi`에는 JAX가 실제 tensor보다
큰 pool을 예약한 것으로 보일 수 있다. 너무 낮으면 weight 복원이나 첫 JIT에서 OOM이
날 수 있고, 너무 높으면 같은 GPU의 다른 process가 사용할 공간이 줄어든다.

## `async_client`: 비동기 chunk 실행

### `actions_per_chunk`

π0가 생성한 미래 action 50개 중 client로 보낼 개수다.

```yaml
actions_per_chunk: 50
```

- 허용 범위: `1~50`
- 권장 시작값: `50`
- 작게 하면 최신 관측을 더 자주 반영할 수 있지만 queue 고갈 위험이 커진다.
- 크게 하면 지연을 버티기 쉽지만 오래된 예측을 더 오래 실행할 수 있다.

서버는 client handshake의 값이 YAML과 다르면 연결을 거부한다. 모델의 고정
`action_horizon=50` 자체를 100으로 늘리는 설정은 아니다.

### `chunk_size_threshold`

client action queue가 어느 정도 남았을 때 새 관측을 서버로 보낼지 정한다.

```yaml
chunk_size_threshold: 0.50
```

`actions_per_chunk=50`일 때 대략 다음처럼 이해할 수 있다.

- `0.0`: 거의 다 쓴 뒤 요청한다. 요청은 적지만 queue 고갈 위험이 크다.
- `0.5`: 약 25개 남았을 때 요청한다. 현재 권장 시작값이다.
- `0.7`: 약 35개 남았을 때 요청한다. 더 일찍 재계획한다.
- `1.0`: 거의 매 control tick 요청할 수 있어 GPU·네트워크 부하가 커진다.

정확한 요청 시점에는 서버 지연과 client thread scheduling도 영향을 준다.

### `aggregate_fn_name`

이전 chunk와 새 chunk가 같은 timestep에서 겹칠 때 합치는 방법이다.

| 값 | 계산 | 쉬운 의미 |
|---|---|---|
| `weighted_average` | 기존 30% + 신규 70% | 새 예측을 우선하면서 부드럽게 연결 |
| `latest_only` | 신규 100% | 반응은 빠르지만 명령이 튈 수 있음 |
| `average` | 기존 50% + 신규 50% | 두 예측을 같은 비중으로 사용 |
| `conservative` | 기존 70% + 신규 30% | 기존 계획을 더 오래 신뢰 |

현재 권장 시작값은 `weighted_average`다. 30/70 숫자는 LeRobot 0.6에 고정된 함수
정의이며 YAML에서 가중치 숫자만 따로 바꾸는 기능은 없다.

### `fps`

action을 실행하는 주파수와 server가 만드는 action timestamp 간격을 정한다.

```yaml
fps: 20
```

학습 데이터가 20 Hz이므로 현재 권장값도 `20`이다. 50개 chunk는 20 Hz에서 2.5초다.
10 Hz로 내리면 같은 50개를 5초에 걸쳐 실행하고, 40 Hz로 올리면 1.25초 만에 실행한다.
이는 학습 때의 시간 의미를 바꾸므로 단순 성능 튜닝 값처럼 변경하면 안 된다.

### `observation_queue_timeout_seconds`

client가 action을 요청했지만 새 observation이 아직 없을 때 서버가 기다리는 시간이다.

```yaml
observation_queue_timeout_seconds: 1.0
```

시간 안에 observation이 없으면 서버는 빈 action 응답을 보내며 client는 다시 polling한다.
너무 길면 연결 이상을 늦게 발견하고, 너무 짧으면 정상적인 네트워크 흔들림에도 빈 응답이
늘어난다. LAN에서는 `1.0`을 시작값으로 권장한다.

### `debug_visualize_queue_size`

기존 client에서 action queue 크기 진단 화면을 표시한다.

```yaml
debug_visualize_queue_size: true
```

모델 결과나 제어 수학은 바뀌지 않는다. 초기 E2E 시험에서는 `true`, 장시간 운영에서
진단 창이 필요 없으면 `false`가 적당하다.

## 실행 순서

1. 설정과 생성될 client 명령을 확인한다.

```bash
./scripts/inference/serve_vla_pipeline.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml \
  --step 30000 \
  --print-client-command
```

2. checkpoint를 GPU 없이 검사한다.

```bash
./scripts/inference/serve_vla_pipeline.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml \
  --step 30000 \
  --check-only
```

3. 학습 process가 끝난 뒤 서버를 실행한다.

```bash
./scripts/inference/serve_vla_pipeline.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml \
  --step 30000
```

4. 첫 명령에서 출력된 client 명령의 `/path/to/vla_pipeline`과 `GPU_SERVER_IP`를
Piper PC의 실제 값으로 바꿔 실행한다.

## 비교 실험 원칙

처음에는 한 번에 하나만 바꾼다.

```text
기준: steps=10, chunk=50, threshold=0.5, weighted_average, 20Hz
실험 A: threshold만 0.7
실험 B: aggregate만 latest_only
실험 C: inference steps만 5
```

각 실험마다 inference latency, queue 최저 크기, 빈 action 응답, 로봇 성공률, 충돌·HOLD
횟수를 함께 기록해야 한다. training loss만으로 이 추론 파라미터의 우열을 판단할 수 없다.
