# π0.5 추론 설정

- `piper_inference.yaml`: OpenPI WebSocket 직접 연결용
- `piper_vla_pipeline.yaml`: 기존 LeRobot 0.6 sync/async client 연결용

두 파일 모두 `pi05_piper_lora` checkpoint와 checkpoint 내부의 quantile
`assets/<asset_id>/norm_stats.json`을 사용한다. 외부 학습 asset으로 조용히 대체하지 않는다.

중요 설정은 다음 네 묶음이다.

1. `checkpoint`: run 이름, asset id, 정확한 완료 step
2. `policy`: 학습 task와 같은 prompt, Euler 추론 횟수
3. `server`: bind 주소와 port
4. `runtime`: JAX GPU allocator 비율

`piper_vla_pipeline.yaml`에는 `client`가 추가된다. `mode`, 실행 시간, chunk 크기,
20Hz 주기와 async queue 합성 방식을 고른다. 자세한 실행 예시는
[`../../../docs/inference/pi05/README.md`](../../../docs/inference/pi05/README.md)에 있다.
