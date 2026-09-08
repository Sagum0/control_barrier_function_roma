---
date: 2026-09-03
task: fulllog 에 매 프레임 하트비트 레코드(record:"frame") 추가 — 사람 없음 구간을 명시적으로 기록
planner: Claude
executor: codex
status: done
---

# PLAN12 — fulllog 프레임 하트비트 레코드

## 한 줄 결론

`scripts/zed_fusion_fulllog.py` 는 사람이 검출 안 된 프레임에 아무 레코드도 안 쓴다.
융합 처리된 **매 프레임마다 `record: "frame"` 한 줄**(frame_idx, 타임스탬프, n_bodies,
body_ids)을 추가해 30Hz 연속 타임라인을 만든다. 사람 없음 = `n_bodies: 0` 인 frame 레코드.
null 을 채운 더미 바디 레코드는 만들지 않는다 — NaN 채움은 분석 시 frame 레코드와
outer join 으로 얻는다(사용자 합의, 2026-09-03).

## 맥락 (self-contained)

- `scripts/zed_fusion_fulllog.py`(PLAN11, 2026-09-03 구현)는 dual ZED-M Fusion 의
  fused(BODY_34)/raw(BODY_18) 바디 전 필드 + FusionMetrics 를 JSONL 로 기록하고,
  카메라별 LEFT MP4 를 기본 저장하며 모든 레코드에 `frame_idx`(raw=int,
  fused=serial→int dict)를 넣는다. 레코드는 `record` 키("fused"/"raw"/"metrics")로 구분.
- 직렬화 규약: `json.dumps(..., allow_nan=False)` — NaN/inf 는 null 로 치환돼 있어야 한다.
- fused/raw 는 `body_list` 순회라 사람이 0명인 프레임에는 줄이 하나도 안 쓰인다.
  metrics 는 `--metrics-every`(기본 30) 프레임마다만 쓰인다.

## 구현해야 할 것

**`scripts/zed_fusion_fulllog.py` 한 파일만 수정한다.**

1. 메인 루프에서 `fusion.retrieve_bodies()` 성공 직후(= `n_frames` 증가하는 지점),
   fused/raw 레코드 기록 **앞에** 매 프레임 다음 한 줄을 쓴다:
   ```json
   {"record": "frame", "frame_idx": {"13870389": 12, "19321109": 12},
    "t_sdk_ns": ..., "t_wall_ns": ..., "n_bodies": 2, "body_ids": [0, 3]}
   ```
   - `frame_idx` 는 기존 fused 레코드와 같은 serial→int dict (`fused_frame_idx` 재사용).
   - `t_sdk_ns` 는 기존 `_timestamp_ns(fused)`, `t_wall_ns` 는 기존 `t_wall_ns` 재사용.
   - `n_bodies` = `len(fused.body_list)`, `body_ids` = fused body 들의 `id` 리스트(빈 리스트 가능).
2. 종료 요약 print 와 stdout 라이브 카운터에 frame 레코드 수를 추가한다
   (기존 `frames=... fused=...` 라인에 필드 하나 추가 수준).
3. CLI 플래그는 추가하지 않는다 — 하트비트는 항상 켜져 있다(프레임당 ~100B, 부담 없음).
4. worklog `docs/worklog/2026-09-03.md` 에 Changes 한 줄 append.

## 참고해야 할 것

- `scripts/zed_fusion_fulllog.py` 메인 루프 L302-361 — 삽입 지점(`n_frames += 1` 이후,
  fused body 순회 이전)과 재사용 변수(`fused_frame_idx`, `t_wall_ns`) 확인.
- 같은 파일 `_write_record()` — 직렬화 헬퍼. 새 레코드도 이것으로 쓴다.

## 신경써야 할 것

- **기존 fused/raw/metrics 레코드의 키·의미는 한 글자도 바꾸지 않는다** (이미 스키마로
  안내됨). frame 레코드는 순수 추가다.
- `scripts/zed_fusion_bodytrack.py`·`zed_fusion_viz.py`·`run_fusion.py` 수정 금지.
- `allow_nan=False` 통과 유지(frame 레코드는 NaN 이 생길 필드가 없다).
- 주석 한국어, 기존 파일 스타일 유지. 하드웨어 없음 — 정적 검증까지만.

## 이번에는 하지 않는 것

- null/NaN 을 채운 더미 바디 레코드 — 의도적으로 배제(분석 시 outer join 으로 대체).
- grab 실패 프레임의 기록(하트비트는 융합 처리 성공 프레임 기준 — grab 실패는 지금처럼
  frame_idx 공백으로 남는다).
- 분석 스크립트, 스키마 문서화 별도 파일.

## 검증

- `python3 -m py_compile scripts/zed_fusion_fulllog.py`
- `conda run -n zed python3 scripts/zed_fusion_fulllog.py --help` 정상 종료(옵션 변화 없음).
- 단위 수준: 빈 `body_list` 상황을 흉내 내 frame 레코드 dict 를 만들어
  `json.dumps(..., allow_nan=False)` 통과 + `n_bodies: 0`, `body_ids: []` 확인.
- 라이브(사용자): 빈 방 5초 + 사람 등장 5초 촬영 → jsonl 에서 (1) frame 레코드가 매
  프레임 존재, (2) 사람 없는 구간 `n_bodies: 0`, (3) 사람 구간에서 frame 다음에 fused 가
  따라오고 `body_ids` 가 fused 의 id 와 일치.

## 다음 단계

- 라이브 로그 수집 → frame 레코드 기준 30Hz 타임라인으로 velocity 지연·covariance 특성 분석.
