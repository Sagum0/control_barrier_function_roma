# Piper π0.5 LoRA 설정 가이드

실제 실행값은 [`piper_lora.yaml`](./piper_lora.yaml)에 있다. 이 문서는 각 값이 무엇을 바꾸는지 쉬운 말로 설명한다.

> **중요:** 고정 OpenPI에는 Piper용 공식 π0.5 LoRA profile이 없다. 현재 설정은 π0.5 모델 구조에 Piper 데이터 계약과 기존 π0 LoRA optimizer/LR baseline을 결합한 **실험 profile**이다.

## 1. 1분 요약

YAML에서 직접 바꿀 수 있는 값:

- dataset·asset·checkpoint 경로
- Vision encoder 학습 여부
- 목표 step, batch, worker, log·checkpoint 간격, seed
- JAX memory 상한과 진행 화면 갱신 간격

YAML에 표시되지만 자유롭게 바꾸면 안 되는 값:

- `optimizer`
- `lr_schedule`
- `model_contract`

이 세 section은 production Python 코드와 같은지 확인하는 **잠긴 계약**이다. 값만 바꾸면 모델이 변경되는 것이 아니라 strict loader가 실행을 거부한다.

## 2. π0와 π0.5의 핵심 차이

| 항목 | π0 | 현재 π0.5 | 쉬운 설명 |
|---|---:|---:|---|
| 모델 family | `pi05: false` | `pi05: true` | π0.5 구조를 사용한다 |
| prompt 길이 | 48 tokens | 200 tokens | π0.5는 state 정보도 token 영역에 넣는다 |
| state 입력 | continuous state | discrete-state 입력 추가 | 로봇 상태를 언어 입력과 함께 표현한다 |
| 정규화 | z-score | quantile | 평균/표준편차 대신 q01/q99 범위를 중심으로 맞춘다 |
| profile 출처 | 공식 low-memory 예제 | 로컬 experimental profile | 공식 Piper π0.5 LoRA 설정은 없다 |

Production 코드는 YAML 밖에서도 다음 값을 강제로 검증한다.

```python
discrete_state_input=True
```

`action_horizon=50`, `action_dim=32`, Piper 7D와 joint 6축 delta 규칙은 π0와 동일하게 유지한다. 두 모델을 같은 로봇·데이터 조건에서 비교하기 위한 프로젝트 선택이다.

## 3. 새 run과 resume 규칙

다음 값을 바꾸면 반드시 새로운 `--run-name`으로 시작한다.

- dataset, `asset_id`, norm stats
- `batch_size`, `seed`
- Vision encoder의 `trainable`/`frozen`
- optimizer, LR, EMA, model 구조·variant·horizon

다음 값은 같은 run을 resume하면서 조정할 수 있다.

- 더 큰 `num_train_steps`
- `num_workers`
- `log_interval`, `save_interval`, `keep_period`
- `jax_memory_fraction`, `progress_refresh_seconds`

> **쉽게 말하면:** 모델이 배우는 수학이나 학습 대상이 달라지면 새 실험이다. 화면·저장 주기나 최종 종료 step만 바꾸는 것은 이어서 실행할 수 있다.

π0 checkpoint와 π0.5 checkpoint는 서로 resume할 수 없다. 저장 namespace도 각각 분리돼 있다.

```text
π0   : data/runs/pi0_piper_lora/<run-name>
π0.5 : data/runs/pi05_piper_lora/<run-name>
```

## 4. 경로와 dataset 설정

### `paths.dataset_root`

LeRobot v3 묶음의 루트다. 아래 폴더의 부모를 가리켜야 한다.

```text
dataset_root/
├── meta/
├── data/
└── videos/
```

Loader는 shard와 episode 수를 자동으로 읽는다. 하지만 임의의 LeRobot v3 dataset을 의미적으로 자동 변환하지는 않는다. 현재 adapter는 Piper 7D, 두 카메라, 20Hz 계약을 검사한다.

### `paths.assets_base_dir`와 `dataset.asset_id`

π0.5 norm stats의 실제 위치는 다음 규칙으로 만들어진다.

```text
<assets_base_dir>/pi05_piper_lora/<asset_id>/norm_stats.json
```

현재 `two_block_pnp` asset은 다음 파일이다.

```text
data/assets/pi05_piper_lora/two_block_pnp/norm_stats.json
```

`asset_id`는 Hugging Face의 `ORG/REPO` 이름이 아니라 dataset과 norm stats를 연결하는 로컬 이름이다.

### `paths.runs_root`

학습 결과를 저장하는 상위 폴더다. 최종 경로는 다음과 같다.

```text
<runs_root>/pi05_piper_lora/<run-name>
```

### `paths.base_params`

새 run을 시작할 때 읽는 π0.5 base model이다.

```text
data/cache/openpi/openpi-assets/checkpoints/pi05_base/params
```

Resume에서는 기존 checkpoint를 복원하므로 base params를 다시 읽지 않는다. `pi0_base`를 지정하면 안 된다.

## 5. Vision encoder

### `finetuning.vision_encoder: trainable`

Vision encoder도 gradient와 AdamW update를 받는다.

- 새 배경·조명·카메라에 적응할 가능성이 높다.
- 학습 parameter, VRAM, optimizer state가 커진다.
- 데이터가 단조로우면 시각 특징이 과적합될 수 있다.

> **쉽게 말하면:** 모델의 눈까지 다시 학습한다.

### `finetuning.vision_encoder: frozen`

Vision encoder는 고정하고 두 expert의 LoRA와 action/state projection을 학습한다.

- 메모리와 optimizer state가 줄어든다.
- 작은 dataset에서 기존 시각 특징을 보존하기 쉽다.
- 카메라 환경 차이가 크면 적응력이 부족할 수 있다.

> **쉽게 말하면:** 눈은 그대로 두고, 본 것을 행동으로 바꾸는 부분을 주로 학습한다.

노트북에서 확인한 π0.5 vision-frozen 분할:

```text
전체 parameter    : 3,403,421,456
학습 parameter    :    52,153,376 (1.532%)
동결 parameter    : 3,351,268,080
```

`vf`나 `vt` 같은 run 이름은 설명용일 뿐이다. 실제 동작은 YAML의 `vision_encoder` 값으로 결정된다.

## 6. Step과 batch

### `training.num_train_steps`

현재 step에 더할 횟수가 아니라 학습이 도달할 **absolute 최종 step**이다.

```text
latest checkpoint = 5,000
target step        = 30,000
실제로 더 실행     = 25,000 steps
```

현재 `30,000`은 공식 Piper π0.5 권장값이 아니다. 기존 π0 LoRA 실험과 비교하기 위한 시작점이다. 5k 단위 checkpoint를 rollout 평가해 최종 checkpoint만 무조건 선택하지 않는다.

### `training.batch_size`

한 번의 parameter update에서 같이 보는 sample 수다. 현재 trainer에는 gradient accumulation이 없다.

```text
한 step의 sample 수 = batch_size
전체 sample 수       = num_train_steps × batch_size
명목상 dataset pass  = 전체 sample 수 / dataset frames
```

현재 dataset은 699,921 frames다. 30,000 steps 기준:

| batch | 전체 sample | 명목상 dataset pass |
|---:|---:|---:|
| 1 | 30,000 | 0.043회 |
| 8 | 240,000 | 0.343회 |
| 16 | 480,000 | 0.686회 |
| 32 | 960,000 | 1.372회 |

Action horizon 50의 이웃 window가 서로 겹치므로 일반 이미지 분류의 독립적인 epoch와 완전히 같지는 않다.

배치 추천 해석:

- 논문과 공식 OpenPI에는 Piper π0.5 LoRA 최적 batch가 없다.
- 먼저 `1`로 end-to-end 계약을 검사한다.
- `4 → 8 → 16 → 32` smoke로 VRAM·속도·finite metric을 비교한다.
- 큰 batch가 OOD 성능을 자동으로 높이지 않는다. OOD는 데이터 다양성과 rollout 평가가 더 중요하다.

`steps/s`만 보면 작은 batch가 훨씬 빨라 보인다. 공정한 속도 비교는 `samples/s`를 본다.

### `training.num_workers`

영상 decode와 dataset 준비를 담당하는 CPU subprocess 수다.

- `0`: 가장 단순하고 문제 추적이 쉬움
- `2`: 일반적인 시작값
- 너무 높음: host RAM과 process 수 증가

GPU가 계속 100%라면 worker를 늘려도 학습은 빨라지지 않는다. JSONL의 data time이 큰 경우에만 조정한다.

## 7. 기록과 checkpoint

### `training.log_interval`

loss·grad norm·param norm을 JAX에서 host로 동기화하는 간격이다.

- smoke: `1`
- 장기 실행 시작 범위: `10~30`

값이 작으면 화면은 자주 정확해지지만 accelerator synchronization 비용이 증가한다. 1초 dashboard repaint와는 별개다.

### `training.save_interval`

정기 checkpoint 저장 간격이다. 목표 step은 이 간격과 맞지 않아도 마지막에 저장한다.

- 현재 baseline: `5,000`
- 작게 설정: 장애 시 손실 step 감소, 디스크·RAM·저장시간 증가
- 크게 설정: 저장 부담 감소, 장애 시 다시 계산할 구간 증가

### `training.keep_period`

장기 보존할 checkpoint 간격이다. 일반 checkpoint는 최신 하나만 남기고, `keep_period` 배수는 보존한다.

```text
save_interval = 5,000
keep_period   = 5,000
```

이면 5k, 10k, 15k처럼 장기 checkpoint를 유지한다. 디스크 용량을 먼저 확인한다.

### `training.seed`

DataLoader shuffle, flow noise와 augmentation 난수를 결정한다. 비교 실험에서는 같은 seed를 사용한다. Resume 중 seed를 바꾸면 이어지는 데이터·난수 순서가 달라진다.

## 8. JAX runtime

### `runtime.jax_memory_fraction`

JAX allocator가 사용할 GPU memory pool의 최대 비율이다. 모델 학습량이나 batch를 자동 조정하지 않는다.

```yaml
jax_memory_fraction: 0.65
```

48GB GPU에서 0.65는 약 29GiB 수준의 allocator limit이다. `nvidia-smi`는 예약량을 보여줄 수 있고, dashboard의 JAX `live/peak/limit`는 tensor 실사용량과 peak를 보여준다.

OOM이 나도 JAX가 batch를 자동으로 줄이지 않는다. batch나 memory fraction을 사용자가 조정해 새 process로 다시 실행해야 한다.

### `runtime.progress_refresh_seconds`

TTY 진행 화면을 다시 그리는 간격이다. loss/JAX metric을 새로 계산하는 간격은 `log_interval`이다.

```text
progress_refresh_seconds = 화면 repaint
log_interval             = 실제 metric synchronization
```

## 9. Optimizer와 LR

현재 optimizer는 AdamW다.

| 값 | 현재값 | 의미 |
|---|---:|---|
| `b1` | 0.9 | gradient 방향의 이동평균 |
| `b2` | 0.95 | gradient 크기 제곱의 이동평균 |
| `eps` | 1e-8 | 0으로 나누는 수치 문제 방지 |
| `weight_decay` | 1e-10 | parameter가 과도하게 커지는 것을 억제; 현재는 매우 작음 |
| `clip_gradient_norm` | 1.0 | AdamW 전에 전체 gradient norm을 1 이하로 축소 |

Dashboard의 `grad_norm`은 clipping 전 원래 gradient norm이다. 1보다 크다고 즉시 오류는 아니다.

Learning rate schedule:

```text
step 0~1,000      : warmup으로 2.5e-5까지 증가
step 1,000~30,000 : cosine으로 2.5e-6까지 감소
step 30,000 이후  : end LR 근처에 머묾
```

이 optimizer/LR은 π0.5 논문 권장값이 아니라 기존 π0 LoRA baseline이다. 변경하려면 잠금값과 trainer를 함께 수정하고 새 run으로 검증한다.

## 10. EMA

`ema_decay: null`은 EMA 가중치를 만들지 않는다는 뜻이다.

EMA를 `0.999`로 사용하면 매 step 별도 평균 가중치를 갱신한다.

```text
EMA = 0.999 × 이전 EMA + 0.001 × 현재 parameter
```

장점:

- noisy update를 평균 내 추론 결과가 더 안정적일 수 있음
- 일부 full-finetuning recipe에서 성능 향상 가능

비용:

- 모델 parameter 복사본이 추가돼 GPU/RAM 사용 증가
- checkpoint와 저장 중 staging 부담 증가
- 기존 EMA 없는 checkpoint와 TrainState 계약이 달라짐

현재 OpenPI는 EMA가 켜지면 inference용 `params`에 EMA 값을 저장하고, resume용 `train_state`에는 현재 원본 parameter도 보관한다. 따라서 비용이 작지 않다.

공식 `pi05_libero`의 EMA 값은 그 profile의 full-finetuning·batch·LR과 묶인 설정이다. 현재 Piper LoRA에 그대로 적용하는 것을 공식 추천으로 해석하면 안 된다. 현재 baseline은 메모리와 checkpoint 안정성을 위해 `null`이다.

## 11. 잠긴 model contract

| YAML key | 의미 | 현재 계약 |
|---|---|---|
| `openpi_profile` | 설정 출처 표시 | `experimental_pi05_piper_lora` |
| `pi05` | π0.5 구조 활성화 | `true` |
| `paligemma_variant` | VLM expert | `gemma_2b_lora` |
| `action_expert_variant` | action expert | `gemma_300m_lora` |
| `dtype` | 기본 계산/동결 parameter dtype | `bfloat16` |
| `action_dim` | 모델 내부 action/state 폭 | `32` |
| `action_horizon` | 한 sample의 미래 action 수 | `50` |
| `max_token_len` | prompt/discrete-state token 길이 | `200` |
| `robot_dim` | 실제 Piper 값 개수 | `7` |
| `delta_joint_dim` | delta로 바꾸는 joint 축 | `6` |
| `normalization` | 수치 정규화 | `quantile` |
| `freeze_mode` | base LLM과 LoRA 구분 filter | `pi05_lora_filter` |
| `ema_decay` | 이동평균 parameter | `null` |
| `fsdp_devices` | 학습 JAX device 수 | `1` |

`freeze_mode`와 `finetuning.vision_encoder`는 역할이 다르다.

- `freeze_mode`: base LLM은 고정하고 LoRA를 학습하는 기본 filter 계약
- `vision_encoder`: 그 기본 filter에 Vision tower 동결을 추가할지 결정

## 12. 실행 순서

### 설정·데이터만 검사

```bash
./scripts/training/pi05/train_from_config.py \
  --config config/training/pi05/piper_lora.yaml \
  --run-name two_block_pnp_pi05_check \
  --target-step 10 \
  --check-only
```

### 10-step GPU smoke

```bash
./scripts/training/pi05/train_from_config.py \
  --config config/training/pi05/piper_lora.yaml \
  --run-name two_block_pnp_pi05_smoke_s10_r001 \
  --target-step 10
```

### 같은 설정으로 이어서 실행

```bash
./scripts/training/pi05/train_from_config.py \
  --config config/training/pi05/piper_lora.yaml \
  --run-name <기존-run-name> \
  --resume \
  --target-step 30000
```

### 진행 상황 확인

```bash
./scripts/training/pi05/watch_training.py \
  --run-name <run-name> \
  --unit <systemd-unit-name>
```

## 13. 성능 판단

Training loss가 낮다고 실제 로봇 성공률이 높은 것은 아니다. 최소한 다음을 따로 확인한다.

- held-out episode loss와 denormalized joint/gripper 오차
- 같은 환경에서의 closed-loop 성공률
- 다른 조명·배경·물체 위치의 OOD 성공률
- 충돌, timeout, 잘못된 gripper 동작

Batch, Vision mode, EMA 비교는 `steps`가 아니라 처리한 sample 수와 rollout 조건을 맞춰야 한다.

참고 구현:

- [고정 OpenPI model config](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/models/pi0_config.py)
- [고정 OpenPI training config](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/training/config.py)
- [고정 OpenPI optimizer](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/training/optimizer.py)
