# Piper π0 VLA workspace

이 workspace는 학습과 추론 코드를 서로 다른 production 경로로 관리한다.

```text
src/piper_vla/
├── training/       # dataset, normalization, trainer, diagnostics
└── inference/      # checkpoint, observation, policy server, robot contract

scripts/
├── training/       # 학습·통계·plot·monitor CLI
└── inference/      # 정책 서버 CLI

config/
├── training/       # 학습 YAML
└── inference/      # 추론 YAML
```

## 학습

```bash
./scripts/training/train_from_config.py \
  --config config/training/pi0_piper_lora.yaml \
  --run-name RUN_NAME \
  --target-step 30000
```

## 추론 checkpoint 검사

```bash
./scripts/inference/serve_policy.py \
  --config config/inference/pi0_piper_inference.yaml \
  --step 30000 \
  --check-only
```

## 기존 vla_pipeline용 gRPC 서버·client

```bash
# terminal: model server
./scripts/inference/serve_vla_pipeline.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml

# terminal: robot client
./scripts/inference/run_vla_pipeline_client.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml
```

두 명령 모두 YAML의 checkpoint step을 먼저 검증한다. client launcher는 `lerobot-060`
Python을 자동으로 사용하며 `client.mode`에 따라 기존 비동기 client 또는 vla_ws 동기
client를 선택한다. 실행 시간, prompt, 서버 주소, chunk와 FPS도 같은 YAML에서 적용한다.

실행·원격 client 주소 설정은
[`docs/inference/VLA_PIPELINE_SERVER.md`](./docs/inference/VLA_PIPELINE_SERVER.md)에 있다.

상세 문서는 [`docs/README.md`](./docs/README.md)에 있다.
