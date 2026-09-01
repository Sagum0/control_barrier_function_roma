# Piper π0 LoRA 설정 가이드

실행에 쓰는 값은 [`pi0_piper_lora.yaml`](../../config/training/pi0_piper_lora.yaml)에 있고, 각 값의 뜻과 조정 방법은 이 문서에 있다.

이 문서는 기술적인 설명을 그대로 남기면서, 각 항목에 **쉽게 말하면** 설명을 추가한 버전이다.

## 1. 1분 요약

### Config로 바로 바꿀 수 있는 것

Train 핵심 코드를 수정하지 않고 YAML에서 다음 값을 바꿀 수 있다.

- 학습할 LeRobot v3 dataset 경로
- Norm stats와 학습 결과를 저장할 상위 경로
- 목표 step, batch, DataLoader worker, 로그·저장 주기, seed
- Vision encoder를 학습할지 고정할지
- JAX가 사용할 GPU memory 비율

> **쉽게 말하면:** 어떤 데이터를 읽을지, 결과를 어느 큰 폴더에 넣을지, 몇 번 학습할지, 한 번에 몇 sample을 볼지, 카메라를 보는 부분까지 학습할지는 YAML에서 정할 수 있다.

> **현재 경로 제한:** YAML에 적는 모든 경로는 현재 workspace인 `/home/pc/vla_ws` 안쪽만 사용할 수 있다. 외장 디스크나 workspace 밖의 경로를 적으면 안전 검사에서 거부된다.

### Config만으로 바꿀 수 없는 것

다음 항목은 CLI 또는 Python profile에 남아 있다.

| 항목 | 어디서 정하는가 | 이유 |
|---|---|---|
| `run_name` | CLI `--run-name` | 새 학습과 resume 대상을 사용자가 실행할 때 명시 |
| Resume 여부 | CLI `--resume` | 실수로 기존 checkpoint를 덮거나 잘못 이어가는 것을 방지 |
| 임시 목표 step | CLI `--target-step` | YAML의 최종 목표보다 일찍 멈추는 검증용 |
| Optimizer·LR 변경 | 새 Python training profile | 현재 YAML 값은 공식 baseline과 같은지 확인하는 잠긴 값 |
| π0.5·모델 구조 | 새 Python model/training profile | base weight, transform, checkpoint 계약이 달라짐 |

> **쉽게 말하면:** 자주 바꾸는 실행값과 Vision encoder 학습 여부는 YAML에 있다. π0를 π0.5로 바꾸거나 optimizer 계산법과 모델 구조를 바꾸려면 새 구현과 별도 검증이 필요하다.

### 결과 경로는 어떻게 만들어지는가

YAML의 `runs_root`는 **상위 폴더**다. 실제 경로는 코드가 다음 규칙으로 만든다.

```text
<runs_root>/pi0_piper_lora/<run_name>/
```

예:

```text
runs_root = data/runs
run_name  = background_400_0818_v3_r001

실제 결과 = data/runs/pi0_piper_lora/background_400_0818_v3_r001/
```

`pi0_piper_lora`라는 중간 폴더 이름은 현재 코드에 고정돼 있다. 임의의 정확한 최종 경로를 YAML 한 줄로 지정하는 구조는 아니다.

> **쉽게 말하면:** YAML로 결과를 저장할 큰 폴더는 바꿀 수 있고, 마지막 실험 폴더 이름은 `--run-name`으로 정한다.

### 새 dataset 경로만 바꾸면 바로 학습되는가

아니다. 새 dataset에는 다음 네 가지가 함께 필요하다.

1. 새 `paths.dataset_root`
2. 새 `dataset.asset_id`
3. 새 dataset에서 계산한 `norm_stats.json`
4. 기존과 다른 새 `run_name`

> **쉽게 말하면:** 데이터 위치만 알려주는 것으로는 부족하다. 로봇 값의 크기를 모델이 이해하도록 새 평균·표준편차 통계도 만들어야 한다.

## 2. 설정값의 출처

이 문서에서는 값의 근거를 다음처럼 나눈다.

| 표기 | 의미 |
|---|---|
| **논문** | Physical Intelligence의 π0 논문에 직접 적힌 값 또는 설계 |
| **공식 구현** | 이 workspace가 고정한 OpenPI commit `215abfb`의 preset/default |
| **로컬 검증** | RTX 6000 Ada 48GB에서 실제 1,000 step까지 실행한 값 |
| **실험 범위** | 다음 비교 실험을 시작할 때 쓸 수 있는 범위 |
| **잠금** | YAML에서 바꾸면 strict loader가 거부하는 값 |

중요한 차이:

- π0 논문은 action horizon `H=50`, flow matching, 사전학습 뒤 고품질 post-training의 효과를 설명한다.
- 논문에는 LoRA용 learning rate, batch size, optimizer, 30,000 step의 정확한 추천값이 없다.
- AdamW, cosine schedule, LoRA variant, 30,000 step은 **논문값이 아니라 공식 OpenPI 구현값**이다.
- `batch=1`, `workers=0`, `JAX memory=0.80`은 초기 1,000-step 검증값이고, 현재 YAML의 `batch=32`, `workers=2`, `JAX memory=0.70`은 다음 장기 실행을 위한 별도 설정이다.

> **쉽게 말하면:** 논문에 없는 숫자를 “논문 추천값”이라고 부르지 않는다. 논문값, 공개 코드값, 이 PC에서 직접 시험한 값을 따로 적었다.

원문:

- [π0 논문 PDF](https://www.physicalintelligence.company/download/pi0.pdf)
- [고정 OpenPI training config](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/training/config.py)
- [고정 OpenPI optimizer](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/training/optimizer.py)
- [고정 OpenPI model config](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/models/pi0_config.py)

## 3. 기존 run을 이어도 되는 변경

### 비교적 안전하게 바꿀 수 있는 값

- `num_train_steps`: 현재 checkpoint보다 큰 최종 step으로 연장
- `num_workers`: data loading 속도 조정
- `log_interval`, `save_interval`, `keep_period`: 기록과 저장 주기 조정
- `jax_memory_fraction`: 새 process에서 GPU pool 조정
- `progress_refresh_seconds`: TTY dashboard 화면 갱신 간격 조정

> **쉽게 말하면:** 모델이 배우는 내용은 유지하고, 더 오래 돌리거나 기록 빈도와 데이터 읽기 속도만 바꾸는 값들이다.

### 새 run이 필요한 값

- `dataset_root`, `asset_id`, norm stats
- `batch_size`, `seed`
- optimizer와 learning-rate schedule
- model variant, action horizon, dimension, EMA
- `finetuning.vision_encoder`의 `trainable`/ `frozen` 변경

> **쉽게 말하면:** 학습 데이터나 학습 수학, 학습할 parameter 범위가 달라지면 이전 실험에 이어 붙이지 말고 새 실험으로 분리한다.

Vision mode가 바뀌면 AdamW가 기억하는 parameter 묶음도 달라진다. 코드는 JSONL에 기록된 기존 mode와 요청 mode가 다르면 resume를 거부한다. Mode 기록이 없는 예전 로그는 `trainable`로 취급한다.

현재 legacy checkpoint에는 resolved config와 dataset hash가 저장되지 않는다. Resume할 때는 `dataset_root`, `asset_id`, norm stats, batch, seed가 원래 값과 같은지 사용자가 확인해야 한다.

## 4. 경로 설정

> **쉽게 말하면:** 아래의 dataset, asset, checkpoint 경로는 모두 `/home/pc/vla_ws` 내부를 가리켜야 한다. 외장 디스크나 이 workspace 밖의 폴더는 현재 설정에서 사용할 수 없다.

### `paths.dataset_root`

LeRobot v3 dataset을 읽을 위치다.

```text
dataset_root/
├── meta/
├── data/
└── videos/
```

현재값:

```text
data/datasets/two_block_pnp
```

> **쉽게 말하면:** 다운로드한 dataset 폴더 자체를 가리킨다. `meta`, `data`, `videos`의 부모 폴더를 적어야 한다.

새 dataset이면 `asset_id`와 norm stats도 바꾸고 새 run을 시작한다.

### `paths.assets_base_dir`

Normalization 통계를 저장하는 상위 폴더다.

```text
<assets_base_dir>/pi0_piper_lora/<asset_id>/norm_stats.json
```

π0는 joint 1~6을 delta action으로 바꾼 뒤 state/action의 평균과 표준편차를 사용한다. Hugging Face dataset의 raw `meta/stats.json`을 대신 사용하면 안 된다.

> **쉽게 말하면:** 관절값과 그리퍼값의 단위와 크기를 모델이 다루기 쉽게 바꾸는 기준표를 저장하는 곳이다.

### `paths.runs_root`

Checkpoint와 진단 로그를 저장할 상위 폴더다.

```text
<runs_root>/pi0_piper_lora/<run_name>/
```

현재 checkpoint 한 개는 약 `8.7GiB`다.

> **쉽게 말하면:** 학습 결과가 쌓이는 가장 큰 부모 폴더다. 마지막 실험 폴더 이름은 CLI의 `--run-name`으로 정한다.

Runs root를 기본값이 아닌 곳으로 바꿨다면 plot 명령에도 같은 경로를 전달해야 한다.

```bash
./scripts/training/plot_training.py \
  --runs-root <새 runs_root> \
  --run-name <run_name>
```

### `paths.base_params`

새 학습을 시작할 때 불러오는 공식 π0 base model 위치다.

> **쉽게 말하면:** 아무것도 모르는 모델부터 학습하는 것이 아니라, 이미 학습된 π0에서 시작하기 위한 초기 파일이다.

Resume할 때는 기존 checkpoint만 복원하므로 base params를 다시 읽지 않는다. `pi05_base`와 섞으면 안 된다.

### `dataset.asset_id`

Dataset과 norm stats를 연결하는 로컬 이름이다. Hugging Face의 `ORG/DATASET` 이름이 아니다.

```text
dataset leaf dirname == asset_id
```

처럼 맞추면 관리하기 쉽다. `/`는 사용할 수 없다.

> **쉽게 말하면:** 학습 코드가 “이 dataset에는 이 norm stats를 써야 한다”고 찾을 때 사용하는 짧은 이름이다.

## 5. 학습 횟수와 batch

### `training.num_train_steps`

학습이 도달할 **마지막 step 번호**다. 현재 step에 더하는 횟수가 아니다.

- 현재값: `30,000`
- 공식 구현 예제: `30,000`
- 로컬 검증: `10 -> 100 -> 1,000` save/resume 통과
- 실험 시작 범위: 대략 `10k~100k`, 실제 평가는 별도로 필요

> **쉽게 말하면:** 모델이 parameter를 몇 번 수정할지 정한다. Resume 상태가 1,000이고 목표가 30,000이면 29,000번 더 수정한다.

한 step은 `batch_size`개의 frame/action-window sample을 처리한다.

```text
sample_windows = num_train_steps * batch_size
nominal_passes = sample_windows / dataset_num_frames
```

공식 default, 현재 YAML, 초기 검증값은 다음처럼 구분한다.

```text
공식 OpenPI default: batch 32 * 30,000 = 960,000 windows
현재 YAML         : batch 32 * 30,000 = 960,000 windows
초기 안전 검증값  : batch  1 * 30,000 =  30,000 windows
```

> **쉽게 말하면:** 현재 YAML은 공식 default와 같은 nominal sample 수를 본다. 하지만 데이터 종류와 GPU 환경이 다르므로 같은 성능이나 안정성을 보장한다는 뜻은 아니다.

5k/10k/30k에서 실제 rollout 또는 held-out 평가로 계속 학습할지 결정한다.

### `training.batch_size`

한 번의 model update에서 같이 보는 sample 수다. 현재 trainer에는 gradient accumulation이 없다.

- 현재 YAML: `32`
- 공식 TrainConfig default: `32`; 논문 권장값은 아님
- 로컬 검증: batch `1`은 1,000 step, batch `8/16` smoke, batch `32`는 중간 실행까지 확인
- Loader 허용 상한: `32`; 장기 안정성 보장은 아님

> **쉽게 말하면:** `1`이면 sample 하나를 보고 한 번 수정한다. `32`이면 sample 32개의 결과를 평균 내 한 번 수정한다.

Batch가 커지면 gradient가 덜 흔들릴 수 있지만 activation memory와 한 step 시간이 늘 수 있다. Learning rate는 자동으로 바뀌지 않는다. Batch를 바꾸고 기존 run을 resume하지 않는다.

## 6. 데이터 읽기·로그·저장

### `training.num_workers`

영상과 Parquet을 미리 읽는 DataLoader 보조 process 수다.

- 현재값: `2`
- 공식 default: `2`
- 허용 범위: `0~8`
- 실험 순서: `0 -> 1 -> 2 -> 4`

> **쉽게 말하면:** GPU가 학습하는 동안 다음 데이터를 미리 준비할 작업자 수다. `0`이면 main process가 직접 읽는다.

현재 data loading은 약 `0.05s`, 전체는 약 `0.23s/step`이라 병목이 아니다. Data time이 전체의 30%를 넘을 때만 늘린다.

### `training.log_interval`

Loss, grad norm, parameter norm을 몇 step씩 묶어 평균 내고 기록할지 정한다.

- 현재값: `30`
- 공식 default: `100`
- 추천 범위: `10~100`

> **쉽게 말하면:** 현재 30,000-step 학습에서는 `30` step이 정확히 `0.1%`다. 따라서 실제 동기화된 진행률과 지표가 0.1%마다 갱신된다. 100-step smoke는 한 step 자체가 1%이므로 실제 진행률을 0.1% 단위로 만들 수 없다.

모델 update 계산 자체에는 영향을 주지 않는다.

### `training.save_interval`

Checkpoint를 몇 step마다 저장할지 정한다. 마지막 목표 step은 이 간격과 무관하게 저장된다.

- 현재값: `5,000`
- 공식 기본값: `1,000`
- 로컬 실측: 약 `8.7GiB`, `6~10초/회`
- 실험 범위: `1,000~5,000`

> **쉽게 말하면:** 전원이 꺼지거나 학습을 멈춰도 어디부터 다시 시작할 수 있을지를 정한다. 자주 저장하면 안전하지만 시간과 디스크를 더 쓴다.

### `training.keep_period`

오래 보관할 checkpoint 간격이다. 그 외 checkpoint는 최신 상태 중심으로 정리된다.

- 현재값/공식값: `5,000`
- 실험 범위: `5,000~10,000`
- 제약: `save_interval` 이상이며 그 배수

> **쉽게 말하면:** 현재는 5,000 step마다 저장하고 그 checkpoint를 장기 보관한다. 30,000 step이면 5k, 10k, 15k, 20k, 25k, 30k가 저장 대상이다.

5k 간격으로 30k까지 약 6개를 남기면 현재 크기로 약 `52GiB`가 필요하다. 임시 저장 공간은 별도다.

### `training.seed`

Dataset shuffle과 flow-matching noise를 만드는 시작 숫자다.

- 현재값/공식 default: `42`
- 첫 baseline 추천: `42`
- 최종 비교: `42/43/44` 또는 실제 rollout 반복

> **쉽게 말하면:** 같은 조건의 랜덤 선택을 다시 만들기 위한 번호다. 다른 seed는 같은 설정을 다시 시험하는 독립 실험이다.

Resume 시 DataLoader 위치는 저장되지 않으므로 같은 seed도 완전한 bitwise 재현은 아니다. Seed를 바꾸고 기존 run을 resume하지 않는다.

## 7. GPU memory 설정

### `runtime.jax_memory_fraction`

JAX/XLA가 사용할 수 있는 GPU memory pool 비율이다.

- 현재 YAML: `0.70`
- 초기 로컬 검증값: `0.80`
- OpenPI README 안내: 최대 활용 시 `0.90`
- Loader 허용 범위: `0.50~0.95`; 안전 보장은 아님

> **쉽게 말하면:** GPU memory 전체 중 JAX가 사용할 수 있는 최대 몫을 정한다. `0.70`은 48GiB 카드에서 이론상 약 33.6GiB 범위지만 driver와 다른 process 때문에 정확히 일치하지 않을 수 있다.

값을 낮춘다고 model 계산 자체가 작아지는 것은 아니다. 필요한 실제 memory보다 pool이 작으면 오히려 OOM이 난다.

다른 Jupyter kernel과 GPU process를 먼저 종료한다. 이 값은 JAX import 전 새 process에서 적용해야 한다.
### `runtime.progress_refresh_seconds`

TTY terminal의 5줄 dashboard를 몇 초마다 다시 그릴지 정한다.

- 현재값/추천 기본값: `1.0`초
- 허용값: `1.0~60.0`초
- 화면 움직임을 줄이고 싶을 때: `2.0`초
- SSH redirect와 non-TTY: 사용되지 않으며 background thread도 만들지 않음

> **쉽게 말하면:** `1.0`이면 spinner, 경과 시간, ETA를 1초마다 다시 보여준다. 모델을 1초마다 GPU와 동기화하는 설정은 아니다.

## 8. 잠긴 optimizer 설정

현재 `optimizer` 값은 공식 OpenPI baseline의 exact mirror다. YAML에서 바꾸면 실행이 거부된다.

> **쉽게 말하면:** 아래 값은 읽고 이해하기 위한 표시다. 실제 실험값으로 바꾸려면 새 Python profile을 만들어야 한다.

### `optimizer.name: adamw`

Gradient를 이용해 parameter를 수정하는 계산 방법이다.

> **쉽게 말하면:** 모델이 틀린 정도를 보고 내부 숫자를 어떤 방식으로 고칠지 정하는 규칙이다.

### `optimizer.b1: 0.9`

최근 gradient 방향을 얼마나 부드럽게 평균 낼지 정한다.

- 높이면 update가 부드럽지만 최근 변화에 느리다.
- 낮추면 반응이 빠르지만 noise에 민감하다.
- 실험 범위 `0.85~0.95`; 현재 추천 `0.9`.

### `optimizer.b2: 0.95`

Gradient 크기의 평균을 얼마나 오래 기억할지 정한다.

- 높이면 scale 추정이 안정적이지만 변화 적응이 느리다.
- 실험 범위 `0.95~0.999`.
- Learning rate와 같이 재검증해야 한다.

### `optimizer.eps: 1e-8`

0에 가까운 값으로 나누는 오류를 막는 작은 숫자다.

> **쉽게 말하면:** 계산이 불안정해져 NaN이 생기는 것을 막는 안전장치다. 특별한 원인 분석이 없으면 바꾸지 않는다.

### `optimizer.weight_decay: 1e-10`

Parameter가 지나치게 커지는 것을 줄이는 regularization 값이다. 현재 값은 사실상 끈 것과 가깝다.

OpenPI는 정확히 `0`일 때 일부 환경에서 OOM이 발생할 수 있어 `1e-10`을 사용한다.

> **쉽게 말하면:** 현재 baseline에서는 모델 숫자를 따로 줄이지 않는다. 일반 ML의 큰 weight decay 값을 그대로 넣지 않는다.

### `optimizer.clip_gradient_norm: 1.0`

한 번에 너무 큰 update가 생기지 않도록 전체 gradient 크기를 제한한다.

- 폭주 실험 후보: `0.5`
- 공식 baseline: `1.0`
- 지나치게 항상 제한될 때 후보: `2.0`

> **쉽게 말하면:** 모델이 한 step에서 너무 크게 흔들리지 않도록 gradient를 제한하는 상한이다. 로그의 raw grad norm이 1보다 크면 optimizer 적용 전 전체 gradient norm이 1 이하가 되도록 같은 비율로 줄어든다. 실제 parameter update 크기는 LR과 AdamW가 결정한다.

## 9. 잠긴 learning-rate 설정

Learning rate는 한 step에서 parameter를 얼마나 크게 바꿀지 정한다. 아래 exact 값은 논문이 아니라 공식 OpenPI 구현에서 왔다.

> **쉽게 말하면:** 너무 크면 학습이 흔들리고, 너무 작으면 거의 배우지 못한다.

### `lr_schedule.name: cosine_decay`

처음에는 LR을 올리고, 이후 부드러운 곡선으로 낮춘다.

### `lr_schedule.warmup_steps: 1000`

약 `2.50e-8`에서 peak LR까지 천천히 올리는 구간이다.

- 공식값: `1,000`
- 30k의 약 `3.33%`
- 실험 시작 범위: `500~2,000`

> **쉽게 말하면:** 학습 시작 직후 모델을 크게 바꾸지 않고 1,000 step 동안 변경 폭을 천천히 키운다. 1,000-step 검증은 warmup 종료이지 수렴 검증이 아니다.

### `lr_schedule.peak_lr: 2.5e-5`

Warmup 끝에서 도달하는 가장 큰 learning rate다.

- 보수적 후보: `1e-5`
- 공식 baseline: `2.5e-5`
- 공격적 후보: `5e-5`

> **쉽게 말하면:** 학습 중 모델을 가장 강하게 바꾸는 시점의 변경 크기다.

너무 크면 loss와 grad norm이 불안정하고, 너무 작으면 LoRA·vision·projection 적응이 느리다.

### `lr_schedule.decay_steps: 30000`

Warmup을 포함한 전체 schedule이 끝나는 step이다. 보통 최종 학습 step과 맞춘다.

> **쉽게 말하면:** 30,000 step에 도달할 때까지 LR을 서서히 낮춘다. 30k 이후에는 아래의 작은 끝값을 계속 사용한다.

### `lr_schedule.decay_lr: 2.5e-6`

Schedule 마지막과 그 이후의 learning rate다. Peak의 10%다.

실험 시작 범위는 peak의 `5~20%`지만 peak와 전체 step을 같이 설계해야 한다.

## 10. 잠긴 model과 Piper 계약

이 값은 tuning knob가 아니라 checkpoint, dataset 변환, norm stats, 추론 서버가 같이 지켜야 하는 구조다.

> **쉽게 말하면:** 학습과 추론이 같은 모양과 단위를 사용하도록 정한 약속이다. 하나만 바꾸면 다른 부분도 함께 고쳐야 한다.

### 모델 profile과 LoRA

```yaml
openpi_profile: pi0_libero_low_mem_finetune
pi05: false
paligemma_variant: gemma_2b_lora
action_expert_variant: gemma_300m_lora
```

`pi05`는 π0.5를 켜는 switch가 아니다. `true`로 바꾸면 현재 loader가 거부한다.

현재 profile은 base LLM을 고정하고 LoRA와 projection을 학습한다. Vision encoder는 아래 YAML 값으로 선택한다.

### `finetuning.vision_encoder`

```yaml
finetuning:
  vision_encoder: trainable
```

허용값과 CPU abstract model로 확인한 정확한 parameter 수는 다음과 같다.

| 값 | Vision에서 학습 | 전체 trainable | 전체 frozen | 의미 |
|---|---:|---:|---:|---|
| `trainable` | 414,803,696 | 468,039,440 (14.23%) | 2,819,996,672 | 카메라 특징도 데이터에 맞게 수정 |
| `frozen` | 0 | 53,235,744 (1.62%) | 3,234,800,368 | Vision은 고정하고 LoRA·projection만 수정 |

두 mode 모두 Gemma base LLM은 고정하고, 두 expert의 LoRA `49,987,584`개와 state/action/time projection `3,248,160`개는 학습한다.

> **쉽게 말하면:** `trainable`은 모델의 눈도 다시 가르친다. `frozen`은 기존 눈은 그대로 두고, 본 내용을 로봇 action으로 바꾸는 작은 부분만 가르친다.

새 카메라 위치·배경·조명이 base model과 많이 다르면 `trainable`부터 시작한다. VRAM 여유가 작거나 작은 dataset에서 과적합을 비교하려면 `frozen`을 별도 실험으로 실행한다. JAX는 memory pool을 미리 잡으므로 `nvidia-smi` 예약량이 바로 줄지 않을 수 있고, 아래 로그의 JAX `live` 값을 비교해야 한다.

**Mode를 바꿀 때는 반드시 새 `run_name`을 쓴다.** Parameter 모양은 같아도 AdamW optimizer state의 학습 대상 tree가 달라서 `trainable ↔ frozen` 교차 resume는 코드가 거부한다.

### `dtype: bfloat16`

Model 계산에 사용하는 숫자 표현이다. Trainable parameter는 float32, freeze filter에 걸린 parameter는 bfloat16으로 저장된다.

> **쉽게 말하면:** 큰 모델을 GPU memory에 맞게 계산하기 위해 일부 숫자를 더 작은 형식으로 처리한다.

### `action_dim: 32`

Model 내부 state/action 폭이다. Piper 관절 수가 아니다.

실제 7D를 앞 7칸에 넣고 나머지 25칸은 0으로 채운다.

> **쉽게 말하면:** 모델은 32칸짜리 입력 형식을 기대하고, Piper는 그중 7칸만 실제로 사용한다. 따라서 7로 줄이면 checkpoint와 맞지 않는다.

### `action_horizon: 50`

한 observation에서 예측하고 학습하는 미래 action 개수다.

- 논문값: `H=50`
- Piper 20Hz에서 시간: `2.5초`
- 일반 시작 범위: `10~50`
- 현재 추천: `50` 유지

> **쉽게 말하면:** 지금 화면 하나를 보고 앞으로 50개의 관절 명령을 예상한다.

예측한 50개를 로봇에서 한 번에 모두 실행할 필요는 없다. 추론 시 실제 실행할 action 개수는 별도 설정이다.

### `max_token_len: 48`

작업 문장을 token으로 바꿨을 때 허용하는 최대 길이다.

> **쉽게 말하면:** 모델에 넣는 명령 문장의 최대 길이다. 현재 단일 영어 task 문장은 48 안에 충분히 들어간다.

Truncation 경고가 있을 때만 64 등을 새 profile에서 검토한다.

### Piper action 의미

```yaml
robot_dim: 7
delta_joint_dim: 6
normalization: zscore
```

- 실제 차원: joint 1~6 + gripper 1
- Joint 1~6: `target action - current state` delta
- Gripper: absolute action 유지
- Normalization: 변환된 state/action의 평균과 표준편차 사용

> **쉽게 말하면:** 6개 관절은 현재 위치에서 얼마나 움직일지를 학습하고, 그리퍼는 목표 열림 정도를 그대로 학습한다.

이 계약이 틀리면 추론 역변환도 틀려 위험한 action이 나올 수 있다.

### Freeze, EMA, FSDP

```yaml
freeze_mode: official_lora_filter
ema_decay: null
fsdp_devices: 1
```

- `freeze_mode`: 항상 적용되는 공식 base non-LoRA LLM 동결 계약
- `finetuning.vision_encoder`: 위 공식 계약에 Vision 동결을 추가할지 선택
- `ema_decay: null`: 별도의 평균 parameter 복사본을 만들지 않음
- `fsdp_devices: 1`: GPU 한 장 사용

> **쉽게 말하면:** 큰 언어 모델은 항상 고정한다. Vision은 `trainable`이면 배우고 `frozen`이면 함께 고정한다. GPU 한 장을 쓰며 EMA 복사본은 만들지 않는다.

## 11. YAML 밖에 고정된 학습 동작

현재 source에서 자동으로 적용되는 값이다.

- 입력 영상은 `224x224`로 resize-with-pad된다.
- 외부 카메라는 95% random crop 뒤 resize하고 `-5~+5도` 회전한다.
- 모든 카메라는 brightness `0.3`, contrast `0.4`, saturation `0.5` color jitter를 적용한다.
- Flow timestep은 shifted Beta `(1.5, 1)` 계열로 뽑는다.
- Loss는 `50x32` action tensor의 flow-matching MSE다.

> **쉽게 말하면:** 같은 영상을 조금 자르고, 돌리고, 밝기와 색을 바꿔 보여 주면서 배경과 조명 변화에 덜 민감하도록 학습한다.

실제 7D 뒤의 25개 0도 loss에 들어간다. Episode 끝을 넘는 horizon은 마지막 action 반복으로 채우며 현재 loss mask로 제외하지 않는다.

이 값을 바꾸려면 YAML이 아니라 model/data source를 수정하고 새 profile을 검증해야 한다.

## 12. 실행 명령

### Conda 활성화

```bash
cd /home/pc/vla_ws
conda activate /home/pc/vla_ws/.conda/env
```

### 설정만 확인

```bash
./scripts/training/train_from_config.py \
  --config config/training/pi0_piper_lora.yaml \
  --print-config
```

### Model weight를 읽지 않는 data check

```bash
./scripts/training/train_from_config.py \
  --config config/training/pi0_piper_lora.yaml \
  --run-name preflight_check \
  --target-step 10 \
  --check-only
```

### 현재 step 1,000에서 30,000까지 resume

```bash
./scripts/training/train_from_config.py \
  --config config/training/pi0_piper_lora.yaml \
  --run-name background_400_0818_v3_r001 \
  --resume \
  --target-step 30000
```

`--target-step`은 추가 횟수가 아니라 마지막으로 도달할 step이다.

### Terminal 진행 표시와 JSONL 로그

실제 TTY terminal에서는 `runtime.progress_refresh_seconds`마다 아래 5줄 dashboard를 같은 위치에 덮어쓴다. 기본값은 1초다. 이 background 화면 thread는 JAX를 호출하지 않으며, `log_interval` 또는 checkpoint sync 때 main thread가 넘긴 마지막 숫자만 다시 보여준다. 한글과 block 문자의 실제 terminal 폭을 계산해 각 줄을 terminal 폭보다 한 칸 짧게 제한하므로 좁은 창에서도 자동 줄바꿈되지 않는다.

```text
[100/1000 steps]  10.0% 학습 중 [/] · Vision encoder 학습 · 다음 동기화 후 수치 갱신
[██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]
시간  경과 00:00:22 · ETA 00:03:18 · 1.23 step/s · 39.4 sample/s
지표  loss 0.024145 · grad_norm 0.874 · param_norm 1380 · 최근 구간 평균
JAX   사용/최고/상한 10.50/20.60/31.10 GiB · 33.8% · 최근 동기화 기준
```

- `[/]`: 학습 process가 살아 있음을 보여주는 `| / - \\` 순환 표시
- 첫 줄: GPU sync로 실제 확인한 마지막 step, 목표 진행률, Vision encoder 모드
- 굵은 막대: 채운 `█`, 남은 `░` 영역으로 전체 진행률 표시
- `시간/지표`: 계속 움직이는 경과 시간·ETA와 마지막 sync 구간의 평균 metric
- `JAX`: 마지막 sync의 현재 사용량, 최고값, allocator 상한과 사용률

첫 JIT가 끝나기 전에도 `compiling` dashboard와 spinner, 경과 시간이 먼저 보인다. 이때 ETA·metric·JAX 값은 `n/a` 또는 `--:--:--`다. 두 번째 sync부터 첫 JIT 구간을 제외한 평균으로 ETA를 계산한다.

> **쉽게 말하면:** 화면은 1초마다 움직여도 step, loss, JAX 숫자는 추측해서 올리지 않는다. `last sync step`이 그대로라면 GPU가 다음 구간을 계산 중이라는 뜻이다. `live`는 실제 tensor 사용량이고 `limit`은 JAX allocator 상한이다.

모든 상세 기록은 다음 파일에 JSONL schema v3으로 누적된다.

```text
<runs_root>/pi0_piper_lora/<run_name>/training_metrics.jsonl
```

SSH redirect 같은 non-TTY 환경에서는 움직이는 dashboard를 출력하지 않고 JSONL만 기록한다. 각 `session_start`, `train_step`, `failure`, `session_complete` record에 session과 Vision mode가 남으며, `train_step`에는 진행률·ETA·처리량·JAX memory가 들어간다. 기존 schema v2 record와 섞여도 plot은 공통 field를 그대로 읽는다.

### 진단 그래프 갱신

기본 `runs_root=data/runs`일 때:

```bash
./scripts/training/plot_training.py \
  --run-name background_400_0818_v3_r001
```

Runs root를 바꿨을 때:

```bash
./scripts/training/plot_training.py \
  --runs-root <새 runs_root> \
  --run-name <run_name>
```

생성된 SVG의 memory panel에는 JAX `used`, `peak`, `limit`과 host RSS가 함께 표시된다. Schema v2 로그에는 없던 `limit`은 해당 구간만 비어 있고, schema v3 record부터 선이 그려진다.

## 13. 추천 실험 순서

### 현재 YAML의 다음 장기 실험 설정

```text
batch=32
workers=2
log_interval=30 (30k 기준 0.1%)
checkpoint_interval=5000
vision_encoder=trainable
peak_lr=2.5e-5
warmup=1000
target=30000
JAX memory=0.70
```

이 값은 범용 권장값이나 30,000-step 완료 보장이 아니다. Batch 1의 1,000-step 안정성 검증 뒤 batch를 단계적으로 올렸고, batch 32 장기 실행은 중간에 사용자가 정상 중단했다. 코드 변경 뒤에는 새 run으로 짧은 smoke부터 다시 확인한다.

5k/10k/30k에서 다음을 확인한다.

- Train loss와 grad norm이 정상 숫자인가
- JAX live와 host memory가 계속 증가하지 않는가
- 학습에 없던 영상·배경에서 action이 타당한가
- 저속 실제 로봇 rollout 성공률이 좋아지는가

> **쉽게 말하면:** 로그가 정상이라고 학습 성공이 확정되는 것은 아니다. 실제 영상과 로봇 동작으로 확인해야 한다.

### 그다음 비교 실험

1. 현재 `trainable` 설정을 새 run에서 10 → 100 → 1,000 step 검증
2. YAML을 `frozen`으로 바꾸고 반드시 다른 run name으로 비교
3. Peak LR `1e-5 / 2.5e-5 / 5e-5` 비교
4. 최소 2~3개 seed 또는 반복 rollout 비교

한 실험에서는 한 가지 값만 바꾸고 새 run name을 사용한다.

## 14. 새 dataset으로 학습할 때

새 LeRobot v3 dataset은 다음 위치에 둔다.

```text
/home/pc/vla_ws/data/datasets/<dataset_folder>
```

다음 항목을 함께 준비한다.

1. `paths.dataset_root`
2. `dataset.asset_id`
3. 새 dataset 전용 `norm_stats.json`
4. 새 `run_name`

> **쉽게 말하면:** 새 데이터 폴더, 새 통계, 새 실험 이름을 한 묶음으로 준비한다.

### 새 데이터 전용 통계 생성

YAML에서 `dataset_root`와 `asset_id`를 새 값으로 바꾼 뒤 다음 명령을 실행한다.

```bash
cd /home/pc/vla_ws

./scripts/training/prepare_norm_stats.py \
  --config config/training/pi0_piper_lora.yaml
```

이 명령은 MP4와 GPU를 사용하지 않고 전체 Parquet 숫자만 읽는다. 관절 6축은 delta action으로, gripper는 absolute action으로 계산한다. 재현성을 위해 4,096 frame batch와 데이터 순서를 고정하며 기존 `norm_stats.json`은 덮어쓰지 않는다.

> **쉽게 말하면:** 새 데이터의 관절값·그리퍼값 평균과 표준편차를 만드는 준비 작업이다. Hugging Face의 raw `meta/stats.json`을 그대로 복사하는 작업이 아니다.

생성이 끝나면 실제 학습 batch를 CPU에서 검사한다.

```bash
./scripts/training/train_from_config.py \
  --config config/training/pi0_piper_lora.yaml \
  --run-name <새_dataset>_preflight \
  --target-step 10 \
  --check-only
```

`PASS: Piper v3 -> OpenPI π0 data contract`와 `PASS: run directory not created`가 모두 나와야 한다.

기존 `background_400_0818_v3_r001`을 새 dataset으로 resume하지 않는다.

## 15. π0.5 주의사항

`model_contract.pi05: true`만 설정하면 π0.5로 바뀌지 않는다.

π0.5에는 별도로 다음이 필요하다.

- `pi05_base/params`
- `ModelType.PI05`와 π0.5 전용 TrainConfig
- Quantile normalization과 discrete-state token 처리
- 별도 checkpoint namespace와 norm asset
- 1-step, save, 새 process resume 검증

> **쉽게 말하면:** 원본 LeRobot v3 dataset 파일은 π0와 π0.5에서 재사용할 수 있다. 하지만 현재 `PiperDataConfig`와 transform은 π0 전용이므로, π0.5용 구현과 별도 검증이 필요하다.

현재 `pi0_piper_lora.yaml`은 π0 전용이다.
