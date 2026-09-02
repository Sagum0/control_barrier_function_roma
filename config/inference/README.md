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
| 실행 파일 | `scripts/inference/serve_policy.py` | `scripts/inference/serve_vla_pipeline.py` |
| 기본 포트 | `8000` | `8080` |
| 입력 방식 | RGB 영상 2개, 7D state, prompt를 직접 전송 | LeRobot feature handshake와 observation queue 사용 |
| 출력 방식 | `(50, 7)` absolute action 배열 | timestamp가 포함된 `TimedAction` chunk |
| 비동기 chunk 설정 | 없음 | chunk 크기, 교체 시점, 집계 방식, FPS 설정 가능 |
| YAML schema | `1` | `2` |

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
  --config config/inference/pi0_piper_vla_pipeline.yaml \
  --step 30000
```

같은 YAML을 반영한 Piper PC client 명령은 다음과 같이 생성한다.

```bash
./scripts/inference/serve_vla_pipeline.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml \
  --step 30000 \
  --print-client-command
```

### 새 WebSocket adapter를 사용할 때

```bash
./scripts/inference/serve_policy.py \
  --config config/inference/pi0_piper_inference.yaml \
  --step 30000
```

## 추가 문서

- 비동기 chunk 파라미터 상세 설명:
  [VLA_PIPELINE_PARAMETERS.md](./VLA_PIPELINE_PARAMETERS.md)
- 서버 실행·입출력·ROS 계약:
  [추론 문서](../../docs/inference/README.md)
