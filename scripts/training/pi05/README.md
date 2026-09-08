# π0.5 학습 명령

- `train_from_config.py`: strict YAML wrapper
- `train.py`: JAX/OpenPI low-level trainer
- `watch_training.py`: JSONL 진행 상황 대시보드
- `plot_training.py`: 완료된 JSONL을 SVG로 변환

기본 smoke:

```bash
./scripts/training/pi05/train_from_config.py \
  --config config/training/pi05/piper_lora.yaml \
  --run-name two_block_pnp_b1_pi05_vf_s10_r001 \
  --target-step 10
```

`--target-step`은 추가 횟수가 아니라 absolute 종료 step이다. 같은 run을 이어갈 때만 `--resume`을 붙인다.
