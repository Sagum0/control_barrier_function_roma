---
date: 2026-09-03
task: 융합·raw 바디 데이터의 SDK 전 필드를 JSONL 로 남기는 전용 로거 스크립트 추가 (+SVO2 녹화 옵션)
planner: Claude
executor: codex
status: done
---

> 승인 근거: 2026-09-03 사용자가 `/run-plan`(모델 gpt-5.6-sol high 지정)으로 본 plan 실행을
> 직접 지시함 — Claude 가 임의로 바꾼 것이 아님.

# PLAN11 — 전 필드 raw 로깅 (zed_fusion_fulllog.py)

## 한 줄 결론

`sl.BodyData` 22개 속성 중 현재 JSONL 은 8개만 기록한다. **새 스크립트
`scripts/zed_fusion_fulllog.py`** 를 추가해 fused(BODY_34)·raw(BODY_18) 바디의 **전 필드 +
`Bodies.timestamp` + `FusionMetrics`** 를 JSONL 로 남긴다. 저장 포맷은 ROS2 bag 이 아니라
**Python JSONL** 로 확정한다(탐색 단계라 스키마 자유가 필요, bag 은 커스텀 msg 확정 후 별도
plan). **이미지는 기본으로 무조건 저장한다** — 카메라별 LEFT 영상을 MP4 로 남기고 모든
레코드에 `frame_idx` 를 넣어 JSONL 과 프레임 단위로 join 할 수 있게 한다(사용자 결정,
2026-09-03). 추가로 `--record-svo` 를 켜면 SVO2(원본 좌/우+IMU, 오프라인 재추출용)도 녹화한다.
기존 검증 스크립트는 수정하지 않고 헬퍼만 import 재사용한다.

## 왜 이 plan 이 필요한가

- CBF 입력 설계 전에 "SDK 가 주는 값 중 뭐가 쓸모 있는지"를 데이터로 판단하고 싶다.
  특히 `velocity`(칼만 기반, 지연 보고됨), `position_covariance`, `keypoints_covariance`
  (관절별 3x3 압축 6원소)가 실제 리그에서 어떤 특성을 보이는지 실측이 없다.
- Fusion 이 confidence/covariance 를 다카메라 합의로 재계산하는지, sender 값을 그대로
  넘기는지 공식 문서에 없다 → 로그로만 확인 가능하다.
- 현재 로그의 공백: `zed_fusion_bodytrack.py` 의 `_body_record()` 는 8개 속성만 기록하고,
  SDK 이미지 타임스탬프(`Bodies.timestamp`) 대신 `time.time()` 을 쓰며, `FusionMetrics` 는
  `output_performance_metrics` 를 켜 놓고도 호출하지 않는다.

## 지금까지 이어진 맥락 (self-contained 재서술)

- 리그: ZED-M 2대(S/N 13870389, 19321109), SDK 5.4, conda `zed` env, **2×HD720@30 고정**
  (USB 컨트롤러 1개, @60 붕괴). 좌표계 `RIGHT_HANDED_Z_UP_X_FWD` / METER.
- 파이프라인: 각 카메라 sender 가 BODY_18 검출 → `sl.Fusion` 이 ZED360 캘리브
  (`logs/fusion_zed360.json`)로 융합 → **BODY_34 @ fusion world frame**. 진입점
  `scripts/run_fusion.py` 가 캘리브 게이트 후 대상 스크립트를 실행한다.
- pyzed 5.4.0 introspection 실측(2026-09-03): `sl.BodyData` 속성 22개 확인. 그중
  `keypoint_2d`, `bounding_box_2d`, `head_bounding_box_2d`, `mask` 는 **fused 출력에서
  비어 있다**(이미지 공간 필드, Stereolabs 포럼 확인) — raw sender 레코드에서만 의미 있다.
- Python 속성명은 `keypoints_covariance`(C++ 는 `keypoint_covariances`) — 이름 불일치가
  있으니 `getattr` 로 양쪽 다 시도한다.

## 지금 기준 판단

- **JSONL(py 스크립트) 채택, bag 보류**: 탐색 단계에는 필드 추가/제거가 잦아 스키마-프리
  포맷이 맞다. bag 은 (1) 커스텀 msg 정의·colcon build 선행 필요, (2) 브리지가 현재
  id+keypoint 만 발행하므로 브리지 대개조가 필요, (3) 분석은 결국 pandas 로 한다.
  다운스트림 소비 필드가 확정되면 그때 커스텀 msg + bag plan 을 따로 세운다.
- **SVO2 가 진짜 raw**: JSONL 은 "이번 실행의 파라미터로 SDK 가 계산한 결과"만 남는다.
  SVO2 를 함께 녹화하면 나중에 다른 파라미터(smoothing, fitting, min-cameras 등)로
  오프라인 재추출이 가능하다. 기본 off 옵션으로 넣는다.
- **새 파일 원칙 준수**: `zed_fusion_bodytrack.py` 는 런타임 변경 금지 대상이므로 손대지
  않고, 새 스크립트가 그 모듈의 헬퍼를 import 한다.

## 구현해야 할 것

1. **`scripts/zed_fusion_fulllog.py` (신규)** — 실행 루프는 `zed_fusion_bodytrack.py` 와 동일
   구조(2 sender open → fusion subscribe → grab/process 루프). 다음 헬퍼를 **import 재사용**
   (복사 금지): `_open_sender`, `_read_config`, `_init_fusion`, `_available_serials`,
   `_camera_identifier`, `_status_failed`, `_tolist`, `_enum_text`.
   - CLI 는 bodytrack 과 동일한 공통 인자(`--config`(필수)/`--res`/`--fps`/`--depth`/`--conf`/
     `--duration`/`--outdir`/`--min-keypoints`/`--min-cameras`/`--smoothing`/`--retry-count`/
     `--retry-wait`/`--verbose-fusion`) + 신규 `--record-svo`, `--metrics-every N`(기본 30프레임),
     `--no-raw`(기본은 raw 도 기록), `--no-video`(영상 저장 끄기 탈출구 — 기본은 저장).
   - 출력: `logs/fulllog_YYYYmmdd_HHMMSS.jsonl` + `..._meta.json`(전체 CLI 인자, config 경로,
     SDK 버전, serial 목록, body_format, 좌표계 문자열, 영상 파일 경로 목록 기록).
   - **이미지 저장(기본 on)**: grab 성공한 프레임마다 각 카메라의
     `retrieve_image(sl.VIEW.LEFT)` 를 `cv2.VideoWriter`(mp4v, 카메라 fps)로
     `logs/fulllog_<ts>_cam<serial>.mp4` 에 기록한다. BGRA→BGR 변환 필요.
     각 카메라의 현재 영상 프레임 번호를 `frame_idx` 로 세어 아래 레코드에 넣는다
     (JSONL↔MP4 프레임 join 키). VideoWriter open 실패 시 즉시 에러로 중단한다 —
     이미지는 필수 산출물이므로 조용히 건너뛰지 않는다.
2. **레코드 스키마** — 한 줄 = 한 레코드, `record` 키로 구분:
   - `record: "fused"` (프레임당 바디별): `id, unique_object_id, tracking_state, action_state,
     confidence, position, velocity, position_covariance, dimensions, bounding_box,
     head_position, head_bounding_box, keypoint, keypoint_confidence, keypoints_covariance,
     local_position_per_joint, local_orientation_per_joint, global_root_orientation` +
     `t_sdk_ns`(**`Bodies.timestamp.get_nanoseconds()`**), `t_wall_ns`(`time.time_ns()`),
     `is_new, is_tracked, body_format, frame: "fusion_world"`,
     `frame_idx`(**serial→해당 루프의 영상 프레임 번호 dict** — fused 는 특정 카메라에
     안 묶이므로 양쪽 다 기록).
     2D 필드(`keypoint_2d` 등)와 `mask` 는 fused 레코드에서 **기록하지 않는다**(항상 빈 값).
   - `record: "raw"` (카메라별, `--no-raw` 아니면): 위 필드 전부 + `keypoint_2d,
     bounding_box_2d, head_bounding_box_2d` + `serial_number`, `frame: "camera"`,
     `frame_idx`(해당 카메라 MP4 의 프레임 번호 int).
     mask 는 세그멘테이션 미사용이므로 제외.
   - `record: "metrics"` (`--metrics-every` 주기): `Fusion.get_process_metrics()` 결과 —
     `mean_camera_fused, mean_stdev_between_camera` + serial 별 `{delta_ts, is_present,
     ratio_detection, received_fps, received_latency, synced_latency}`.
   - 직렬화: numpy 는 `_tolist` 로, **NaN/inf 는 `null` 로 치환**한다
     (`json.dumps(..., allow_nan=False)` 가 통과해야 함 — 기존 로그의 비표준 `NaN` 리터럴
     문제 재발 금지). enum 은 `_enum_text` 로 문자열화.
   - `keypoints_covariance` 는 `getattr(body, "keypoints_covariance", None) or
     getattr(body, "keypoint_covariances", None)` 방어 접근.
3. **`--record-svo DIR`** — 각 sender open 직후 `sl.RecordingParameters`(H264)로
   `enable_recording` 을 걸어 `DIR/svo_<serial>_<ts>.svo2` 저장. 실패 시 경고만 하고
   로깅은 계속한다(녹화는 부가 기능).
4. **`scripts/run_fusion.py` 의 `TARGETS` dict 에 한 줄 추가**:
   `"fulllog": "zed_fusion_fulllog.py"`. 다른 로직은 건드리지 않는다.
5. **worklog** — `docs/worklog/2026-09-03.md` 에 Changes 추가 (파일이 이미 있으니 append).

## 참고해야 할 것

- `scripts/zed_fusion_bodytrack.py` — 재사용할 헬퍼의 시그니처와 grab 루프 구조
  (L277 이후 main), `retrieve_bodies(..., sl.FUSION_REFERENCE_FRAME.WORLD)` 호출 형태(L391),
  sender 별 raw `retrieve_bodies`(L385). fulllog 도 동일하게 WORLD 프레임으로 뽑는다.
- `scripts/zed_fusion_viz.py` — headless 가드(DISPLAY 검사) 패턴. fulllog 는 GUI 가 없으므로
  가드 불필요하지만 Ctrl-C 정리(finally 에서 close/unsubscribe) 패턴을 따른다.
- pyzed introspection 결과(위 "맥락" 절) — 필드명·shape 의 단일 근거. 문서와 다르면
  introspection(실제 5.4.0 바이너리)이 우선.
- `logs/fusion_zed360.json` — 실행 시 `--config` 로 받는 캘리브. **읽기 전용.**

## 신경써야 할 것

- **`scripts/zed_fusion_bodytrack.py`·`zed_fusion_viz.py` 는 한 줄도 수정 금지.**
  import 하다가 부족한 헬퍼가 있으면 fulllog 쪽에 새로 쓰지, 원본을 고치지 않는다.
- `run_fusion.py` 변경은 TARGETS 한 줄만. CLI·게이트 로직 불변.
- fps 30 고정·HD720 고정 규칙 유지(bodytrack 의 인자 기본값을 그대로 따른다).
- 좌표계·단위 문자열(`RIGHT_HANDED_Z_UP_X_FWD`, METER)을 meta 에 명시.
- 주석은 한국어. 코드 스타일은 bodytrack 과 동일한 손글씨 스타일(과도한 타입힌트·
  docstring 도배 금지, 기존 파일 밀도에 맞춤).
- `logs/**` 기존 파일 수정·삭제 금지. 새 로그 파일 생성만.
- **영상 인코딩이 30fps 루프를 깎을 수 있다** — `retrieve_image` + VideoWriter 2대분이
  grab 루프 안에 들어간다. 프레임 드랍 여부는 라이브에서 metrics 레코드의
  `received_fps` 로 판정한다. 인코딩 최적화(스레드 분리 등)는 이 plan 범위 밖 —
  느리면 worklog "해결해야 할 점"에 수치와 함께 기록하고 끝낸다.
- 영상은 LEFT 뷰만 저장한다(우안·depth 맵은 SVO2 로만). 디스크: 2×HD720@30 mp4v 는
  대략 수백 MB/10분 수준 — meta 에 파일 경로를 남겨 사용자가 정리할 수 있게 한다.
- 하드웨어(카메라/GPU)는 샌드박스에 없다 — **실행 검증은 정적 수준까지만** 하고,
  라이브 실행은 사용자 몫으로 남긴다.

## 이번에는 하지 않는 것

- ROS2 브리지(`fusion_ros2_bridge.py`) 확장·커스텀 msg·bag 기록 — 필드 확정 후 별도 plan.
- CBF/ε(t) 로의 매핑 설계, covariance 해석 — 이 plan 은 데이터 수집까지만.
- 세그멘테이션(`enable_segmentation`)·mask 기록 — 용량 대비 현재 용도 없음.
- 분석 스크립트(pandas 리포트) — 로그가 쌓인 뒤 별도 작업.
- `zed_fusion_bodytrack.py` 의 기존 JSONL 포맷 변경.

## 검증

- `python3 -m py_compile scripts/zed_fusion_fulllog.py scripts/run_fusion.py`
- `conda run -n zed python3 scripts/zed_fusion_fulllog.py --help` 가 0 으로 종료.
- `conda run -n zed python3 - <<'EOF'` 수준의 단위 검증: `_body_record` 상당 함수에
  `sl.BodyData()` 빈 인스턴스를 넣어 (1) 예외 없이 dict 반환, (2) `json.dumps(...,
  allow_nan=False)` 통과, (3) fused 레코드에 `keypoint_2d`/`mask` 키가 없는 것 확인.
- `python3 scripts/run_fusion.py fulllog --skip-calib -- --help` 가 게이트를 지나
  대상 스크립트 help 를 출력(캘리브 파일 존재 전제).
- `--help` 출력에 `--no-video`/`--record-svo`/`--metrics-every`/`--no-raw` 가 보이는지 확인.
- 라이브(사용자): `run_fusion.py fulllog --skip-calib` 로 30초 촬영 → (1) jsonl 에 fused/raw/
  metrics 세 종류 레코드가 있고 `velocity`·`keypoints_covariance` 가 non-null, (2) 카메라별
  MP4 2개가 생성되고 재생 가능, (3) raw 레코드의 `frame_idx` 로 MP4 해당 프레임을 열었을 때
  `keypoint_2d` 위치가 사람과 일치, (4) metrics 의 `received_fps` 가 ~30 유지(영상 인코딩이
  루프를 깎지 않는지) 확인.

## 다음 단계

- 라이브 로그 1~2회 수집 후: velocity 지연 실측, covariance 특성(융합 재계산 여부) 분석
  → CBF 입력 필드 확정 → 커스텀 msg + bag/브리지 확장 plan.
- 정반 고정 세션(ZED360 1회 → base 측정 1회 → 동결)과 같은 날 묶어서 촬영하면 효율적.
