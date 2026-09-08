# π0.5 추론 실행 파일

- `serve_policy.py`: OpenPI WebSocket policy server
- `serve_vla_pipeline.py`: LeRobot 0.6 AsyncInference gRPC 호환 server
- `run_vla_pipeline_client.py`: 기존 Piper sync/async client launcher

모든 server launcher는 설정과 checkpoint를 먼저 검사한다. `--check-only`에서는
JAX/OpenPI policy/GPU를 초기화하지 않는다.
