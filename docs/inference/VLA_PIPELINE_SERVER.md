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

모델·chunk·queue·합성 파라미터의 쉬운 설명은
[`VLA_PIPELINE_PARAMETERS.md`](../../config/inference/VLA_PIPELINE_PARAMETERS.md)에 있다.

## 서버 점검

```bash
cd /home/pc/vla_ws

./scripts/inference/serve_vla_pipeline.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml \
  --check-only
```

## 같은 설정의 client 점검

```bash
./scripts/inference/run_vla_pipeline_client.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml \
  --print-command
```

이 명령은 로봇 제어 client를 시작하지 않고 checkpoint 존재 여부와 실제 적용될 YAML 값,
`PIPER_EPISODE_TIME_S`, 내부 client 명령만 출력한다.

## 서버 실행

```bash
cd /home/pc/vla_ws

./scripts/inference/serve_vla_pipeline.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml
```

위 세 명령은 YAML의 `checkpoint.step`을 사용한다. 선택한 step의 완료 checkpoint가 없거나
필수 params·norm stats 검증에 실패하면 서버는 다른 step으로 대체하지 않고 종료한다.
일회성으로만 다른 step을 시험할 때는 `--step N`으로 YAML 값을 덮어쓸 수 있다.

기본 endpoint는 `127.0.0.1:8080`이다. client가 다른 PC에 있다면 YAML의 `host`를
`0.0.0.0` 또는 GPU 서버의 신뢰된 LAN 주소로 바꾸고, client의 `--server_address`에는
`GPU_SERVER_IP:8080`을 넣는다. 이 프로토콜은 인증이 없고 pickle 호환 형식을
사용하므로 공용 네트워크에 노출하면 안 된다.

## 기존 client 실행 형태

```bash
cd /home/pc/vla_ws

./scripts/inference/run_vla_pipeline_client.py \
  --config config/inference/pi0_piper_vla_pipeline.yaml
```

`async_client.episode_time_seconds: 35`는 control loop 시작 후 35초에 client를 정상
종료한다. `null`로 바꾸면 launcher가 `PIPER_EPISODE_TIME_S`를 빈 값으로 강제해 이전
shell 설정과 관계없이 무제한으로 실행한다. launcher는 `lerobot-060` Python으로 자동
전환하고 기존 `/home/pc/vla_pipeline/piper_bridge/async_client.py`의 검증된 제어 루프를
호출한다. 따라서 `lerobot` shell 함수나 긴 client 인자를 직접 입력하지 않는다.

서버와 client에서 일회성 `--step N` 또는 `--latest`를 사용할 때는 반드시 양쪽에 같은
옵션을 준다. 보통은 두 명령 모두 옵션 없이 실행해 YAML의 `checkpoint.step`을 공유한다.

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
