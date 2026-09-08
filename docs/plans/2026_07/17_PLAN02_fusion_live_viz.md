---
date: 2026-07-17
task: 2대 ZED-M Fusion 결과를 모니터에서 실시간으로 보는 라이브 뷰어(카메라 오버레이 + top-down)
planner: Codex (초안 Claude Code, 사용자 지시)
executor: Codex (사용자 지시 예외 — 저장소 기본 역할은 Claude Code)
status: done
---

# PLAN02 — Dual ZED-M Fusion 라이브 뷰어 (`zed_fusion_viz.py`)

> 파일: `docs/plans/2026_07/17_PLAN02_fusion_live_viz.md` (식별자 = PLAN02, 사용자 표기와 일치).

## 역할 예외 (사용자 지시)
이 plan 한정으로 역할이 저장소 기본과 다르다. 사용자 명시 지시:
**초안은 Claude Code 가 작성 → Codex 가 검토·승인·구현(owner/executor)**.
저장소 기본 규칙(Codex plan owner / Claude Code executor)의 **사용자 승인 예외**이며,
검토자는 이 역할 배치를 반려 사유로 삼지 않는다(기술 타당성만 판단).

## 한 줄 결론
`scripts/zed_fusion_viz.py` 를 새로 만들어, 이미 동작하는 2대 Fusion 파이프라인을
**모니터에서 실시간(cv2 창)** 으로 보게 한다. 창은 **두 개**:
(1) 좌/우 카메라 실제 영상에 **각 카메라의 raw 2D 스켈레톤**을 그린 오버레이(좌|우 나란히),
(2) **융합된 world-frame 스켈레톤을 top-down** 으로 그린 뷰. 둘 다 신뢰도 색상(빨강→초록).

## 왜 이 plan이 필요한가
PLAN01(`16_PLAN01_zed_fusion_dual.md`)로 2대 open→publish→Fusion subscribe→
융합 스켈레톤 retrieve 파이프라인이 완성됐고 하드웨어에서 2×HD720@30 ~28fps 로 실동작을
확인했다(`config cameras: [13870389, 19321109]`, sender×2 publishing, subscribed×2). 다만
현재 산출물은 JSONL 로그와 **사후 저장 top-down MP4** 뿐이라, 사용자가 **지금 서서
움직이며 포즈가 어떻게 잡히는지** 실시간으로 볼 방법이 없다. 이 뷰어가 그 공백을 채운다.

## 지금까지 이어진 맥락 (이미 확정된 사실)
- SDK 5.4.0 / pyzed 설치 완료, conda `zed` env. ZED-M 2대 S/N **13870389**(좌), **19321109**(우).
- 2×HD720@60 은 이 USB 리그에서 붕괴 → **@30 고정**. 코드 기본 fps=30, 60 은 거부.
- 좌표계: `RIGHT_HANDED_Z_UP_X_FWD`, 단위 METER. 융합 결과 keypoint 는 **fusion world frame**.
- sender(각 카메라)는 **BODY_18** 로 검출·publish, Fusion 이 fitting 하여 **BODY_34** 융합 스켈레톤 산출.
- 관절 인덱스(BODY_34): HEAD=26, LEFT_WRIST=7, RIGHT_WRIST=14. 신뢰도 임계 기본 40.
- 부트스트랩 config: `logs/fusion_manual.json`(`scripts/zed_make_fusion_config.py` 생성).
  정량 융합은 ZED360 config 로 교체해야 함(별도).
- 기존 코드:
  - `scripts/zed_fusion_bodytrack.py` — sender open/publish, Fusion subscribe/retrieve, top-down MP4,
    JSONL 로깅. `_open_sender`, `_init_fusion`, `_draw_topdown`, `BONES_34`, `_tolist`, `_ok_keypoint`,
    `_joint_indices` 등 재사용 가능한 헬퍼가 이미 있음(모듈은 `__main__` 가드라 import 부작용 없음).
  - `scripts/zed_bodytrack_viz.py` — **2D 오버레이 레퍼런스**: `zed.retrieve_image(mat, sl.VIEW.LEFT)`
    → `mat.get_data()` → `b.keypoint_2d` 로 픽셀 좌표 → `BONES` 로 선/점 → `cc(conf)` 빨강→초록,
    `cv2.imshow` + `cv2.waitKey`. (단, 이 파일은 BODY_34 기준이므로 bones 를 그대로 쓰면 안 됨 — 아래 참고.)

## 지금 기준 판단
- **한 프로세스**에서 sender×2 를 열고(이미지 retrieve 포함) + Fusion 을 돌려, 매 프레임
  **각 카메라 raw 2D 스켈레톤**과 **융합 top-down** 을 동시에 그린다.
- **뷰는 창 2개**: `"cameras (raw 2D)"`(좌|우 hconcat), `"fusion top-down (world)"`.
- **오버레이는 BODY_18** 기준(sender 포맷과 일치). top-down 은 BODY_34(융합 포맷) 기준.
- 기존 파일 **런타임 동작은 건드리지 않는다**. 헬퍼는 `zed_fusion_bodytrack.py` 에서 import 하거나
  최소 복제. (import 를 쓰면 그 파일의 CLI/동작을 바꾸지 말 것.)

## 이번에 할 것
1. `scripts/zed_fusion_viz.py` 신규 작성 — 위 두 창을 실시간으로 띄우는 라이브 뷰어.
2. 헤드리스(디스플레이 없음) 대비 `--save` 로 합성 화면을 MP4 로도 저장(선택 실행).

## 구현해야 할 것 (파일 단위)
- **신규** `scripts/zed_fusion_viz.py`
  - 입력: `--config <fusion config json>`(필수, `sl.read_fusion_configuration_file` 로 로드,
    카메라 <2 면 거부). 기타: `--res HD720`, `--fps 30`(기본; 30 아니면 `sys.exit(2)`),
    `--depth NEURAL`, `--conf 40`, `--min-keypoints 7`, `--min-cameras 1`, `--smoothing 0.1`,
    `--topdown-size 900`, `--topdown-scale 180`, `--duration 0`(0=창 닫을 때까지),
    `--save`(합성 프레임 MP4 기록), `--outdir logs`, `--retry-count 3`, `--retry-wait 1`.
  - sender open: `zed_fusion_bodytrack.py` 의 `_open_sender` 와 **동일 파라미터**(HD720@30, NEURAL,
    positional tracking static, BODY_18, ACCURATE, start_publishing). viz 는 여기에 더해 매 프레임
    `zed.retrieve_image(mat, sl.VIEW.LEFT)` 로 좌안 RGB 를 받아 오버레이 배경으로 쓴다.
  - Fusion: `_init_fusion` 과 동일하게 subscribe(각 카메라 pose/override_gravity) + enable_body_tracking,
    2대 미만 subscribe 시 거부. runtime = `BodyTrackingFusionRuntimeParameters`
    (min keypoints/cameras/smoothing).
  - 루프(프레임마다):
    1. 각 sender: `grab()` → `retrieve_image(LEFT)` → `retrieve_bodies(raw_i)`(BODY_18).
    2. `fusion.process()` → `fusion.retrieve_bodies(fused, runtime, CameraIdentifier(), WORLD)`(BODY_34).
    3. **카메라 창**: 각 카메라 이미지(BGR로 변환)에 raw 2D 스켈레톤을 `keypoint_2d`+**BODY_18 bones**로
       그림(선/점 `cc(conf)`). 좌상단에 `S/N, bodies=n`. 좌·우 이미지를 같은 높이로 resize 후
       `cv2.hconcat` → `imshow("cameras (raw 2D)")`.
    4. **top-down 창**: `_draw_topdown` 재사용(또는 동등 구현)으로 융합 BODY_34 스켈레톤을 world x/y
       투영해 그림 + raw world 포인트(옅게) → `imshow("fusion top-down (world)")`.
    5. 디스플레이가 있으면 `imshow` 두 창 + `key = cv2.waitKey(1) & 0xFF`; `q`(113)/ESC(27) 종료.
       HUD 에 fps/융합 body 수 표시.
    6. **합성 프레임(고정 레이아웃)**: 카메라 패널(좌|우 각 640×360 resize → hconcat = 1280×360) 위에
       top-down 패널(`--topdown-size` 정사각 → 폭 1280 로 resize) 을 `vconcat`. 이 **단일 합성 프레임**을
       `--save` 시 `logs/fusion_viz_<ts>.mp4`(mp4v, fps=30) 로 기록. 출력 크기는 매 프레임 동일(고정).
  - **headless 모드**: 환경변수 `DISPLAY` 가 없으면(또는 `imshow` 가 실패하면) 자동으로 창을 열지 않고
    `--save` 를 강제(사용자에게 안내 print). `--save` 없이 headless 이면 "디스플레이 없음 → --save 필요"
    안내 후 `sys.exit(2)`. 디스플레이가 있으면 `--save` 는 순수 추가 기록(창은 그대로 뜸).
  - BODY_18 bones: SDK 상수 `sl.BODY_18_BONES` 가 있으면 그걸로 인덱스쌍을 만들고, 없으면
    18관절 표준 연결(nose-neck, neck-shoulders-elbows-wrists, neck-hips-knees-ankles, nose-eyes-ears)을
    하드코딩. **BODY_34 의 `BONES_34` 를 카메라 오버레이에 쓰지 말 것**(인덱스 불일치).
  - 종료 시 `finally` 로 writer release, `fusion.close()`, 각 sender `disable_body_tracking()`+`close()`,
    `cv2.destroyAllWindows()`.

## 참고해야 할 것 (왜 보는지 함께)
- `scripts/zed_fusion_bodytrack.py` — sender/fusion open·subscribe·retrieve 순서, `_draw_topdown`,
  `BONES_34`, `_ok_keypoint`, `_tolist`, `_camera_identifier`, `_status_failed`, 헬퍼 시그니처 그대로
  재사용(중복 방지). world→화면 투영(`project`)도 여기 있음.
- `scripts/zed_bodytrack_viz.py` — `retrieve_image`→`get_data()`→`keypoint_2d`→BONES→`cc()`→`imshow`
  패턴과 `ok2d()` 필터. 단 BODY_34 bones 라서 **오버레이 bones 는 BODY_18 로 새로 정의**.
- `logs/fusion_manual.json` — 실행 입력 config(좌/우 serial·pose). 기본 실행에 사용.
- pyzed 이미지 채널: `zed_bodytrack_viz.py` 와 **동일하게** `mat.get_data()[:, :, :3].copy()  # BGRA -> BGR`
  로 상위 3채널을 취해 바로 cv2 에 그린다. `cvtColor` 불필요(이미 BGR 순서).

## 신경써야 할 것 (가드레일)
- **기존 파일 런타임 동작 변경 금지**: `zed_fusion_bodytrack.py`/`zed_make_fusion_config.py` 의 CLI·동작을
  바꾸지 말 것. 헬퍼는 import 재사용(모듈은 `__main__` 가드) 또는 최소 복제. **새 파일만 추가**.
- **@30 고정**: `--fps` 30 아니면 거부(2×HD720@60 붕괴).
- **좌표/포맷 구분**: 카메라 오버레이 = 픽셀 2D(BODY_18), top-down = fusion world x/y(BODY_34).
  섞지 말고 창 제목/HUD 에 명시.
- **샌드박스에 카메라·GPU 없음**: Codex 는 라이브 실행 불가(`CAMERA NOT DETECTED`/`cudaErrorNoDevice`).
  검증은 `py_compile` + `--help` + 정적 리뷰까지. **라이브 확인은 사용자가 `zed` env 에서** 수행.
- **디스플레이 의존**: `imshow` 는 디스플레이 필요. `DISPLAY` 없으면 위 headless 규칙대로 `--save` 강제.
  (Codex 샌드박스에는 디스플레이도 카메라도 없으므로 라이브/저장 실행 자체가 불가 — 정적 검증만.)
- 사람이 프레임에 있다고 가정(사용자 확인). 검출 0 이어도 창은 떠야 하고 raw/융합 모두 안전 처리.
- BODY_18 관절 없음/`nan`/화면 밖 좌표는 `ok2d()`/`_ok_keypoint()` 로 건너뜀(그리기 예외 금지).

## 이번에는 하지 않는 것 (non-scope)
- ZED360 캘리브레이션 자체, robot base(hand-eye) 변환, ROS2 노드화.
- 2×HD720@60, ε(t)/CBF 층.
- JSONL 로그 스키마 변경(뷰어는 view 전용; 로깅은 기존 `zed_fusion_bodytrack.py` 담당).

## 근거
- PLAN01 실행 로그에서 2대 융합 파이프라인 실동작 확인(2×HD720@30 ~28fps, subscribed×2).
- 오버레이/뷰는 PLAN01 execution step 3 및 선택 산출물 `zed_fusion_viz.py` 로 이미 로드맵에 있었음.

## 검증
- `python3 -m py_compile scripts/zed_fusion_viz.py` 통과.
- `python3 scripts/zed_fusion_viz.py --help` 통과, `--fps 60` 거부 확인.
- (사용자, `zed` env, 부스에 사람) `python3 scripts/zed_fusion_viz.py --config logs/fusion_manual.json`
  → 창 2개가 뜨고, 좌/우 카메라 영상에 raw 2D 스켈레톤이, top-down 창에 융합 스켈레톤이 실시간으로
  그려지며 `q`/ESC 로 종료되는지 확인. 필요시 `--save` 로 MP4 저장.

## 다음 단계
- ZED360 캘리브레이션으로 `logs/fusion_manual.json` 교체 → top-down 정합 개선 확인.
- 좌/우 각각 팔 가림 시 융합이 관절을 유지하는지 뷰어로 육안 + 로그로 정량 비교.

## 개정 이력 (2026-07-17, rev1)
1차 Codex 검토(needs_codex_revision)의 5개 지적을 다음과 같이 반영:
- **역할 충돌** → front matter 를 `planner: Codex(초안 Claude, 사용자 지시)` / `executor: Codex`
  로 정리하고 "역할 예외(사용자 지시)" 섹션을 추가. 사용자 승인 예외임을 명시.
- **식별자 불일치** → 파일명을 `17_PLAN02_fusion_live_viz.md` 로 변경(본문 PLAN02 와 일치).
- **`--save`/headless 미명확** → 합성 프레임 고정 레이아웃(1280×360 카메라 + top-down vconcat),
  `DISPLAY` 없을 때 `--save` 강제, `--save` 없이 headless 이면 exit(2) 규칙을 "구현해야 할 것"에 명시.
- **이미지 채널** → `mat.get_data()[:, :, :3].copy()  # BGRA->BGR`(기존 `zed_bodytrack_viz.py` 패턴)로 확정.
- (참고) `docs/overview.md` 는 저장소에 아직 없음 — 이 plan 이해에 필요 없음(무시 가능).
