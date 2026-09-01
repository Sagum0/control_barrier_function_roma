# 추론 CPU 테스트

이 디렉터리의 테스트는 모델 weight를 복원하거나 GPU를 초기화하지 않는다.

```bash
cd /home/pc/vla_ws
PYTHONPATH=src .conda/env/bin/python -m unittest discover \
  -s tests/inference \
  -p 'test_*.py' \
  -v
```

현재 검사 범위는 다음과 같다.

- YAML 중복 key와 strict schema
- 숫자 커밋 완료 checkpoint 선택
- Orbax 임시 디렉터리 제외
- checkpoint 내 7차원 norm stats
- RGB `(480, 640, 3)`와 state `(7,)` canonical 입력
- finite absolute action `(50, 7)` 출력
- OpenPI policy 앞뒤의 입출력 검증 wrapper

실제 step 30000 weight restore, 첫 JIT, inference latency는 학습이 끝난 뒤 별도 GPU
smoke로 검사한다. ROS2 action 발행은 그 다음 단계이며 이 테스트에서는 실행하지 않는다.
