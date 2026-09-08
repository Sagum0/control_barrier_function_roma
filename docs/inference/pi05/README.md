# Piper π0.5 추론

π0.5 추론은 학습 때와 같은 모델 계약을 그대로 복원한다.

- `Pi0Config(pi05=True)`
- prompt 최대 200 token과 discrete state 입력
- checkpoint 안의 quantile normalization 통계
- 출력 `(50, 7)`: 6개 관절 rad + gripper m의 absolute action

π0 checkpoint나 z-score asset을 π0.5 설정에 넣으면 namespace 검증에서 거부된다.

## 1. OpenPI WebSocket 검사와 실행

```bash
./scripts/inference/pi05/serve_policy.py \
  --config config/inference/pi05/piper_inference.yaml \
  --check-only

./scripts/inference/pi05/serve_policy.py \
  --config config/inference/pi05/piper_inference.yaml
```

기본 port는 π0의 8000과 다른 8001이다.

## 2. 기존 vla_pipeline 검사와 실행

```bash
./scripts/inference/pi05/serve_vla_pipeline.py \
  --config config/inference/pi05/piper_vla_pipeline.yaml \
  --check-only

./scripts/inference/pi05/serve_vla_pipeline.py \
  --config config/inference/pi05/piper_vla_pipeline.yaml
```

로봇 PC에서는 같은 YAML을 읽는 client launcher를 실행한다.

```bash
./scripts/inference/pi05/run_vla_pipeline_client.py \
  --config config/inference/pi05/piper_vla_pipeline.yaml
```

`client.mode: sync`는 chunk 추론 후 순차 실행하고, `async`는 기존 LeRobot queue와
aggregation으로 추론과 action 실행을 겹친다. π0.5 gRPC handshake는 `policy_type=pi05`로
고정되어 π0 client의 잘못된 접속을 거부한다.

## 3. vision-trainable checkpoint 사용

YAML의 `checkpoint.run_name`만 아래처럼 바꾼다.

```yaml
checkpoint:
  run_name: two_block_pnp_pi05_b32_vt_s30000_r001
  step: 30000
```

vision frozen/trainable은 학습 방법의 차이다. 둘 다 추론 출력 계약은 같지만 같은 서버
process에 두 checkpoint를 동시에 적재하지 않는다.
