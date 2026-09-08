# logs/ — fulllog 데이터 명세

ZED-M 2대를 ZED SDK **Fusion**(SDK 5.4.0)으로 융합해 뽑은 사람 포즈 로그와 카메라 영상이 저장되는
디렉터리다. 생성 스크립트는 `scripts/zed_fusion_fulllog.py`
(실행 진입점 `python3 scripts/run_fusion.py fulllog --skip-calib -- --duration N`).

> 이 디렉터리의 실측 파일은 **수정·이동·삭제하지 않는다.** 재현 비용이 크다.

---

## 1. 디렉터리 구조

촬영 1회 = 디렉터리 1개. 이름의 `<stamp>`는 실행 시작 시각 `YYYYMMDD_HHMMSS`.

```
logs/
├── fulllog_<stamp>/
│   ├── fulllog_<stamp>.jsonl              # 검출 레코드 (아래 §3)
│   ├── fulllog_<stamp>_meta.json          # 실행 조건 (§5)
│   ├── fulllog_<stamp>_cam13870389.mp4    # 카메라 1 LEFT 영상 (1280×720, 30fps)
│   └── fulllog_<stamp>_cam19321109.mp4    # 카메라 2 LEFT 영상
├── fusion_zed360.json                     # ZED360 캘리브 (카메라 간 extrinsic) — 융합의 전제
├── base_cam_extrinsics.yaml               # ArUco 측정 base↔카메라 static TF (ROS2 용, fulllog 와 무관)
└── (2026-09-04 이전 산출물은 하위 디렉터리 없이 루트에 평평하게 있음)
```

카메라 시리얼: **13870389** = zed1, **19321109** = zed2.

---

## 2. 좌표계·단위·포맷 (전 구간 공통)

| 항목 | 값 |
|---|---|
| 좌표계 | `RIGHT_HANDED_Z_UP_X_FWD` — **X=전방, Y=좌, Z=상** |
| 단위 | **미터**, 속도 m/s, 신뢰도 0~100, 각도 없음(회전은 quaternion `[x,y,z,w]`) |
| 시각 | `t_sdk_ns` = 카메라 이미지 타임스탬프(ns, 분석 기준), `t_wall_ns` = 기록 시 PC 시각(ns) |
| 융합 결과 | **`fusion_world`** 프레임, **BODY_34** |
| 카메라별 원시 검출 | **해당 카메라 프레임**, **BODY_18** |
| 결측 | `NaN`/`inf` 는 전부 **`null`** 로 저장됨 (`allow_nan=False`) |

`fusion_world` 는 ZED360 캘리브가 정의하는 공통 좌표계다. 원점은 첫 번째로 로드된 카메라 아래
(바닥 높이는 캘리브 중 발목이 보였을 때만 추정됨). 로봇 base 좌표가 필요하면
`base_cam_extrinsics.yaml` 의 `base→fusion_world` 를 곱한다(ROS2 `/tf_static` 으로 발행됨).

---

## 3. JSONL 레코드

한 줄 = JSON 객체 1개. `record` 키로 네 종류를 구분한다. 한 프레임(1/30 s)마다 보통 이 순서로 쌓인다:

```
frame    ← 매 프레임 정확히 1줄 (사람이 없어도)
fused    ← 융합된 사람 1명당 1줄
raw      ← 카메라별 검출 사람 1명당 1줄 (카메라 2대 × 사람 수 이하)
metrics  ← 30 프레임마다 1줄 (--metrics-every)
```

### 3.1 `frame` — 프레임 하트비트

```json
{"record":"frame","frame_idx":{"13870389":11,"19321109":11},
 "t_sdk_ns":1788511085635778395,"t_wall_ns":1788511085866293713,
 "n_bodies":0,"body_ids":[]}
```

| 필드 | 의미 |
|---|---|
| `frame_idx` | 카메라 시리얼 → **그 카메라 MP4 의 프레임 번호(0-based)**. 영상과의 join 키 |
| `n_bodies` | 이 프레임의 융합된 사람 수. `0` = 빈 방 |
| `body_ids` | 뒤따르는 `fused` 레코드들의 `id` 목록 |

30 Hz 연속 타임라인의 앵커다. 사람 없음 구간을 명시적으로 남기기 위해 존재한다.
융합 처리에 실패한 프레임(grab 실패 등)은 `frame_idx` 가 건너뛴다.

### 3.2 `fused` — 융합된 사람 (핵심 데이터)

`frame:"fusion_world"`, `body_format:"BODY_34"`.

| 필드 | 형태 | 의미 |
|---|---|---|
| `id` | int | Fusion 추적 ID. 같은 사람이면 프레임 간 유지. `frame.body_ids` 와 동일 |
| `unique_object_id` | str | UUID (id 재사용 대비 영구 식별자) |
| `tracking_state` | `OK` / `SEARCHING` / `OFF` / `TERMINATE` | 추적 상태 |
| `action_state` | `IDLE` / `MOVING` / `Unknown` | 동작 상태 (fused 에서는 보통 `Unknown`) |
| `confidence` | 0~100 | 검출 신뢰도 |
| `position` | [3] | 몸 중심 위치 (m) |
| `velocity` | [3] | 속도 (m/s). 칼만 기반 — 지연 보고됨 |
| `position_covariance` | [6] | 3×3 대칭 공분산의 상삼각 `[xx, xy, xz, yy, yz, zz]` |
| `dimensions` | [3] | 3D 박스 W/H/D (m) |
| `bounding_box` | [8][3] | 3D 박스 꼭짓점 |
| `keypoint` | **[34][3]** | **관절 3D 좌표**. 인덱스는 §4 의 BODY_34 표 |
| `keypoint_confidence` | [34] | 관절별 신뢰도 0~100. 가림으로 못 본 관절은 낮음 |
| `keypoints_covariance` | [18][6] | 관절 공분산 — **34 가 아니라 18 개만 옴(SDK 특성, §6)** |
| `local_position_per_joint` | [34][3] | 부모 관절 기준 상대 위치 |
| `local_orientation_per_joint` | [34][4] | 부모 관절 기준 상대 회전 quat `[x,y,z,w]` |
| `global_root_orientation` | [4] | 골반(루트) 전체 회전 quat |
| `head_position`, `head_bounding_box` | — | **fused 에서는 채워지지 않음**(`[0,0,0]`, `[]`). 머리는 `keypoint[26]`(HEAD)/`[27]`(NOSE) 사용 |
| `is_new`, `is_tracked` | bool | 컨테이너(`sl.Bodies`) 상태 |

안전 신호가 소비하는 "머리 + 양 손목" 은 `keypoint[26]`, `keypoint[7]`(LEFT_WRIST),
`keypoint[14]`(RIGHT_WRIST) 와 대응 `keypoint_confidence` 에서 뽑는다.

### 3.3 `raw` — 카메라별 원시 검출

각 카메라가 **혼자** 본 결과. `frame:"camera"`(그 카메라 좌표계), `body_format:"BODY_18"`.
`fused` 와 같은 필드 구성에 아래가 추가된다:

| 필드 | 형태 | 의미 |
|---|---|---|
| `serial_number` | int | 어느 카메라인지 |
| `frame_idx` | **int** | 그 카메라 MP4 프레임 번호 (fused 는 dict, raw 는 int) |
| `keypoint_2d` | [18][2] | **LEFT 영상 픽셀 좌표 (x, y)**. 같은 `frame_idx` 의 MP4 프레임 위에 바로 그릴 수 있다 |
| `bounding_box_2d`, `head_bounding_box_2d` | [4][2] | 픽셀 박스 |
| `head_position` | [3] | raw 에서는 채워져 있음 |

raw 는 `id:-1`, `tracking_state:"OFF"` 가 **정상**이다 — 카메라 쪽 추적을 끄고 Fusion 이 추적하는
구조라 raw 에는 ID 가 없다. 따라서 **raw ↔ fused 대응은 ID 로 못 잇고**, 같은 `frame_idx` 에서
위치(카메라 pose 로 world 변환 후)로 매칭해야 한다.
`local_position_per_joint`/`local_orientation_per_joint` 는 raw 에서 빈 배열이다.

### 3.4 `metrics` — 융합 품질 지표

| 필드 | 의미 |
|---|---|
| `mean_camera_fused` | 사람당 기여 카메라 수 평균. **2.0 이면 두 카메라 모두 융합에 기여** |
| `mean_stdev_between_camera` | 카메라 간 위치 불일치 (m). 캘리브 품질 지표 |
| `camera_individual_stats[serial]` | `received_fps`(30 근처여야 정상), `received_latency`, `synced_latency`, `delta_ts`, `is_present`, `ratio_detection` |

---

## 4. 관절 인덱스 (SDK 5.4.0 enum 에서 추출)

### BODY_34 (`fused.keypoint`)

| idx | 부위 | idx | 부위 | idx | 부위 |
|---|---|---|---|---|---|
| 0 | PELVIS | 12 | RIGHT_SHOULDER | 24 | RIGHT_ANKLE |
| 1 | NAVAL_SPINE | 13 | RIGHT_ELBOW | 25 | RIGHT_FOOT |
| 2 | CHEST_SPINE | **14** | **RIGHT_WRIST** | **26** | **HEAD** |
| 3 | NECK | 15 | RIGHT_HAND | 27 | NOSE |
| 4 | LEFT_CLAVICLE | 16 | RIGHT_HANDTIP | 28 | LEFT_EYE |
| 5 | LEFT_SHOULDER | 17 | RIGHT_THUMB | 29 | LEFT_EAR |
| 6 | LEFT_ELBOW | 18 | LEFT_HIP | 30 | RIGHT_EYE |
| **7** | **LEFT_WRIST** | 19 | LEFT_KNEE | 31 | RIGHT_EAR |
| 8 | LEFT_HAND | 20 | LEFT_ANKLE | 32 | LEFT_HEEL |
| 9 | LEFT_HANDTIP | 21 | LEFT_FOOT | 33 | RIGHT_HEEL |
| 10 | LEFT_THUMB | 22 | RIGHT_HIP | | |
| 11 | RIGHT_CLAVICLE | 23 | RIGHT_KNEE | | |

### BODY_18 (`raw.keypoint`, `raw.keypoint_2d`)

| idx | 부위 | idx | 부위 | idx | 부위 |
|---|---|---|---|---|---|
| 0 | NOSE | 6 | LEFT_ELBOW | 12 | LEFT_KNEE |
| 1 | NECK | **7** | **LEFT_WRIST** | 13 | LEFT_ANKLE |
| 2 | RIGHT_SHOULDER | 8 | RIGHT_HIP | 14 | RIGHT_EYE |
| 3 | RIGHT_ELBOW | 9 | RIGHT_KNEE | 15 | LEFT_EYE |
| **4** | **RIGHT_WRIST** | 10 | RIGHT_ANKLE | 16 | RIGHT_EAR |
| 5 | LEFT_SHOULDER | 11 | LEFT_HIP | 17 | LEFT_EAR |

**두 포맷의 인덱스는 다르다.** 섞어 쓰지 말 것 (예: 손목이 BODY_34 는 7/14, BODY_18 은 7/4).

---

## 5. `_meta.json`

실행 조건 스냅샷. 분석 시 함께 읽는다.

| 키 | 의미 |
|---|---|
| `args` | 전체 CLI 인자 (fps, depth 모드, 신뢰도 임계값, `--no-raw` 등) |
| `config` | 사용한 ZED360 캘리브 파일 절대경로 |
| `sdk_version`, `serials` | SDK 버전, 카메라 시리얼 순서 |
| `body_format` | `{"sender":"BODY_18","fused":"BODY_34"}` |
| `coordinate_system`, `unit` | §2 와 동일 |
| `run_dir`, `log_path` | 이 실행의 디렉터리·JSONL 절대경로 |
| `video_paths[]` | `{serial_number, path, codec}` — `codec` 은 `h264`(기본) 또는 `mp4v`(폴백) |
| `svo_paths[]` | `--record-svo` 를 준 경우 SVO2 경로 |

---

## 6. 알아둘 점 / 함정

- **영상 코덱**: 2026-09-04 18:30 이후 촬영분은 H.264(`libx264`, yuv420p) 로 어디서나 재생된다.
  그 이전 파일(`fulllog_20260904_170220*`, `fulllog_20260904_173800/`)은 OpenCV `mp4v`
  (MPEG-4 Part 2) 라 **VS Code 미리보기·브라우저에서 열리지 않는다.** 파일은 무결하며 VLC/ffplay 로
  재생되고, 필요하면 `ffmpeg -i IN.mp4 -fps_mode passthrough -c:v libx264 -crf 18 -pix_fmt yuv420p OUT.mp4`
  로 변환한다(프레임 수 보존). 어느 쪽인지는 `_meta.json` 의 `video_paths[].codec` 으로 확인.
- **MP4 프레임 수 ≥ frame 레코드 수**: 영상은 grab 성공 즉시 쓰지만 `frame` 레코드는 융합 처리
  성공 시에만 쓰인다. 시작 직후 몇 프레임과 융합 실패 프레임은 영상에만 있다. 항상 `frame_idx` 로
  join 하고, 영상 프레임 순번을 레코드 순번으로 가정하지 말 것.
- **`fused.keypoints_covariance` 는 18 개**(34 아님). SDK 가 돌려주는 길이 그대로다. 관절별 대응이
  필요하면 SDK 문서에서 확인한 뒤 쓰고, 그 전엔 위치 불확실성은 `position_covariance` 로 대체.
- **`fused.head_position` 은 항상 0** — `keypoint[26]`/`[27]` 을 쓴다.
- **raw 에는 사람 ID 가 없다**(§3.3).
- **캘리브 신선도**: `fusion_zed360.json` 이 촬영 당시 카메라 배치와 다르면 같은 사람이 두 스켈레톤
  (`n_bodies:2`)으로 갈라진다. `metrics.mean_camera_fused` 가 2.0 근처인지로 판별.
- **null 처리**: 신뢰도 0 인 관절은 좌표가 `null` 일 수 있다. 수치 연산 전 필터링 필요.

---

## 7. 읽기 예시

```python
import json
recs = [json.loads(l) for l in open("logs/fulllog_<stamp>/fulllog_<stamp>.jsonl")]

frames = [r for r in recs if r["record"] == "frame"]          # 30 Hz 타임라인
fused  = [r for r in recs if r["record"] == "fused"]

# 사람 id 0 의 오른손목(BODY_34 idx 14) 궤적: (t, xyz, conf)
rw = [(r["t_sdk_ns"], r["keypoint"][14], r["keypoint_confidence"][14])
      for r in fused if r["id"] == 0 and r["keypoint"][14] is not None]

# raw 2D 관절을 영상 위에 그리기: 같은 카메라 MP4 의 frame_idx 번째 프레임에 keypoint_2d 를 겹친다
raw_cam1 = [r for r in recs if r["record"] == "raw" and r["serial_number"] == 13870389]
# cv2.VideoCapture(mp4).set(cv2.CAP_PROP_POS_FRAMES, r["frame_idx"]) → read() → r["keypoint_2d"]
```

사람이 없는 구간의 NaN 채움은 더미 바디를 만들지 않고, 분석 시 `frame` 레코드와 **outer join**
으로 얻는다(설계 결정).

---

## 8. 재현

```bash
conda activate zed && cd ~/cbf_ws
python3 scripts/run_fusion.py fulllog --skip-calib -- --duration 60      # 캘리브 재사용
python3 scripts/run_fusion.py fulllog -- --duration 60                   # ZED360 캘리브부터
```

옵션: `--duration 0`(Ctrl-C 까지), `--no-raw`, `--no-video`, `--video-mp4v`(H.264 대신 cv2 mp4v),
`--record-svo DIR`(SVO2 원본 녹화), `--metrics-every N`. 전체 목록은
`conda run -n zed python3 scripts/zed_fusion_fulllog.py --help`.
