# 기존 vla_pipeline용 π0 서버

이 경로는 기존 `vla_pipeline`의 LeRobot 0.6 async client와 ROS publisher를 그대로
사용하고, 원격 policy server의 내부 모델만 OpenPI π0로 교체한다.

## 바뀌는 것과 유지되는 것

- 새 서버: LeRobot `transport.AsyncInference` gRPC 네 RPC를 그대로 제공한다.
- 새 서버: YAML이 고른 Orbax checkpoint와 내장 norm stats만 사용한다.
- 기존 client: observation 수집, action queue, chunk aggregation, 20 Hz 실행은 그대로다.
- 기존 ROS 경로: `/piper/inference/output` publisher와 rosbridge 코드는 바꾸지 않는다.

client의 `--pretrained_name_or_path`는 gRPC 호환상 필수지만 서버의 모델 경로로
사용하지 않는다. 실제 모델은 서버 YAML의 `checkpoint.run_name`과 `step`으로 고정된다.

## 서버 점검

```bash
cd /home/pc/vla_ws

./scripts/inference/serve_vla_pipeline.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml \
  --step 30000 \
  --check-only
```

## 서버 실행

```bash
cd /home/pc/vla_ws

./scripts/inference/serve_vla_pipeline.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml \
  --step 30000
```

기본 endpoint는 `127.0.0.1:8080`이다. client가 다른 PC에 있다면 YAML의 `host`를
`0.0.0.0` 또는 GPU 서버의 신뢰된 LAN 주소로 바꾸고, client의 `--server_address`에는
`GPU_SERVER_IP:8080`을 넣는다. 이 프로토콜은 인증이 없고 pickle 호환 형식을
사용하므로 공용 네트워크에 노출하면 안 된다.

## 기존 client 실행 형태

```bash
PYTHONPATH=/path/to/vla_pipeline python -m piper_bridge.async_client \
  --server_address=GPU_SERVER_IP:8080 \
  --robot.type=piper_bridge \
  --policy_type=pi0 \
  --pretrained_name_or_path=two_block_pnp_b32_vt_s30000_r002/30000 \
  --task="pick up the green blocks one at a time and place them in the white box" \
  --policy_device=cuda \
  --client_device=cpu \
  --actions_per_chunk=50 \
  --chunk_size_threshold=0.5 \
  --aggregate_fn_name=weighted_average \
  --fps=20
```

서버는 client의 raw key `joint_1.pos`~`joint_6.pos`, `gripper.pos`, `wrist`,
`third_person`, `task`를 검증해 OpenPI canonical observation으로 바꾼다. 응답은
기존 client가 기대하는 `list[TimedAction]`이며 각 action은 CPU torch tensor 7차원,
간격은 0.05초다.

현재 범위는 기본 추론과 실행이다. session metadata 및 `inference_log.jsonl`용
event publisher는 이 서버 호환 작업에 포함하지 않는다.

## 현재 검증 상태

- 공식 LeRobot 0.6 proto field 번호와 네 RPC path를 CPU 테스트로 고정했다.
- 실제 client 순서인 Ready → instruction → observation → actions loopback이 통과했다.
- step 30000의 완료 checkpoint와 내장 norm stats `--check-only`가 통과했다.
- 실제 GPU weight restore·첫 JIT·다른 PC의 client·실제 로봇 E2E는 아직 실행하지 않았다.

따라서 코드는 서버 기동 직전 단계까지 완성됐지만, 실제 장비 운영 완료 판정은 GPU
smoke와 기존 client 연결 테스트 뒤에 내린다.
