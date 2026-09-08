# ZED M 기반 Human Pose 추출 — 초기 연결·셋업 인수인계 문서

> **목적**: 다른 세션(또는 다른 작업자)이 이 문서만 보고 ZED M 카메라를 연결하고, Body Tracking으로 3D Human Pose를 추출하는 최소 파이프라인을 재현할 수 있게 한다.
> **상위 맥락**: HRC 안전 연구용 perception-to-barrier 어댑터의 **주 스트림(스트림 A)** 구축 1단계. barrier(CBF)가 소비할 관절 좌표 + 관절별 신뢰도를 로봇 베이스 좌표계로 내보내는 것이 최종 목표이며, 본 문서는 그 전 단계인 "카메라 단독으로 포즈가 안정적으로 나오는 상태"까지를 다룬다.
> 작성 기준일: 2026-07-16

---

## 0. 이 대화에서 확정된 결정사항 요약 (변경 금지 / 출발점 구분)

| 항목 | 값 | 상태 |
|---|---|---|
| 카메라 역할 | ZED M = 주 스트림 (SDK Body Tracking) / D435 = 감시 스트림 (RTMPose+depth, 별도 문서) | 확정 |
| Body Tracking 지원 여부 | ZED M **공식 지원** (IMU 탑재 카메라 요건 충족 — Stereolabs Body Tracking 문서에서 확인) | 확인됨 |
| 해상도/주기 | HD720 @ 60 FPS | 확정 (Maithani 실증 구성 계승) |
| Depth 모드 | NEURAL | 확정 |
| 골격 포맷 | BODY_34 (body fitting 필수) | 확정 |
| 검출 모델 | HUMAN_BODY_ACCURATE | 확정 |
| Segmentation | 비활성 (연산 절감) | 확정 |
| 검출 신뢰도 임계 | 52 | **출발점일 뿐** — ZED 2i 유래 값. ZED M에서 재도출 대상 |
| 작동 거리 (카메라↔사람) | **1.2–2.0 m** | 확정 — ZED M 베이스라인 63 mm(ZED 2i의 절반) 때문에 z-오차 ∝ 거리²/베이스라인으로 악화, 거리 단축으로 상쇄 |
| 배치 | 인간–로봇 축 기준 ±45°, 사람에서 1.5–1.8 m, 높이 ~1.8–2.0 m, 하향 20–25° | 설계 목표 (±10–15°, ±0.2–0.3 m 허용오차) |
| FOV 참고 | 약 90°(H) × 60°(V) — ZED 2i(~120°)보다 좁음. 수직 시야에 "머리~테이블 위 손" 포함되게 조준 | 확인 필요(실측) |
| barrier가 소비할 관절 | 머리, 좌/우 손목(+손) — 34관절 전부가 아님 | 확정 (Maithani 선례) |
| 카메라 강체성 | 캘리브레이션↔사용 사이 고정. 세션마다 재캘 아님 — 검증(T2/T4)으로 대체 | 확정 (별도 T0–T5 프로토콜 문서 참조) |

**핵심 철학 리마인더**: 이 연구의 안전 주장은 "포즈가 정확하다"가 아니라 "오차를 측정→ε(t)로 흡수→런타임 감시→인증 불가 시 강등"이다. 따라서 이 단계의 산출물은 예쁜 스켈레톤 화면이 아니라 **관절 좌표 + 관절별 신뢰도 + 캡처 타임스탬프의 로그**다.

---

## 1. 전제조건 (하드웨어/소프트웨어)

- [ ] **NVIDIA GPU** 필수 (ZED SDK는 CUDA 의존). RTX 4060 Ti급이면 HD720@60 Body Tracking 여유 (Maithani 실증).
- [ ] NVIDIA 드라이버 + SDK가 요구하는 CUDA 버전 (SDK 설치기가 안내 — 설치 시점 최신 조합 확인)
- [ ] OS: Ubuntu 22.04 권장 (이후 ROS 2 Humble 연동 계획과 정합)
- [ ] **USB 3.0 포트에 직결** — 허브 금지, 메인보드 루트포트 사용, 케이블 ≤ 5 m (초과 시 액티브 리피터)
- [ ] ZED M 본체 + USB-C 케이블 (정품/고품질 — 케이블 불량이 초기 트러블 1순위)
- [ ] 인터넷 연결 (첫 실행 시 AI 모델 다운로드·TensorRT 최적화 필요)

---

## 2. ZED M 초기 연결 절차 (체크리스트)

1. [ ] **SDK 설치**: stereolabs.com → Developers → SDK 다운로드 (Ubuntu용 `.run` 설치기). 기본 경로 `/usr/local/zed`. 설치 중 CUDA/의존성 안내를 따른다.
2. [ ] **물리 연결**: ZED M을 USB 3.0 루트포트에 직결. `lsusb`로 장치 인식 확인 (Stereolabs 벤더로 표시).
3. [ ] **진단 실행**: `/usr/local/zed/tools/ZED_Diagnostic` 실행 → USB 대역·GPU/CUDA·드라이버·펌웨어 전 항목 통과 확인. **펌웨어 업데이트 프롬프트가 뜨면 지금 수행**.
4. [ ] **AI 모델 사전 최적화**: ZED_Diagnostic의 AI 모듈 탭(또는 첫 Body Tracking 실행)에서 모델 다운로드+최적화. 첫 최적화는 GPU에 따라 수 분 소요 — 실험 당일이 아니라 지금 해 둘 것.
5. [ ] **영상 확인**: `ZED_Explorer` 실행 → HD720/60fps 설정 → 좌/우 영상 정상, 실측 fps ≥ 58 확인.
6. [ ] **Depth 확인**: `ZED_Depth_Viewer` → depth 모드 NEURAL → 1.2–2.0 m 대상(사람/의자)의 depth가 안정적으로 나오는지 확인.
7. [ ] **워밍업 규칙 기록**: 전원 인가 후 10–15분 열 안정화 뒤에만 캘리브레이션/실험 (열로 인한 미세 광학 변형 방지).

> 트러블 시 §7 빠른표 참조.

---

## 3. Python API (pyzed) 설치

```bash
# SDK 설치 후 제공되는 스크립트가 현재 SDK/CUDA/파이썬 조합에 맞는 휠을 받아 설치한다
python3 /usr/local/zed/get_python_api.py
python3 -c "import pyzed.sl as sl; print(sl.Camera().get_sdk_version() if hasattr(sl.Camera(),'get_sdk_version') else 'pyzed OK')"
```

- 공식 샘플 저장소: `github.com/stereolabs/zed-sdk` (body tracking 예제 폴더 존재 — 아래 최소 코드와 대조 검증할 것)
- 가상환경 사용 시 해당 환경 활성화 후 스크립트 실행.

---

## 4. Body Tracking 최소 동작 코드 (스트림 A 프로토타입)

> **주의**: SDK 4.x 기준의 골격 코드다. enum/필드명은 마이너 버전에 따라 다를 수 있으므로 **실행 전 공식 샘플과 대조**한다. `# VERIFY` 주석은 반드시 확인.

```python
import pyzed.sl as sl

zed = sl.Camera()

# ---- 초기화 (0절 확정값) ----
init = sl.InitParameters()
init.camera_resolution = sl.RESOLUTION.HD720
init.camera_fps = 60
init.depth_mode = sl.DEPTH_MODE.NEURAL
init.coordinate_units = sl.UNIT.METER
init.coordinate_system = sl.COORDINATE_SYSTEM.RIGHT_HANDED_Z_UP_X_FWD  # ROS 정합  # VERIFY
err = zed.open(init)
assert err == sl.ERROR_CODE.SUCCESS, f"open 실패: {err}"

# ---- 정적 카메라 선언 (고정 마운트이므로 필수) ----
pt = sl.PositionalTrackingParameters()
pt.set_as_static = True                      # VERIFY: SDK 4.x 필드명
zed.enable_positional_tracking(pt)

# ---- Body Tracking (0절 확정값) ----
bt = sl.BodyTrackingParameters()
bt.detection_model = sl.BODY_TRACKING_MODEL.HUMAN_BODY_ACCURATE
bt.body_format = sl.BODY_FORMAT.BODY_34     # BODY_34는 fitting 전제
bt.enable_tracking = True
bt.enable_body_fitting = True
bt.enable_segmentation = False
zed.enable_body_tracking(bt)

rt = sl.BodyTrackingRuntimeParameters()
rt.detection_confidence_threshold = 52       # 출발점 — ZED M 재도출 대상

# ---- (선택·권장) SVO 녹화: 오프라인 재처리·설정 스윕용 ----
rec = sl.RecordingParameters("session_001.svo2", sl.SVO_COMPRESSION_MODE.H264)
zed.enable_recording(rec)

# ---- barrier 소비 관절 (BODY_34 인덱스) ----
# VERIFY: 인덱스는 sl.BODY_34_PARTS enum을 출력해 확정할 것. 아래는 자리표시자.
JOINTS = {"HEAD": None, "L_WRIST": None, "R_WRIST": None}
# 예: for p in sl.BODY_34_PARTS: print(p, p.value)

bodies = sl.Bodies()
runtime = sl.RuntimeParameters()

try:
    while True:
        if zed.grab(runtime) != sl.ERROR_CODE.SUCCESS:
            continue
        zed.retrieve_bodies(bodies, rt)
        t_img_ns = zed.get_timestamp(sl.TIME_REFERENCE.IMAGE).get_nanoseconds()  # 캡처 시각(도착 시각 아님)
        for b in bodies.body_list:
            kp   = b.keypoint              # (34,3) [m] — 카메라 좌표계 (base 변환은 캘리브레이션 후)
            conf = b.keypoint_confidence   # (34,)  — ε(t)의 1차 재료. 반드시 로그.
            state = b.tracking_state
            # TODO(후속): T_base_cam 적용 → 관절 선택 → ROS 2 토픽 발행
            # TODO(로그): t_img_ns, id, kp, conf, state 를 파일로 축적 (기준선 분포용)
finally:
    zed.disable_recording()
    zed.close()
```

**이 단계의 산출물 정의(Definition of Done)**
- [ ] 1인 대상 60 Hz 근접(실측 ≥ 55 Hz)으로 34관절 + 신뢰도 스트림이 로그로 쌓인다
- [ ] 캡처 타임스탬프가 함께 기록된다
- [ ] 같은 세션의 SVO 파일이 저장된다 (오프라인 재처리 검증: SVO 재생 입력으로 동일 코드 실행 가능)
- [ ] 신뢰도 분포(관절별 히스토그램) 1차 스냅샷 저장 → 임계 52의 적정성 판단 기초자료

---

## 5. 첫 연결 합격 기준 (자체 검수)

| 검사 | 합격선 |
|---|---|
| ZED_Diagnostic | 전 항목 green (펌웨어 최신) |
| 실측 프레임레이트 | HD720에서 ≥ 58 fps (Explorer), Body Tracking 포함 ≥ 55 fps |
| Depth 안정성 | 1.2–2.0 m 정지 대상의 depth 표준편차가 수 mm~1 cm 수준 |
| 검출 안정성 | 작업 자세(서서 테이블 앞)에서 사람 검출 끊김 없음, tracking id 유지 |
| 첫 실행 지연 | AI 최적화가 사전 완료되어 실행 즉시 검출 시작 |

---

## 6. ZED M 특유 제약 — 후속 작업자가 반드시 알아야 할 것

1. **베이스라인 63 mm** → z-오차가 ZED 2i 대비 동거리 약 2배. 그래서 작동 거리 1.2–2.0 m 제약이 존재한다. 이 거리 밖(접근 존 바깥)은 ODD 밖 = 추적 미보장으로 설계상 선언되어 있음.
2. **오차 프로파일이 안전 요구와 정렬**: 가까울수록 정확 = 가까울수록 정밀 필요. ZED M의 약점이 barrier 관점에선 흡수 가능(원거리 ε 확대).
3. **신뢰도 임계 52는 남의 값**: Maithani(ZED 2i) 유래. ZED M에서는 4절의 신뢰도 분포 스냅샷과 파일럿(아래 §8)으로 재도출한다.
4. **Body Tracking은 depth를 상속**: 공식 문서 기준, 2D 키포인트를 신경망으로 뽑고 SDK depth/positional tracking으로 3D화한다 → depth 품질(NEURAL 모드, 조명, 텍스처)이 곧 관절 z 품질.
5. **실전 품질 이슈 보고 존재**: ZED Mini 다수 구성에서 body tracking 품질 문제를 겪은 커뮤니티 사례가 있음 → 채택의 최종 판정은 문헌·사양이 아니라 **자기 리그 실측**(§8 파일럿).
6. **멀티 카메라 확장**: SDK 4.x Fusion 모듈이 다중 ZED 골격 융합 지원(ZED360 캘리브레이션). 2대 확장 시 GPU 예산 재산정 필요. (현행 SDK 문서에서 버전·지원 범위 재확인)

---

## 7. 트러블슈팅 빠른표

| 증상 | 1차 점검 |
|---|---|
| 카메라 미인식 | USB3 루트포트 직결 여부, 케이블 교체, `lsusb`, 다른 포트/PC |
| fps 저하 | 동일 USB 컨트롤러에 다른 장치 공유 여부, 해상도/depth 모드, GPU 점유 |
| SDK/CUDA 불일치 | ZED_Diagnostic 메시지 기준으로 드라이버·CUDA 재설치 |
| AI 모델 다운로드 실패 | 방화벽/프록시, ZED_Diagnostic에서 수동 다운로드 |
| 검출 불안정 | 조명(역광 금지·확산광), 거리(≤2 m), 신뢰도 임계 하향 실험, NEURAL 모드 확인 |
| IMU 이상 | 펌웨어 업데이트, 카메라 재연결 (Body Tracking은 IMU 탑재 요건) |

---

## 8. 다음 단계 (이 문서 범위 밖 — 순서만 고정)

1. **eye-on-base 캘리브레이션**: ChArUco + 로봇 자세 15–20개 → `T_base←cam`. 자동화는 easy_handeye2(ROS 2) 계열 사용. 이후 AR 태그 필드 데이텀 방식으로 원샷 재캘 체계 구축(별도 논의 완료).
2. **파일럿 검증**: EE 프로빙 정적(0.8 / 1.2 / 1.8 m) + 리니어 스테이지 동적(0.5 / 1.0 / 1.6 m/s) → 관절별 오차 분포 = ε(t) 바닥값. **여기서 ZED M 최종 합격 판정.**
3. **감시 스트림(D435 + RTMPose-m, CPU)** 추가 → 불일치 d(t) 분포 수집 → 임계 τ 산정.
4. **세션 프로토콜 T0–T5** 게이트 스크립트화(통과해야 제어 노드 기동).
5. ROS 2 노드화: 관절+신뢰도+타임스탬프 토픽 발행 → ε(t) 모듈 → 점유/CBF 층 연결.

---

## 9. 참고 (본 대화에서 링크 검증 완료분)

- Stereolabs Body Tracking 공식 문서 — ZED Mini 지원 명시, 모듈 구조(2D NN → depth 3D화): `stereolabs.com/docs/body-tracking`
- Maithani et al., *Proactive Hierarchical CBF-Based Safety Prioritization in Close HRI*, Control Eng. Practice 2025 (설정값 원전: HD720@60 · BODY_34 · ACCURATE · conf 52 · segmentation off): https://www.sciencedirect.com/science/article/abs/pii/S0967066125003867
- Thumm et al., *Vision-Based Safe HRC with Uncertainty Guarantees*, 2026 (불확실성·OOD 처리의 상위 참조): https://arxiv.org/abs/2604.15221
- RTMPose (감시 스트림용, CPU 90+FPS): https://arxiv.org/abs/2303.07399 · https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose
- easy_handeye2 (ROS 2 자동 핸드아이): https://github.com/marcoesposito1988/easy_handeye2
- 공식 SDK 샘플: `github.com/stereolabs/zed-sdk` (설치 시점 최신 브랜치 확인)

> **문서 관리 규칙**: 이 문서의 "출발점" 표기 값(신뢰도 임계 등)이 실측으로 확정되면, 확정값과 근거(로그 파일 경로·날짜)를 0절 표에 추가하고 상태를 "확정(실측)"으로 갱신할 것.
