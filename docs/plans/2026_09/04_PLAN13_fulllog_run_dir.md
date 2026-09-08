---
date: 2026-09-04
task: fulllog 산출물을 실행 시각별 하위 디렉터리(logs/fulllog_YYYYMMDD_HHMMSS/)에 묶어 저장 + SIGTERM 도 SIGINT 처럼 정상 종료
planner: Claude
executor: codex
status: done
---

# PLAN13 — fulllog 실행 단위 디렉터리 + SIGTERM 정상 종료

## 한 줄 결론

`scripts/zed_fusion_fulllog.py` 가 지금은 `--outdir`(기본 `logs`) 바로 아래에 JSONL·meta·MP4 를
평평하게 쌓는다. 실행마다 **`<outdir>/fulllog_<stamp>/`** 디렉터리를 하나 만들고 그 안에
같은 이름으로 저장하도록 바꾼다(파일 이름은 그대로, 디렉터리만 추가). 더불어 **SIGTERM** 도
SIGINT 와 같은 stop 플래그 핸들러에 연결해 `kill`/터미널 닫힘에서도 MP4 가 정상적으로 닫히게 한다.
`--record-svo DIR` 의 동작은 바꾸지 않는다.

## 왜 이 plan 이 필요한가

- 촬영 1회 = 파일 4개(`.jsonl`, `_meta.json`, `_cam<serial>.mp4` ×2)라 `logs/` 루트가 빠르게
  어지러워진다. 세션별로 한 디렉터리에 묶여 있어야 복사·분석·대조가 편하다(사용자 요청, 2026-09-04).
- 2026-09-04 17:02 실측 로그의 MP4 는 Ctrl-C 로 끊었는데도 ffprobe/ffmpeg 전체 디코드가 통과했다.
  이유는 SIGINT 핸들러가 stop 플래그만 세워 루프가 정상 탈출하고 `finally` 에서
  `writer.release()` 가 불려 moov 가 기록되기 때문이다. 그러나 **SIGTERM 은 핸들러가 없어**
  `kill <pid>`·터미널 닫힘 시 `finally` 를 거치지 못하고 MP4 가 깨진다. 한 줄로 막을 수 있다.

## 지금까지 이어진 맥락 (self-contained)

- `zed_fusion_fulllog.py` 는 dual ZED-M Fusion 의 fused(BODY_34)/raw(BODY_18) 바디 전 필드,
  매 프레임 `record:"frame"` 하트비트, FusionMetrics 를 JSONL 로 기록하고 카메라별 LEFT MP4 를
  기본 저장한다. 레코드마다 `frame_idx` 가 MP4 프레임 번호와의 join 키다.
- 실행 진입은 보통 `python3 scripts/run_fusion.py fulllog --skip-calib -- <fulllog 옵션>` 이며,
  런처가 `--config logs/fusion_zed360.json` 을 붙여 이 스크립트를 부른다. 런처는 수정하지 않는다.
- `logs/**` 는 실측 로그 보관 디렉터리로 **기존 파일을 이동·삭제하지 않는다.** 이미 루트에 있는
  `fulllog_20260904_170220*` 은 그대로 둔다.

## 구현해야 할 것

**`scripts/zed_fusion_fulllog.py` 한 파일만 수정한다.**

1. **실행 디렉터리 생성** — `main()` 의 경로 준비 구간(현재 L236-239):
   ```python
   os.makedirs(args.outdir, exist_ok=True)
   stamp = time.strftime("%Y%m%d_%H%M%S")
   log_path  = os.path.abspath(os.path.join(args.outdir, "fulllog_%s.jsonl" % stamp))
   meta_path = os.path.abspath(os.path.join(args.outdir, "fulllog_%s_meta.json" % stamp))
   ```
   을 다음 의미로 바꾼다: `run_dir = os.path.abspath(os.path.join(args.outdir, "fulllog_%s" % stamp))`
   를 만들고 `os.makedirs(run_dir, exist_ok=True)`, `log_path`/`meta_path` 는 `run_dir` 아래에
   **같은 파일 이름**으로 둔다. 시작 시 `print("run dir ->", run_dir)` 한 줄을 추가한다.
2. **MP4 경로** — `_open_video_writers(senders, args.outdir, stamp, args.fps)` 호출(현재 L256)의
   두 번째 인자를 `run_dir` 로 바꾼다. 함수 본문(L162 의 `"fulllog_%s_cam%s.mp4"`)은 그대로 두면
   파일 이름이 유지된다.
3. **meta.json** — 기존 키는 전부 유지하고 `"run_dir": run_dir` 키 하나를 추가한다.
   `log_path`/`video_paths` 는 이미 절대경로를 쓰므로 자동으로 새 위치를 가리킨다.
4. **SIGTERM** — 현재 L294 `signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("value", True))`
   바로 아래에 같은 핸들러를 `signal.SIGTERM` 에도 등록한다. 핸들러 본체는 공유한다.
5. **`--outdir` help 문구** — "실행마다 `<outdir>/fulllog_<stamp>/` 하위 디렉터리를 만들어 저장"
   취지로 한 줄 갱신한다. 기본값 `logs` 는 유지.
6. **worklog** — `docs/worklog/2026-09-04.md` 의 Changes 표에 한 줄 append.

산출 구조(기대):
```
logs/fulllog_20260904_183000/
  fulllog_20260904_183000.jsonl
  fulllog_20260904_183000_meta.json
  fulllog_20260904_183000_cam13870389.mp4
  fulllog_20260904_183000_cam19321109.mp4
```

## 참고해야 할 것

- `scripts/zed_fusion_fulllog.py` L236-239 (경로 준비), L256 (`_open_video_writers` 호출),
  L149-172 (`_open_video_writers` — `outdir` 파라미터가 그대로 파일 경로의 부모가 됨),
  L270-290 (meta dict 구성과 저장), L294 (SIGINT 핸들러), L381-383 (`finally` 의 `release()`).
- `_enable_svo(sender, args.record_svo, stamp)` (L246, 함수 L130-146) — **건드리지 않는다.**
  `--record-svo DIR` 은 지정한 DIR 에 그대로 저장한다.

## 신경써야 할 것

- **JSONL 레코드 스키마·MP4 파일 이름·CLI 옵션 집합은 바꾸지 않는다.** 바뀌는 것은
  "파일이 놓이는 디렉터리" 와 meta 의 `run_dir` 키 추가, `--outdir` help 문구뿐이다.
- 종료 요약 print 는 이미 `log_path` 를 찍으므로 새 위치가 자동으로 나온다. 별도 변경 불필요.
- `scripts/run_fusion.py`·`zed_fusion_bodytrack.py`·`zed_fusion_viz.py` 수정 금지.
- `logs/` 의 기존 파일을 옮기거나 지우지 않는다.
- SIGTERM 핸들러는 stop 플래그만 세운다 — 핸들러 안에서 release/close 를 직접 부르지 않는다
  (정상 종료 경로는 `finally` 하나로 유지).
- 주석 한국어, 기존 파일 스타일 유지. 하드웨어 없음 — 정적 검증까지만.

## 이번에는 하지 않는 것

- `--record-svo` 를 실행 디렉터리로 통합하는 것(CLI 의미 변경) — 사용자 결정으로 제외.
- 파일 이름 단축(`bodies.jsonl` 등) — 제외. 파일을 밖으로 복사해도 출처가 남도록 stamp 유지.
- 기존 `logs/` 루트 산출물의 정리·이동.
- SIGKILL/크래시 대비(주기적 flush, 분할 저장 등).

## 근거

- 2026-09-04 17:02 실측: `fulllog_20260904_170220_cam*.mp4` 두 파일 모두 ffprobe 640 frames/30fps/
  21.33s, `ffmpeg -f null` 전체 디코드 에러 0 → Ctrl-C 종료 경로는 안전함이 확인됨. 같은 실행의
  JSONL 은 frame 628 / fused 626 / raw 1256 / metrics 20, `received_fps` 29.998 (MP4 인코딩이
  30fps 를 깎지 않음).
- `signal` 은 이미 import 돼 있고(L7) SIGINT 핸들러 패턴이 존재하므로 SIGTERM 추가는 한 줄이다.

## 검증

- `python3 -m py_compile scripts/zed_fusion_fulllog.py`
- `conda run -n zed python3 scripts/zed_fusion_fulllog.py --help` 정상 종료, 옵션 집합 불변,
  `--outdir` help 문구에 하위 디렉터리 설명 반영.
- 단위 수준: `--outdir /tmp/fl_test` 와 임의 stamp 로 경로 구성 로직만 흉내 내어
  `run_dir == /tmp/fl_test/fulllog_<stamp>` 이고 jsonl/meta/mp4 경로가 모두 그 아래이며
  파일 이름이 기존과 동일함을 확인.
- `signal.getsignal(signal.SIGTERM)` 이 SIGINT 와 같은 핸들러 객체인지 확인(핸들러 등록 직후
  단위 수준으로).
- 라이브(사용자): `run_fusion.py fulllog --skip-calib -- --duration 10` → `logs/fulllog_<stamp>/`
  안에 파일 4개 생성, meta.json 의 `run_dir`·`log_path`·`video_paths` 가 그 디렉터리를 가리킴.
  이어서 `--duration 0` 으로 실행 후 다른 터미널에서 `kill <pid>` → 종료 요약이 찍히고 MP4 가
  `ffprobe` 로 읽힘.

## 다음 단계

- 촬영 세션이 쌓이면 `logs/fulllog_<stamp>/` 단위로 분석 스크립트(velocity 지연·covariance
  특성) 입력을 잡는다.
