---
date: 2026-07-16
task: 두 대의 ZED-M(사람 좌/우)을 Fusion으로 융합해 가림에 강한 단일 스켈레톤 산출
planner: Claude Code (user-directed)
executor: Claude Code
status: done
---

# PLAN01 — ZED-M 2대 상호보완(Fusion) Body Tracking

## 한 줄 결론
사람의 **좌/우에 놓인 ZED-M 2대**를 SDK **Fusion 모듈**로 묶어, 한쪽 카메라에서 가려진 관절(예: 지금 오른손목 conf 0)을 반대쪽이 메워주는 **가림-강건 단일 스켈레톤 + 관절별 신뢰도 로그**를 만든다. USB 대역 제약 때문에 **두 대 모두 HD720@30**으로 돌린다. 정확한 융합에는 **ZED360 캘리브레이션(카메라 간 상대 위치)** 이 선행돼야 한다.

## 왜 이 plan이 필요한가
단일 ZED-M 스트림 A는 동작하지만(34관절+conf+ts @30 로그 검증됨), **앉은/가림 상황에서 반대쪽 관절이 통째로 소실**된다. 실측에서 오른손목 conf median 0. barrier가 소비하는 게 **머리+양 손목**이라, 한 손목이라도 소실되면 안전 신호가 비는 셈. 카메라를 좌/우로 두고 융합하면 서로의 사각을 덮는다.

## 지금까지 이어진 맥락 (이미 확정된 사실)
- **SDK 5.4.0 설치 완료**, pyzed는 conda `zed` env에 격리됨.
- **ZED-M 2대**: S/N **13870389**, **19321109**. 각 단독 HD720@60 = ~61fps 정상.
- **동시 스트리밍 제약**: 단일 USB 컨트롤러 공유로 **2×HD720@60 불가(5.7/21.7fps 붕괴)**, **2×HD720@30 정상(30/30)**. → Fusion은 **@30 고정**. (하드웨어로 USB 라인/컨트롤러 분리하면 @60 재검 가능 — worklog "해결해야 할 점".)
- 단일 카메라 파이프라인/시각화 코드 존재: `scripts/zed_bodytrack_min.py`(로그), `scripts/zed_bodytrack_viz.py`(오버레이), `scripts/zed_check.py`.
- 관절 인덱스(BODY_34): HEAD=26, LEFT_WRIST=7, RIGHT_WRIST=14. 신뢰도 임계 40에서 시작(문서의 52는 ZED-2i 논문값이라 폐기).
- **코드 현황(중요)**: `scripts/zed_fusion_bodytrack.py`는 **작성돼 있으나 하드웨어 미검증** — SDK 5.4 Fusion API 호출부에 `# VERIFY` 다수. `scripts/zed_make_fusion_config.py`(수동 config 생성기)는 **아직 미작성**.
- **실측 공백(중요)**: `logs/`·`.jsonl`·`.svo2`가 전무 = **단일캠 Stage A 실측 로그 0건**. → Fusion이 "가림을 메웠다"를 증명할 **비교 baseline이 아직 없음**. 이 선행조건을 아래 실행 순서 P1에서 먼저 해소한다.

## 지금 기준 판단
- **아키텍처**: 공식 multi-camera 샘플 구조를 따른다 — 한 프로세스 안에서 **카메라마다 sender(각자 body tracking publish)** + **Fusion 객체가 두 sender를 subscribe**해 융합 스켈레톤을 retrieve. (정확한 API는 researcher 검증 후 확정 — 아래 "참고".)
- **배치**: 사람 기준 **좌/우**. 두 시점이 서로 반대쪽을 봐서 가림 상보성이 최대. 각 카메라는 문서 §0 배치(1.2–2.0m, 하향 20–25°)를 좌/우로 대칭 적용.
- **캘리브레이션**: 두 카메라의 상대 위치(월드 프레임)가 있어야 융합이 의미 있다. **주 경로 = ZED360**(`/usr/local/zed/tools/ZED360`)로 fusion config JSON 생성. **부트스트랩 경로 = 수동 pose**(좌/우 카메라의 대략 위치를 손으로 넣은 config)로 파이프라인 먼저 돌려보기.
- **좌표계/단위**: METER, 융합 결과는 **fusion 월드 프레임**(캘리브레이션이 정의). robot base 변환(hand-eye)은 이 plan 범위 밖.
- **프레임레이트**: 2×HD720@30 고정.

## 이번에 할 것
1. Fusion sender(×2) + Fusion subscriber를 한 프로세스에서 돌려 **융합 스켈레톤**을 얻는다.
2. 융합 결과를 **JSONL 로그**(kp+per-joint conf+timestamp, 단일캠과 동일 스키마 + `n_cameras_seen` 등 융합 메타)로 축적.
3. **오버레이/뷰** 로 사람이 확인 가능하게(한 카메라 이미지에 융합 스켈레톤 투영, 또는 top-down 뷰).
4. **수동 config 생성기**로 캘리브레이션 없이도 파이프라인이 도는지 먼저 검증 → 이후 ZED360 config로 교체.

## 구현해야 할 것 (파일 단위)
- `scripts/zed_fusion_bodytrack.py` — 메인. 입력: fusion config(JSON) 경로, fps(기본 30), conf, duration, outdir, 옵션 overlay/record.
  - 각 카메라 open(HD720@30, NEURAL, set_as_static) → enable_positional_tracking → enable_body_tracking → **publish 시작**.
  - `sl.Fusion` init → 각 카메라 **subscribe(serial, comm, pose)** → **enable_body_tracking(fusion)**.
  - 루프: 각 카메라 `grab()` → `fusion.process()` → `fusion.retrieve_bodies(fused, runtime)` → JSONL 기록 + (옵션)오버레이 프레임.
  - 융합 런타임 파라미터로 가림-강건성 조절(최소 관절수/최소 카메라수 등 — API 확정 후).
- `scripts/zed_make_fusion_config.py` — 수동/측정 pose로 fusion config JSON을 생성(부트스트랩용). 좌/우 카메라의 translation·rotation을 인자로 받아 SDK가 읽는 포맷으로 저장. (ZED360 결과 JSON과 호환되게.)
- (선택) `scripts/zed_fusion_viz.py` — 융합 스켈레톤 오버레이 전용(메인에 --overlay로 통합 가능).

## 참고해야 할 것 (왜 보는지 함께)
- **researcher 결과(진행 중)**: SDK 5.4 Python Fusion 정확한 호출 순서 — `camera.start_publishing`, `sl.Fusion`, `sl.InitFusionParameters`, `fusion.subscribe(sl.CameraIdentifier, CommunicationParameters, pose)`, `sl.read_fusion_configuration_file`, `sl.BodyTrackingFusionParameters`, `fusion.retrieve_bodies(bodies, sl.BodyTrackingFusionRuntimeParameters)`, 공식 `body tracking/multi-camera/python` 샘플 구조. **코드는 이 결과 확정 후 작성**(추측 금지).
- **ZED360 툴**: `/usr/local/zed/tools/ZED360` — 두 카메라 상대 위치 캘리브레이션 → fusion config JSON.
- **worklog 2026-07-16 "해결해야 할 점"**: 2×60 대역 제약. Fusion은 @30 유지 근거.
- **기존 `scripts/zed_bodytrack_min.py`**: BODY_34/fitting/ACCURATE/조인트 인덱스/로그 스키마 재사용.
- **`ZEDM_포즈추출_초기셋업.md` §6.6**: Fusion 확장이 원래 로드맵에 있었음.

## 신경써야 할 것 (가드레일)
- **@30 고정**: 2×HD720@60은 이 하드웨어에서 붕괴. 코드 기본 fps=30, 60은 하드웨어 개선 후.
- **캘리브레이션 없으면 융합 무의미**: config(ZED360 or 수동) 없이는 두 스켈레톤이 정합 안 됨. 수동 config는 어디까지나 파이프라인 점검용이라고 로그/문서에 명시.
- **좌표 프레임**: 융합 결과는 fusion 월드 프레임. 단일캠 로그와 프레임이 다름 → 로그에 `frame: "fusion_world"` 태그.
- **기존 단일캠 스크립트 훼손 금지**: 새 파일로만 추가.
- **동시 개방 안정성**: 2대 동시 open 시 첫 열거가 깜빡인 이력 있음(재시도/대기 처리).
- **camera 점유**: ZED Studio 등 다른 앱이 카메라 물면 실패 → 실행 전 종료.

## 이번에는 하지 않는 것 (non-scope)
- robot base 변환(hand-eye, `T_base_cam`) / ROS2 노드화.
- D435 감시 스트림, τ 산정.
- 2×HD720@60 (USB 하드웨어 개선 후 별도).
- ε(t) 모델링.

## 검증
- 수동 config로 파이프라인 기동 → `fusion.retrieve_bodies`가 융합 바디 반환, @30 유지 확인.
- **가림 상보성 실증**: 한쪽 팔을 한 카메라에서 가렸을 때, 단일캠에선 conf 0이던 관절이 융합에선 유지되는지 로그로 비교(단일캠 로그 vs 융합 로그의 손목 conf 분포).
- 오버레이 영상으로 사람이 확인.
- ZED360 config로 교체 후 정합 개선 확인.

## 다음 단계
- ZED360 캘리브레이션 실제 수행 → config 교체.
- 가림 상보성 정량화(좌/우 각각 가림 시 관절 유지율).
- 이후: fusion 월드 → robot base(hand-eye) → ε(t) → CBF 층 연결.
